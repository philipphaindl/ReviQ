"""WARC snapshot writing.

WARC (ISO 28500) rather than loose files: it keeps the HTTP headers with the
payload, carries a payload digest in-format, and can be opened in existing
tooling (pywb, ReplayWeb.page) — so a reviewer can see the source as it looked
at retrieval time.

One honest caveat, which belongs in any paper using this tool: retrieval goes
through ScrapingBee, so the `response` record holds the proxy's answer, not the
origin server's raw answer. The origin facts ScrapingBee does report
(Spb-Initial-Status-Code, Spb-Resolved-Url, Spb-Cost) are written alongside as
a `metadata` record, so the WARC alone is enough to reconstruct the retrieval.

Files are written with gzip=True, which produces one gzip member per record.
That is what makes the stored `warc_offset` usable for random access later.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from types import TracebackType

from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

WARC_VERSION = "1.1"  # 1.1 stores WARC-Date with microsecond precision


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ArchiveReadError(Exception):
    """The archived bytes could not be produced from the file and offset."""


def read_payload(path: Path, offset: int, expected_sha256: str | None = None) -> bytes:
    """The bytes of one archived response, by file and offset.

    This is the half of the design that `warc_offset` exists for: one gzip
    member per record means a stored offset is a seek, not a scan, so
    re-reading one document out of a 200 MB archive costs the same as reading
    the first. Everything downstream of retrieval — extraction, and any later
    correction to it — can therefore run again without touching the network.

    `expected_sha256` is checked when given, and a mismatch raises rather than
    returning the bytes. The point of storing a digest beside an offset is that
    the pair can disagree: an archive rewritten, truncated, or restored from
    the wrong backup would otherwise feed a corpus content that the database
    describes incorrectly, and every claim resting on that document would be
    quietly wrong. Refusing is the only safe answer.
    """
    from warcio.archiveiterator import ArchiveIterator

    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            for record in ArchiveIterator(fh):
                if record.rec_type != "response":
                    raise ArchiveReadError(
                        f"{path.name}@{offset} holds a {record.rec_type!r} record, "
                        f"not a response"
                    )
                payload = record.content_stream().read()
                break
            else:
                raise ArchiveReadError(f"no record at {path.name}@{offset}")
    except ArchiveReadError:
        raise
    except Exception as exc:
        # Deliberately broad. A missing file, a truncated gzip member, an
        # offset pointing into the middle of one, a warcio parse failure —
        # every one of them means the same thing to the caller, and a
        # re-extraction covering hundreds of documents must report the bad one
        # and carry on rather than abort on whichever exception type the
        # archive layer happened to raise.
        raise ArchiveReadError(f"{type(exc).__name__}: {exc}") from exc

    if expected_sha256 and sha256_hex(payload) != expected_sha256:
        raise ArchiveReadError(
            f"{path.name}@{offset} does not hold the recorded bytes: "
            f"expected sha256 {expected_sha256[:16]}…, "
            f"found {sha256_hex(payload)[:16]}…"
        )
    return payload


class SnapshotArchive:
    """Append-only WARC file for a single run."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._writer = None

    def __enter__(self) -> "SnapshotArchive":
        self._fh = self.path.open("ab")
        self._writer = WARCWriter(self._fh, gzip=True, warc_version=WARC_VERSION)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._fh is not None:
            self._fh.close()

    def write_response(
        self,
        url: str,
        content: bytes,
        content_type: str | None,
        origin_status_first: int | None,
        final_url: str | None,
        credits_cost: int | None,
    ) -> tuple[str, int]:
        """Write the response record plus a metadata record with the proxy's
        provenance headers. Returns (warc_record_id, byte offset).

        The response record's status line is always 200: this method is only
        reached when content actually arrived, and the record holds the body
        served at the *resolved* URL. Stamping the redirect status here instead
        would produce a record announcing 301 above a full HTML body — a
        contradiction that replay tools are right to distrust. The first status
        of the chain is recorded in the metadata record, where it belongs.
        """
        if self._writer is None or self._fh is None:
            raise RuntimeError("SnapshotArchive must be used as a context manager")

        offset = self._fh.tell()

        http_headers = StatusAndHeaders(
            "200 OK",
            [("Content-Type", content_type or "application/octet-stream"),
             ("Content-Length", str(len(content)))],
            protocol="HTTP/1.1",
        )
        record = self._writer.create_warc_record(
            final_url or url,
            "response",
            payload=BytesIO(content),
            http_headers=http_headers,
        )
        record_id = record.rec_headers.get_header("WARC-Record-ID")
        self._writer.write_record(record)

        # Retrieval facts that the response record cannot carry, because the
        # response came from the proxy rather than the origin.
        provenance = (
            f"requested-url: {url}\r\n"
            f"resolved-url: {final_url or ''}\r\n"
            f"origin-status-first: "
            f"{origin_status_first if origin_status_first is not None else ''}\r\n"
            f"retrieved-via: scrapingbee\r\n"
            f"credits-cost: {credits_cost if credits_cost is not None else ''}\r\n"
            f"payload-sha256: {sha256_hex(content)}\r\n"
        ).encode("utf-8")
        meta = self._writer.create_warc_record(
            final_url or url,
            "metadata",
            payload=BytesIO(provenance),
            warc_content_type="application/warc-fields",
        )
        meta.rec_headers.add_header("WARC-Concurrent-To", record_id)
        self._writer.write_record(meta)

        self._fh.flush()
        return record_id, offset
