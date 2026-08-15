"""WARC round-trip against the real warcio.

Writes a snapshot, then reads it back with warcio's own reader. This is the
one part of the pipeline that cannot be checked by inspection: if the records
are malformed, they still write happily and only fail when someone tries to
open the archive — which, for a provenance tool, would be the worst possible
time to find out.

No network, no API keys.
"""

import gzip

import pytest
from warcio.archiveiterator import ArchiveIterator

from app.retrieval.archive import (ArchiveReadError, SnapshotArchive, read_payload,
                         sha256_hex)

PAYLOAD = b"<!DOCTYPE html><html><body><p>archived content</p></body></html>"
URL = "https://example.org/report"


def _write_one(tmp_path, **overrides):
    path = tmp_path / "snapshots.warc.gz"
    kwargs = dict(
        url=URL,
        content=PAYLOAD,
        content_type="text/html; charset=utf-8",
        origin_status_first=200,
        final_url=URL + "?redirected=1",
        credits_cost=1,
    )
    kwargs.update(overrides)
    with SnapshotArchive(path) as archive:
        record_id, offset = archive.write_response(**kwargs)
    return path, record_id, offset


def test_archive_is_readable_by_warcio(tmp_path):
    path, _, _ = _write_one(tmp_path)
    with path.open("rb") as fh:
        records = [(r.rec_type, r.rec_headers.get_header("WARC-Target-URI"))
                   for r in ArchiveIterator(fh)]
    types = [t for t, _ in records]
    assert "response" in types
    assert "metadata" in types


def test_response_record_round_trips_the_payload(tmp_path):
    path, _, _ = _write_one(tmp_path)
    with path.open("rb") as fh:
        for record in ArchiveIterator(fh):
            if record.rec_type == "response":
                assert record.content_stream().read() == PAYLOAD
                return
    raise AssertionError("no response record found")


def test_record_targets_the_resolved_url(tmp_path):
    """The archive should point at where the content actually came from."""
    path, _, _ = _write_one(tmp_path)
    with path.open("rb") as fh:
        for record in ArchiveIterator(fh):
            if record.rec_type == "response":
                assert record.rec_headers.get_header("WARC-Target-URI") == URL + "?redirected=1"
                return
    raise AssertionError("no response record found")


def test_metadata_record_carries_the_origin_facts(tmp_path):
    """The provenance the response record structurally cannot hold, because
    the response came from the proxy rather than the origin."""
    path, _, _ = _write_one(tmp_path)
    with path.open("rb") as fh:
        for record in ArchiveIterator(fh):
            if record.rec_type == "metadata":
                fields = record.content_stream().read().decode()
                assert f"requested-url: {URL}" in fields
                assert "origin-status-first: 200" in fields
                assert "retrieved-via: scrapingbee" in fields
                assert f"payload-sha256: {sha256_hex(PAYLOAD)}" in fields
                return
    raise AssertionError("no metadata record found")


def test_redirected_response_is_not_stamped_with_the_redirect_status(tmp_path):
    """Regression: ScrapingBee's Spb-Initial-Status-Code reports the FIRST
    status in the chain (verified against http://github.com -> 301). Writing
    that into the response record produced a record announcing 301 above a full
    HTML body. The record holds the body served at the resolved URL, so its
    status line must say 200; the 301 belongs in the metadata record."""
    path, _, _ = _write_one(tmp_path, origin_status_first=301)
    with path.open("rb") as fh:
        for record in ArchiveIterator(fh):
            if record.rec_type == "response":
                assert record.http_headers.get_statuscode() == "200"
                assert record.content_stream().read() == PAYLOAD
                break
        else:
            raise AssertionError("no response record found")

    with path.open("rb") as fh:
        for record in ArchiveIterator(fh):
            if record.rec_type == "metadata":
                assert "origin-status-first: 301" in record.content_stream().read().decode()
                return
    raise AssertionError("no metadata record found")


def test_stored_offset_seeks_to_the_record(tmp_path):
    """warc_offset is stored per snapshot so a single record can be read back
    without scanning the archive. If gzip member framing is wrong, this is
    where it shows."""
    path, _, offset = _write_one(tmp_path)
    with path.open("rb") as fh:
        fh.seek(offset)
        member = gzip.decompress(fh.read())
    assert b"WARC/1.1" in member
    assert PAYLOAD in member


def test_second_write_appends_at_a_later_offset(tmp_path):
    path = tmp_path / "snapshots.warc.gz"
    with SnapshotArchive(path) as archive:
        _, first = archive.write_response(
            url=URL, content=PAYLOAD, content_type="text/html",
            origin_status_first=200, final_url=URL, credits_cost=1,
        )
        _, second = archive.write_response(
            url=URL + "/2", content=b"second document", content_type="text/html",
            origin_status_first=200, final_url=URL + "/2", credits_cost=1,
        )
    assert second > first
    with path.open("rb") as fh:
        assert sum(1 for r in ArchiveIterator(fh) if r.rec_type == "response") == 2


def test_record_ids_are_distinct(tmp_path):
    path = tmp_path / "snapshots.warc.gz"
    with SnapshotArchive(path) as archive:
        first, _ = archive.write_response(
            url=URL, content=PAYLOAD, content_type="text/html",
            origin_status_first=200, final_url=URL, credits_cost=1,
        )
        second, _ = archive.write_response(
            url=URL + "/2", content=b"other", content_type="text/html",
            origin_status_first=200, final_url=URL + "/2", credits_cost=1,
        )
    assert first and second and first != second


def test_binary_payload_survives_unchanged(tmp_path):
    """PDFs must come back byte-identical — the SHA-256 in the CSV is only
    meaningful if the archived bytes are the retrieved bytes."""
    pdf = b"%PDF-1.7\n\x00\x01\x02binary\xff\xfe payload\n%%EOF"
    path = tmp_path / "snapshots.warc.gz"
    with SnapshotArchive(path) as archive:
        archive.write_response(
            url=URL, content=pdf, content_type="application/pdf",
            origin_status_first=200, final_url=URL, credits_cost=1,
        )
    with path.open("rb") as fh:
        for record in ArchiveIterator(fh):
            if record.rec_type == "response":
                assert record.content_stream().read() == pdf
                return
    raise AssertionError("no response record found")


# --- reading back out, which is what makes extraction repeatable ----------


def test_read_payload_returns_the_archived_bytes(tmp_path):
    """The promise the whole design rests on: the WARC is written before
    anything is extracted, so extraction can run again at any later time
    without touching the network."""
    path, _, offset = _write_one(tmp_path)
    assert read_payload(path, offset) == PAYLOAD


def test_read_payload_seeks_rather_than_scans(tmp_path):
    """One gzip member per record is what makes a stored offset a seek. Reading
    the second of three records must not depend on the first two."""
    path = tmp_path / "snapshots.warc.gz"
    payloads = [b"<html>first</html>", b"<html>second</html>", b"<html>third</html>"]
    offsets = []
    with SnapshotArchive(path) as archive:
        for index, payload in enumerate(payloads):
            _, offset = archive.write_response(
                f"{URL}/{index}", payload, "text/html", 200, None, 1
            )
            offsets.append(offset)

    for offset, payload in zip(offsets, payloads):
        assert read_payload(path, offset) == payload


def test_read_payload_verifies_the_digest_when_given_one(tmp_path):
    path, _, offset = _write_one(tmp_path)
    assert read_payload(path, offset, sha256_hex(PAYLOAD)) == PAYLOAD


def test_a_digest_mismatch_refuses_rather_than_returning_the_bytes(tmp_path):
    """An archive rewritten, truncated or restored from the wrong backup would
    otherwise feed a corpus content the database describes incorrectly, and
    every claim resting on that document would be quietly wrong."""
    path, _, offset = _write_one(tmp_path)
    with pytest.raises(ArchiveReadError) as exc:
        read_payload(path, offset, "0" * 64)
    assert "does not hold the recorded bytes" in str(exc.value)


def test_a_missing_archive_raises_the_archive_error(tmp_path):
    with pytest.raises(ArchiveReadError):
        read_payload(tmp_path / "absent.warc.gz", 0)


def test_an_offset_pointing_at_the_metadata_record_is_refused(tmp_path):
    """The metadata record sits immediately after its response record. Reading
    it as a document would put the provenance fields into the corpus as if they
    were the source text."""
    path, _, offset = _write_one(tmp_path)
    with path.open("rb") as fh:
        fh.seek(offset)
        iterator = ArchiveIterator(fh)
        offsets = [(iterator.get_record_offset(), record.rec_type)
                   for record in iterator]
    metadata_offset = next(o for o, kind in offsets if kind == "metadata")

    with pytest.raises(ArchiveReadError) as exc:
        read_payload(path, metadata_offset)
    assert "metadata" in str(exc.value)


def test_an_offset_that_is_not_a_record_boundary_is_refused(tmp_path):
    """Whatever the archive layer raises on garbage, the caller sees one error
    type — a re-extraction over hundreds of documents reports the bad one and
    carries on."""
    path, _, offset = _write_one(tmp_path)
    with pytest.raises(ArchiveReadError):
        read_payload(path, offset + 7)


def test_no_offset_inside_a_record_returns_bytes(tmp_path):
    """The whole neighbourhood, not one offset, because the failure this
    replaced was intermittent.

    Handed a stream that does not begin a gzip member, warcio stops treating
    the file as compressed and scans for an uncompressed record instead. About
    one attempt in twenty it found something in the deflated bytes it read as a
    response with an empty body, and `read_payload` returned b"" for an offset
    that was simply wrong — a re-extraction would have recorded an empty
    document where the archive could not be read. Which of the two happened
    depended on the compressed bytes, and those vary per record: the record id
    is a fresh UUID and the date is the current time. So the test that caught
    it failed roughly one run in twenty and passed on a re-run.
    """
    path, _, offset = _write_one(tmp_path)
    for delta in range(1, 48):
        with pytest.raises(ArchiveReadError):
            read_payload(path, offset + delta)


def test_an_offset_past_the_end_is_refused(tmp_path):
    path, _, _ = _write_one(tmp_path)
    with pytest.raises(ArchiveReadError):
        read_payload(path, path.stat().st_size + 1)


def test_a_binary_payload_reads_back_unchanged(tmp_path):
    payload = b"%PDF-1.7\n\x00\x01\x02\xff\xfe binary body \x00"
    path, _, offset = _write_one(tmp_path, content=payload,
                                 content_type="application/pdf")
    assert read_payload(path, offset, sha256_hex(payload)) == payload
