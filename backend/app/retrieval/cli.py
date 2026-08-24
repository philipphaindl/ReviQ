"""Command line interface.

    python -m app.retrieval init
    python -m app.retrieval run "AI maturity assessment model" --pages 5
    python -m app.retrieval refetch <run_id> --dry-run --render-js
    python -m app.retrieval export <run_id> --out results.csv
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

import httpx

from . import (__version__, adopt, arxiv, batch, db, export, extract, figures,
               interchange, links, redact, refetch, report, serp, urls, vision)
from .archive import ArchiveReadError, SnapshotArchive, sha256_hex
from .archive import read_payload as archive_read_payload
from .fetch import fetch_url

# Rooted at DATA_DIR, which is the Docker volume ReviQ already keeps its own
# database in. Relative to the working directory it would land in the image at
# /app/data/ instead, outside the volume — and the next `docker compose up
# --build` would take a retrieved corpus with it. `data` as the fallback keeps
# a checkout usable without Docker, as before.
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DEFAULT_RUNS_DIR = DATA_DIR / "runs"


def default_db() -> Path:
    """Where a retrieval writes when `--db` is not given: ReviQ's own database.

    Taken from `DATABASE_URL` **when that variable is actually set**, so the CLI
    and the API cannot end up holding different files — which is what a separate
    `glr.sqlite3` was, and why the pilot corpus needs `adopt` at all.

    When it is *not* set, `DATA_DIR/reviq.db` — relative in a checkout, the
    volume under Docker. Reading `app.database.DATABASE_URL` instead would pick
    up that module's own default, which is container-shaped
    (`sqlite:////data/reviq.db`) because Compose always sets the variable
    anyway; locally that is an absolute path on a read-only root, and the first
    thing `db.connect` does is try to create it.

    A `DATABASE_URL` that is set but unusable is *not* swallowed: somebody
    configured it, and silently writing somewhere else is the two-databases
    situation this whole step removed.

    The import is deferred rather than module-level so that loading the
    retrieval package does not drag in the review side — the boundary this
    package keeps everywhere else. The parsing itself is not duplicated here:
    one implementation, in `app.database`, or the two could disagree about
    which file they mean.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        return Path(os.environ.get("DATA_DIR", "data")) / "reviq.db"

    from app.database import retrieval_db_path

    # Passed explicitly rather than left to the module-level constant, which is
    # frozen at import time — a CLI is invoked once, and what its environment
    # says now is what it means.
    return retrieval_db_path(url)


def _require_key(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"error: {name} is not set.\n"
            f"       cp .env.example .env, fill it in, then:\n"
            f"       set -a && source .env && set +a"
        )
    return value


def cmd_init(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    db.init_db(conn)
    conn.close()
    print(f"initialised {args.db}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    is_arxiv = args.engine == "arxiv"
    searchapi_key = None if is_arxiv else _require_key("SEARCHAPI_API_KEY")
    scrapingbee_key = _require_key("SCRAPINGBEE_API_KEY")

    conn = db.connect(args.db)
    db.init_db(conn)

    run_id = str(uuid.uuid4())
    search_params = {
        "pages": args.pages,
        "gl": args.gl,
        "hl": args.hl,
        "location": args.location,
        "render_js": args.render_js,
        "premium_proxy": args.premium_proxy,
        "stealth_proxy": args.stealth_proxy,
        "wait_ms": args.wait,
        "snowball_depth": args.snowball_depth,
        "snowball_max_links": args.snowball_max_links,
        "ocr": args.ocr,
        "describe_figures": args.describe_figures,
        "vision_model": args.vision_model,
        "max_figures": args.max_figures,
        "refetch": args.refetch,
    }
    project_id = getattr(args, "project", None)
    db.start_run(
        conn, run_id, args.query, args.engine,
        json.dumps(search_params, sort_keys=True), __version__,
        batch_id=getattr(args, "batch_id", None),
        project_id=project_id,
    )
    print(f"run {run_id}")
    print(f'query "{args.query}" on {args.engine}, {args.pages} page(s)')

    warc_path = args.runs_dir / run_id / "snapshots.warc.gz"

    try:
        # --- 1. SERP -----------------------------------------------------
        pending: list[tuple[int, str, str]] = []  # (document_id, canonical_url, raw_url)
        seen_documents: set[int] = set()

        with httpx.Client(timeout=serp.TIMEOUT) as client:
            for page in range(1, args.pages + 1):
                if is_arxiv:
                    xml_text = arxiv.fetch_page(args.query, page, client=client)
                    search_id = None
                    hits = arxiv.parse_entries(xml_text, page)
                else:
                    payload = serp.fetch_page(
                        searchapi_key, args.query, page,
                        engine=args.engine, gl=args.gl, hl=args.hl,
                        location=args.location, client=client,
                    )
                    search_id = serp.search_id_of(payload)
                    hits = serp.parse_organic(payload, page)
                retrieved_at = db.utc_now()
                print(f"  page {page}: {len(hits)} organic results")
                if not hits:
                    break

                for hit in hits:
                    canonical = urls.canonicalize(hit.raw_url)
                    document_id = db.upsert_document(
                        conn, canonical, urls.host_of(hit.raw_url), run_id
                    )
                    db.insert_serp_result(
                        conn, run_id, hit.page, hit.position, hit.global_rank,
                        hit.raw_url, canonical, hit.title, hit.snippet,
                        hit.displayed_link, retrieved_at, search_id, document_id,
                    )
                    # Deduplication in action: the same URL at two positions,
                    # or already known from an earlier run, is fetched once.
                    if document_id in seen_documents:
                        continue
                    seen_documents.add(document_id)
                    if not urls.is_fetchable(hit.raw_url):
                        continue
                    if not args.refetch and db.has_snapshot(conn, document_id,
                                                            project_id):
                        continue
                    pending.append((document_id, canonical, hit.raw_url))
                conn.commit()

        total_seen = len(seen_documents)
        print(f"{total_seen} unique document(s), {len(pending)} to fetch")

        # --- 2. fetch, archive, extract ----------------------------------
        credits_used = 0
        failures = 0
        empty_text = 0
        blocked = 0
        described = 0

        # The frontier is a queue of (document_id, url, depth). Depth 0 is the
        # SERP hits; snowballing appends depth 1 and beyond as pages are read.
        frontier: list[tuple[int, str, int]] = [(d, u, 0) for d, _c, u in pending]
        fetched_total = 0
        links_found = 0

        with SnapshotArchive(warc_path) as archive, httpx.Client(timeout=None) as client:
            while frontier:
                document_id, raw_url, depth = frontier.pop(0)
                fetched_total += 1
                marker = f"d{depth}" if depth else "  "
                print(f"  [{fetched_total}/{fetched_total + len(frontier)} {marker}] {raw_url[:84]}")
                result = fetch_url(
                    scrapingbee_key, raw_url,
                    render_js=args.render_js, premium_proxy=args.premium_proxy,
                    stealth_proxy=args.stealth_proxy, wait_ms=args.wait, client=client,
                )
                credits_used += result.credits_cost or 0
                fetched_at = db.utc_now()

                if not result.ok:
                    failures += 1
                    print(f"      failed: {result.error}")
                    db.insert_snapshot(
                        conn, document_id=document_id, run_id=run_id,
                        requested_url=raw_url, final_url=result.final_url,
                        origin_status_first=result.origin_status_first, proxy_status=result.proxy_status,
                        fetched_at_utc=fetched_at, credits_cost=result.credits_cost,
                        fetch_error=result.error,
                    )
                    conn.commit()
                    time.sleep(args.delay)
                    continue

                content = result.content
                media_type = extract.detect_media_type(content)
                # Archive before judging: a block page is still evidence that
                # the source was unreachable at this moment, and the WARC is
                # the record of what was actually served.
                record_id, offset = archive.write_response(
                    raw_url, content, result.content_type,
                    result.origin_status_first, result.final_url, result.credits_cost,
                )
                extraction = extract.extract(
                    content, media_type, url=result.final_url or raw_url, ocr=args.ocr
                )
                blocked_reason = extract.detect_block_page(content, extraction.text)
                if blocked_reason:
                    blocked += 1
                    print(f"      blocked: {blocked_reason}")
                elif extraction.word_count == 0:
                    empty_text += 1

                snapshot_id = db.insert_snapshot(
                    conn, document_id=document_id, run_id=run_id,
                    requested_url=raw_url, final_url=result.final_url,
                    origin_status_first=result.origin_status_first,
                    proxy_status=result.proxy_status,
                    content_type=result.content_type, content_length=len(content),
                    sha256=sha256_hex(content), media_type=media_type,
                    fetched_at_utc=fetched_at, warc_path=str(warc_path),
                    warc_offset=offset, warc_record_id=record_id,
                    credits_cost=result.credits_cost, blocked_reason=blocked_reason,
                )
                db.insert_extraction(
                    conn, snapshot_id=snapshot_id, extractor=extraction.extractor,
                    title=extraction.title, author=extraction.author,
                    publication_date=extraction.publication_date,
                    language=extraction.language, text=extraction.text,
                    word_count=extraction.word_count, extracted_at_utc=db.utc_now(),
                    extraction_error=extraction.error,
                )

                # --- snowballing -----------------------------------------
                # Only from a clean HTML page: a block page's links are the
                # firewall's, and a PDF is a leaf.
                if (
                    args.snowball_depth
                    and depth < args.snowball_depth
                    and media_type == "html"
                    and not blocked_reason
                ):
                    selected = links.select_snowball_links(
                        content, result.final_url or raw_url,
                        max_links=args.snowball_max_links,
                    )
                    for link in selected:
                        target_id = db.upsert_document(
                            conn, link.canonical_url, urls.host_of(link.resolved_url),
                            run_id, discovery_source="link", discovery_depth=depth + 1,
                        )
                        db.insert_link(
                            conn, document_id, target_id, snapshot_id, run_id,
                            link.raw_href, link.anchor_text, depth + 1,
                        )
                        links_found += 1
                        if target_id in seen_documents:
                            continue
                        seen_documents.add(target_id)
                        if not args.refetch and db.has_snapshot(conn, target_id,
                                                                project_id):
                            continue
                        frontier.append((target_id, link.resolved_url, depth + 1))

                # --- figures ---------------------------------------------
                # Only from a clean HTML page: a block page's images are the
                # firewall's, and a PDF needs a different extraction path.
                if (
                    args.describe_figures
                    and media_type == "html"
                    and not blocked_reason
                ):
                    described += _describe_figures(
                        conn, archive, client, scrapingbee_key, args,
                        content, result.final_url or raw_url,
                        document_id, snapshot_id, run_id, warc_path,
                    )

                conn.commit()
                time.sleep(args.delay)

        db.finish_run(conn, run_id, "completed")

        # --- 3. export ---------------------------------------------------
        # In a batch the per-query CSV would be noise; the batch exports once.
        print()
        if args.out is not None:
            rows = export.export_run(conn, run_id, args.out)
            print(f"wrote {rows} row(s) to {args.out}")
        if args.report is not None:
            report.report_run(conn, run_id, args.report)
            print(f"wrote report to {args.report}")
        print(f"snapshots: {warc_path}")
        print(f"credits used: {credits_used}")
        if described:
            print(f"figures described: {described} (model {args.vision_model})")
        if args.snowball_depth:
            print(
                f"snowballing: {links_found} link(s) followed to depth "
                f"{args.snowball_depth}, {fetched_total} document(s) fetched in total"
            )
        if failures:
            print(f"warning: {failures} of {fetched_total} fetches failed (see fetch_error)")
        if blocked:
            # The most dangerous failure mode in a review: HTTP 200, content
            # present, text extracted — and a firewall notice in the corpus.
            # The hint escalates from what this run already used, so it never
            # suggests repeating a setting that has just demonstrably failed.
            if args.stealth_proxy:
                hint = ("already at the strongest setting — read the archived "
                        "block page, then consider recording these as inaccessible")
            elif args.premium_proxy:
                hint = "try a longer --wait, then --stealth-proxy (75 credits)"
            else:
                hint = "try --premium-proxy --render-js"
            print(
                f"warning: {blocked} document(s) returned a block page instead of "
                f"the source (see blocked_reason); {hint}"
            )
        if empty_text:
            # Surfaced deliberately: silent empty text columns look like a data
            # problem rather than a retrieval problem, and the reader who could
            # act on it — by re-running with rendering — is the one at this
            # terminal, not the one reading the CSV a week later.
            print(
                f"warning: {empty_text} document(s) yielded no text "
                f"(see extraction_error; --render-js may help)"
            )
        return 0

    except KeyboardInterrupt:
        # Ctrl-C, or SIGTERM once _install_termination_handler has mapped it.
        # Without this the run row stays 'running' for ever, and anything
        # watching the database — a progress display, a later report — cannot
        # tell an interrupted run from one still in flight. Note that a bare
        # `except Exception` would not catch this.
        db.finish_run(conn, run_id, "failed", notes="interrupted")
        print("\ninterrupted — partial results are committed and the run is "
              "marked failed; re-running skips what was already archived")
        raise
    except Exception as exc:
        db.finish_run(conn, run_id, "failed",
                      notes=redact.scrub(f"{type(exc).__name__}: {exc}"))
        raise
    finally:
        conn.close()


def _describe_figures(
    conn, archive, client, scrapingbee_key, args,
    content, base_url, document_id, snapshot_id, run_id, warc_path,
) -> int:
    """Fetch, archive and describe the selected figures of one document.

    Archive first, describe second: the bytes are the evidence, the description
    is a claim about them. A description without its archived input cannot be
    checked by anyone.
    """
    described = 0
    for figure in figures.select_figures(content, base_url, max_figures=args.max_figures):
        image = fetch_url(scrapingbee_key, figure.resolved_url, render_js=False, client=client)
        fetched_at = db.utc_now()
        if not image.ok:
            db.insert_figure(
                conn, document_id=document_id, snapshot_id=snapshot_id, run_id=run_id,
                raw_src=figure.raw_src, resolved_url=figure.resolved_url,
                alt_text=figure.alt_text, caption=figure.caption,
                fetched_at_utc=fetched_at, credits_cost=image.credits_cost,
                fetch_error=image.error,
            )
            continue

        media_type = figures.media_type_of(image.content)
        if not figures.looks_describable(image.content, image.content_type):
            db.insert_figure(
                conn, document_id=document_id, snapshot_id=snapshot_id, run_id=run_id,
                raw_src=figure.raw_src, resolved_url=figure.resolved_url,
                alt_text=figure.alt_text, caption=figure.caption,
                sha256=sha256_hex(image.content), content_type=image.content_type,
                byte_size=len(image.content), fetched_at_utc=fetched_at,
                credits_cost=image.credits_cost,
                fetch_error="not a describable image (too small, vector, or unknown format)",
            )
            continue

        record_id, offset = archive.write_response(
            figure.resolved_url, image.content, image.content_type,
            image.origin_status_first, image.final_url, image.credits_cost,
        )
        figure_id = db.insert_figure(
            conn, document_id=document_id, snapshot_id=snapshot_id, run_id=run_id,
            raw_src=figure.raw_src, resolved_url=figure.resolved_url,
            alt_text=figure.alt_text, caption=figure.caption,
            sha256=sha256_hex(image.content), content_type=image.content_type,
            byte_size=len(image.content), warc_path=str(warc_path),
            warc_offset=offset, warc_record_id=record_id,
            credits_cost=image.credits_cost, fetched_at_utc=fetched_at,
        )

        result = vision.describe_figure(
            image.content, media_type, model=args.vision_model
        )
        db.insert_description(
            conn, figure_id=figure_id, description=result.description,
            model=result.model, prompt=result.prompt,
            input_tokens=result.input_tokens, output_tokens=result.output_tokens,
            described_at_utc=db.utc_now(), error=result.error,
        )
        if result.error:
            print(f"      figure not described: {result.error}")
        elif result.is_substantive:
            described += 1
    return described


def cmd_report(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    row = conn.execute(
        "SELECT 1 FROM runs WHERE run_id = ? OR batch_id = ? LIMIT 1",
        (args.id, args.id),
    ).fetchone()
    if row is None:
        conn.close()
        sys.exit(f"error: no run or batch with id {args.id}")
    is_batch = conn.execute(
        "SELECT 1 FROM runs WHERE batch_id = ? LIMIT 1", (args.id,)
    ).fetchone() is not None
    if is_batch:
        report.report_batch(conn, args.id, args.out)
    else:
        report.report_run(conn, args.id, args.out)
    conn.close()
    print(f"wrote report to {args.out}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Run a whole query set. One run per query, grouped by a batch_id.

    A query that fails does not abort the batch: in a review, nineteen of
    twenty queries succeeding is a result worth keeping, and the failure is
    recorded on its own run row.
    """
    try:
        specs = batch.load_config(args.config)
    except batch.ConfigError as exc:
        sys.exit(f"error: {exc}")
    except OSError as exc:
        sys.exit(f"error: cannot read {args.config}: {exc}")

    batch_id = str(uuid.uuid4())
    print(f"batch {batch_id}: {len(specs)} quer{'y' if len(specs) == 1 else 'ies'}\n")

    failed: list[str] = []
    for index, spec in enumerate(specs, start=1):
        print(f"--- [{index}/{len(specs)}] {spec.q}")
        run_args = argparse.Namespace(
            db=args.db, query=spec.q, runs_dir=args.runs_dir, delay=args.delay,
            refetch=args.refetch, out=None, batch_id=batch_id,
            pages=spec.params["pages"], engine=spec.params["engine"],
            gl=spec.params["gl"], hl=spec.params["hl"],
            location=spec.params["location"],
            render_js=spec.params["render_js"],
            premium_proxy=spec.params["premium_proxy"],
            stealth_proxy=spec.params["stealth_proxy"],
            wait=spec.params["wait_ms"],
            snowball_depth=spec.params["snowball_depth"],
            snowball_max_links=spec.params["snowball_max_links"],
            ocr=args.ocr, report=None,
            describe_figures=args.describe_figures,
            vision_model=args.vision_model,
            max_figures=args.max_figures,
            project=getattr(args, "project", None),
        )
        try:
            cmd_run(run_args)
        except Exception as exc:
            failed.append(spec.q)
            print(f"    query failed: {type(exc).__name__}: {exc}")
        print()

    conn = db.connect(args.db)
    rows = export.export_batch(conn, batch_id, args.out)

    if args.report is not None:
        report.report_batch(conn, batch_id, args.report)
    conn.close()

    print(f"batch {batch_id} finished")
    print(f"wrote {rows} row(s) to {args.out}")
    if args.report is not None:
        print(f"wrote report to {args.report}")
    if failed:
        print(f"warning: {len(failed)} of {len(specs)} queries failed:")
        for query in failed:
            print(f"  - {query}")
    return 1 if failed else 0


def cmd_init_config(args: argparse.Namespace) -> int:
    if args.path.exists():
        sys.exit(f"error: {args.path} already exists")
    args.path.write_text(batch.EXAMPLE, encoding="utf-8")
    print(f"wrote {args.path} — edit it, then: python -m app.retrieval batch {args.path}")
    return 0


def _check_target_project(conn, db_path: Path, project_id: int | None) -> None:
    """Refuse a target whose review side does not hold that project.

    The one place this package looks at a review table, and `adopt` is the one
    command whose entire purpose is to bridge into one. It earns the exception
    by catching a mistake that is otherwise silent and expensive: the target is
    whatever `--db` or `DATABASE_URL` resolves to, and if ReviQ runs in Docker
    while this command runs on the host, that is a *different file*. Adoption
    would succeed, into a database nobody reads, and the corpus would appear to
    have vanished.

    A missing `project` table means the same thing one step earlier — the file
    is not a ReviQ database at all, usually because it was just created empty by
    this very invocation.
    """
    if project_id is None:
        return
    tables = {
        row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if "project" not in tables:
        sys.exit(
            f"error: {db_path} holds no reviews — it has the retrieval tables "
            f"and nothing else.\n"
            f"       If ReviQ runs in Docker, its database is inside the volume, "
            f"not here. Point --db at the file ReviQ actually opens, or run this "
            f"inside the container."
        )
    known = [row["id"] for row in conn.execute("SELECT id FROM project ORDER BY id")]
    if project_id not in known:
        listed = ", ".join(str(i) for i in known) if known else "none"
        sys.exit(
            f"error: {db_path} has no project {project_id}. Projects there: {listed}"
        )


def _warn_if_runs_dir_is_transient(runs_dir: Path) -> None:
    """`--runs-dir` is not where the archive is read from — it is what gets
    *stored*.

    Every adopted snapshot keeps `DATA_DIR/runs/<run_id>/<file>` as its
    `warc_path`, and every later read resolves that string. Pointing it at a
    directory that only exists during this command — a read-only mount used to
    hand the old corpus in, say — writes paths that stop resolving the moment
    the command exits, and the failure surfaces much later as a document whose
    bytes cannot be found. Worth one line now.
    """
    data_dir = Path(os.environ.get("DATA_DIR", "data")).resolve()
    if not runs_dir.resolve().is_relative_to(data_dir):
        print(f"note: --runs-dir {runs_dir} is outside DATA_DIR ({data_dir}).\n"
              f"      That path is stored on every snapshot and has to keep "
              f"resolving after this command exits — move the WARC files into "
              f"place first if it will not.")


def cmd_adopt(args: argparse.Namespace) -> int:
    """Bring a corpus from a separate retrieval database into this one.

    Reads the source read-only and writes the target in a single transaction.
    The dry run performs the identical work and rolls it back, so its counts are
    the outcome rather than a prediction of it.
    """
    try:
        source = adopt.open_source(args.source)
    except adopt.AdoptError as exc:
        sys.exit(f"error: {exc}")

    conn = db.connect(args.db)
    _check_target_project(conn, args.db, args.project)
    _warn_if_runs_dir_is_transient(args.runs_dir)
    try:
        result = adopt.adopt(
            source, conn, project_id=args.project, runs_dir=args.runs_dir,
            dry_run=args.dry_run,
        )
    except adopt.AdoptError as exc:
        source.close()
        conn.close()
        sys.exit(f"error: {exc}")
    finally:
        source.close()

    conn.close()
    print(f"source: {args.source}")
    print(f"target: {args.db}")
    for line in adopt.describe(result, dry_run=args.dry_run):
        print(line)

    if not result.runs:
        print("nothing to do — every run in the source is already here")
        return 0
    if args.project is None:
        print("note: adopted without --project, so these runs belong to no "
              "review and their snapshots stay visible to all of them")
    if args.dry_run:
        print("dry run: rolled back, nothing written")
    else:
        print(f"{result.rows} row(s) adopted. Verify with: "
              f"python -m app.retrieval report <batch_id> --out r.md")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    rows = export.export_run(conn, args.run_id, args.out)
    conn.close()
    print(f"wrote {rows} row(s) to {args.out}")
    return 0


def cmd_export_json(args: argparse.Namespace) -> int:
    """Write the interchange package for a run or batch.

    Unlike the CSV this is entity-shaped — one record per document, with its
    search observations nested — and it carries the retrieval timestamp,
    payload digest and archive offset that make a grey source citable.
    """
    conn = db.connect(args.db)
    try:
        count = interchange.write_package(
            conn, args.id, args.out,
            include_text=not args.no_text,
            include_figures=not args.no_figures,
            include_unretrievable=not args.only_usable,
        )
    except LookupError as exc:
        conn.close()
        sys.exit(f"error: {exc}")
    conn.close()
    print(f"wrote {count} record(s) to {args.out}")
    if args.only_usable:
        print("note: --only-usable omits blocked and failed retrievals, so the "
              "record count will not reconcile with the retrieval report")
    return 0


def cmd_refetch(args: argparse.Namespace) -> int:
    """Retry exactly the documents a second attempt could recover.

    Deliberately narrow: no search is issued, so the sample stays what the
    original run observed, and nothing already recorded is modified. The retry
    is a new run with its own WARC; re-exporting the original run or batch
    afterwards picks up the better snapshot through `db.best_snapshot`.
    """
    conn = db.connect(args.db)
    only = set(args.only) if args.only else None
    try:
        scope = refetch.for_scope(conn, args.id, reasons=only)
    except LookupError as exc:
        conn.close()
        sys.exit(f"error: {exc}")

    candidates = scope.candidates
    per_request = refetch.estimated_credits(
        render_js=args.render_js, premium_proxy=args.premium_proxy,
        stealth_proxy=args.stealth_proxy,
    )
    print(f"{scope.kind} {args.id}: {scope.documents} document(s) in scope, "
          f"{len(candidates)} worth retrying")
    for label, count, hint in refetch.summarise(candidates):
        print(f"  {count:4}  {label}")
        print(f"        {hint}")

    if not candidates:
        print("nothing to do")
        conn.close()
        return 0

    print(f"\nestimated cost: {len(candidates)} x {per_request} = "
          f"{len(candidates) * per_request} credits")
    if args.dry_run:
        print("dry run: nothing fetched")
        conn.close()
        return 0

    scrapingbee_key = _require_key("SCRAPINGBEE_API_KEY")
    run_id = str(uuid.uuid4())
    search_params = {
        "refetch_of": args.id,
        "render_js": args.render_js,
        "premium_proxy": args.premium_proxy,
        "stealth_proxy": args.stealth_proxy,
        "wait_ms": args.wait,
        "ocr": args.ocr,
        "only": sorted(only) if only else None,
    }
    # A refetch run issues no query. `runs.query` is NOT NULL and describes what
    # a run did, so it says so plainly rather than borrowing the query of the
    # run being retried — which would make this look like a second search and
    # put a sampling event in the record that never happened.
    db.start_run(
        conn, run_id, f"refetch of {scope.kind} {args.id}", "none",
        json.dumps(search_params, sort_keys=True), __version__,
        # From the runs being repaired, not from --project: a retry belongs to
        # the search it repairs, and asking again is a chance to answer wrong.
        project_id=scope.project_id,
    )
    print(f"run {run_id}")

    warc_path = args.runs_dir / run_id / "snapshots.warc.gz"
    credits_used = recovered = still_failing = 0

    try:
        with SnapshotArchive(warc_path) as archive, httpx.Client(timeout=None) as client:
            for index, candidate in enumerate(candidates, start=1):
                print(f"  [{index}/{len(candidates)}] {candidate.url[:84]}")
                result = fetch_url(
                    scrapingbee_key, candidate.url,
                    render_js=args.render_js, premium_proxy=args.premium_proxy,
                    stealth_proxy=args.stealth_proxy, wait_ms=args.wait, client=client,
                )
                credits_used += result.credits_cost or 0
                fetched_at = db.utc_now()

                if not result.ok:
                    still_failing += 1
                    print(f"      still failing: {result.error}")
                    db.insert_snapshot(
                        conn, document_id=candidate.document_id, run_id=run_id,
                        requested_url=candidate.url, final_url=result.final_url,
                        origin_status_first=result.origin_status_first,
                        proxy_status=result.proxy_status, fetched_at_utc=fetched_at,
                        credits_cost=result.credits_cost, fetch_error=result.error,
                    )
                    conn.commit()
                    time.sleep(args.delay)
                    continue

                content = result.content
                media_type = extract.detect_media_type(content)
                record_id, offset = archive.write_response(
                    candidate.url, content, result.content_type,
                    result.origin_status_first, result.final_url, result.credits_cost,
                )
                extraction = extract.extract(
                    content, media_type,
                    url=result.final_url or candidate.url, ocr=args.ocr,
                )
                blocked_reason = extract.detect_block_page(content, extraction.text)
                snapshot_id = db.insert_snapshot(
                    conn, document_id=candidate.document_id, run_id=run_id,
                    requested_url=candidate.url, final_url=result.final_url,
                    origin_status_first=result.origin_status_first,
                    proxy_status=result.proxy_status, content_type=result.content_type,
                    content_length=len(content), sha256=sha256_hex(content),
                    media_type=media_type, fetched_at_utc=fetched_at,
                    warc_path=str(warc_path), warc_offset=offset,
                    warc_record_id=record_id, credits_cost=result.credits_cost,
                    blocked_reason=blocked_reason,
                )
                db.insert_extraction(
                    conn, snapshot_id=snapshot_id, extractor=extraction.extractor,
                    title=extraction.title, author=extraction.author,
                    publication_date=extraction.publication_date,
                    language=extraction.language, text=extraction.text,
                    word_count=extraction.word_count, extracted_at_utc=db.utc_now(),
                    extraction_error=extraction.error,
                )
                if blocked_reason:
                    still_failing += 1
                    print(f"      still blocked: {blocked_reason}")
                elif extraction.word_count:
                    recovered += 1
                    print(f"      recovered: {extraction.word_count} words")
                else:
                    still_failing += 1
                    print("      still no text")
                conn.commit()
                time.sleep(args.delay)

        db.finish_run(conn, run_id, "completed")
    except KeyboardInterrupt:
        db.finish_run(conn, run_id, "failed")
        conn.commit()
        conn.close()
        print("\ninterrupted; the snapshots already written are intact")
        return 130

    conn.commit()
    print()
    print(f"recovered: {recovered} of {len(candidates)}")
    print(f"still not usable: {still_failing}")
    print(f"credits used: {credits_used}")
    print(f"snapshots: {warc_path}")
    if recovered:
        # The retry wrote a separate run, so the original scope only shows the
        # improvement once it is re-exported.
        print(f"\nre-export the original scope to pick these up:")
        print(f"  python -m app.retrieval export-json {args.id} --out records.json")
        print(f"  python -m app.retrieval report {args.id} --out report.md")
    conn.close()
    return 0


def cmd_reextract(args: argparse.Namespace) -> int:
    """Re-run extraction against the archived bytes. No network, no credits.

    The design promise this redeems: the WARC is written before anything is
    extracted, so extraction is repeatable at any later time — after the
    extractor improves, or after it starts collecting a field it was not
    collecting before. Until now nothing exercised that promise, and a corpus
    stayed frozen at whatever the extractor of the day produced.

    Nothing is lost. Each replaced extraction is copied to `extraction_history`
    first, with the run that superseded it.
    """
    conn = db.connect(args.db)
    try:
        kind, run_ids = interchange.resolve_scope(conn, args.id)
    except LookupError as exc:
        conn.close()
        sys.exit(f"error: {exc}")

    ids = interchange.document_ids(conn, run_ids)
    # Same rule as the report and the export: the review is derived from the
    # runs asked for, so all three see the same snapshot per document.
    project_id = db.project_of_runs(conn, run_ids)
    if args.all:
        targets = refetch.archived(conn, ids, project_id)
        selection = "every archived document"
    else:
        only = set(args.only) if args.only else None
        candidates = refetch.select(conn, ids, reasons=only, action="reextract",
                                    project_id=project_id)
        wanted = {c.document_id for c in candidates}
        targets = [a for a in refetch.archived(conn, ids, project_id)
                   if a.document_id in wanted]
        selection = "documents whose recorded cause was an extraction failure"

    print(f"{kind} {args.id}: {len(ids)} document(s) in scope, "
          f"{len(targets)} to re-extract")
    print(f"selection: {selection}")
    if not args.all:
        for label, count, hint in refetch.summarise(
            refetch.select(conn, ids, action="reextract", project_id=project_id)
        ):
            print(f"  {count:4}  {label}")
            print(f"        {hint}")
        if not targets:
            print("nothing to do — use --all to re-extract the whole corpus, "
                  "which is what an extractor change calls for")

    if not targets:
        conn.close()
        return 0

    # No credits are at stake, so the dry run is about time rather than money:
    # a few hundred documents through trafilatura and pdfminer is minutes.
    print(f"\nno network access, no credits — {len(targets)} document(s) "
          f"re-read from the archive")
    if args.dry_run:
        print("dry run: nothing extracted")
        conn.close()
        return 0

    run_id = str(uuid.uuid4())
    db.start_run(
        conn, run_id, f"reextract of {kind} {args.id}", "none",
        json.dumps({"reextract_of": args.id, "all": args.all,
                    "ocr": args.ocr,
                    "only": sorted(args.only) if args.only else None},
                   sort_keys=True),
        __version__,
        project_id=project_id,
    )
    print(f"run {run_id}")

    changed = gained_text = lost_text = unreadable = superseded = 0
    language_filled = 0

    try:
        for index, target in enumerate(targets, start=1):
            # A line per document, before the work rather than after it: a few
            # hundred documents through trafilatura and pdfminer runs for
            # minutes, and a command that prints only when something goes wrong
            # is indistinguishable from one that has hung. It also names the
            # document being worked on, so an interruption says where it stopped.
            print(f"  [{index}/{len(targets)}] {target.url[:78]}")
            path = Path(target.warc_path)
            try:
                content = archive_read_payload(path, target.warc_offset, target.sha256)
            except ArchiveReadError as exc:
                unreadable += 1
                print(f"      unreadable: {exc}")
                continue

            before = conn.execute(
                "SELECT word_count, language FROM extractions WHERE snapshot_id = ?",
                (target.snapshot_id,),
            ).fetchone()
            media_type = target.media_type or extract.detect_media_type(content)
            extraction = extract.extract(
                content, media_type, url=target.url, ocr=args.ocr
            )
            was_superseded = db.replace_extraction(
                conn, target.snapshot_id, run_id,
                extractor=extraction.extractor, title=extraction.title,
                author=extraction.author,
                publication_date=extraction.publication_date,
                language=extraction.language, text=extraction.text,
                word_count=extraction.word_count, extracted_at_utc=db.utc_now(),
                extraction_error=extraction.error,
            )
            superseded += 1 if was_superseded else 0

            old_words = (before["word_count"] if before else 0) or 0
            if extraction.word_count and not old_words:
                gained_text += 1
                print(f"      now has text: {extraction.word_count} words")
            elif old_words and not extraction.word_count:
                # A regression, not a detail: the corpus just lost a source.
                lost_text += 1
                print(f"      LOST text: had {old_words} words, now none "
                      f"({extraction.error or 'no error reported'})")
            elif (before is not None and not before["language"]
                    and extraction.language):
                # The reason this command exists, so it should be visible while
                # it happens rather than only in the total at the end.
                print(f"      language now recorded: {extraction.language}")
            if before is not None and not before["language"] and extraction.language:
                language_filled += 1
            if extraction.word_count != old_words:
                changed += 1
            conn.commit()

        db.finish_run(conn, run_id, "completed")
    except KeyboardInterrupt:
        db.finish_run(conn, run_id, "failed")
        conn.commit()
        conn.close()
        print("\ninterrupted; the extractions already written are intact")
        return 130

    conn.commit()
    print()
    print(f"re-extracted: {len(targets) - unreadable} of {len(targets)}")
    print(f"previous extractions kept in extraction_history: {superseded}")
    print(f"word count changed: {changed}")
    if language_filled:
        print(f"language now recorded where it was not: {language_filled}")
    if gained_text:
        print(f"gained text: {gained_text}")
    if lost_text:
        print(f"warning: {lost_text} document(s) lost their text. The previous "
              f"extraction is in extraction_history; check before exporting.")
    if unreadable:
        print(f"warning: {unreadable} document(s) could not be read from the "
              f"archive (see the messages above)")
    conn.close()
    return 0


def _install_termination_handler() -> None:
    """Make SIGTERM unwind like Ctrl-C does.

    A supervisor stopping this process — a container shutting down, or a UI
    cancelling a retrieval job — sends SIGTERM, and Python's default handler
    exits without running any cleanup. The run row would then stay 'running'
    for ever, and nothing reading the database could tell an interrupted run
    from one still in flight. Raising KeyboardInterrupt routes SIGTERM through
    the same handler as Ctrl-C, which marks the run failed.
    """
    def handler(signum, frame):  # noqa: ARG001 - signal handler signature
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, handler)
    except (AttributeError, OSError, ValueError):
        # No SIGTERM on this platform, or not running in the main thread.
        pass


# Offered by the three subcommands that record a run, and by no others.
#
# It was global once, which put it before the subcommand while every other
# option goes after — `adopt data/glr.sqlite3 --project 1` failed outright. The
# README managed to write it both ways in one file, which is evidence enough
# that the position was the problem.
#
# The seven remaining subcommands are not missing it. `report`, `export-json`,
# `refetch` and `reextract` derive the project from the runs they were asked to
# read — a run belongs to a review, so the ids already name it — and taking it
# as an argument would be a second chance to name it wrong; `init`,
# `init-config` and `export` have no project at all.
_PROJECT_HELP = ("the review this retrieval belongs to. Recorded on the run, "
                 "and confines snapshot reuse to that review's own retrievals")


def build_parser() -> argparse.ArgumentParser:
    """The command line surface, buildable without running anything.

    Separate from `main` so a test can inspect what the CLI accepts and where.
    Nothing covered `cli.py` at all until a misplaced flag made that expensive.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.retrieval",
        description="Creel — provenance-preserving retrieval of grey literature, for ReviQ.",
    )
    parser.add_argument("--version", action="version",
                        version=f"Creel {__version__} — ReviQ's grey-literature retrieval")
    parser.add_argument("--db", type=Path, default=None,
                        help="SQLite database path (default: ReviQ's own, from "
                             "DATABASE_URL)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="create the database")
    p_init.set_defaults(func=cmd_init)

    p_run = subparsers.add_parser("run", help="search, fetch, archive, extract, export")
    p_run.add_argument("query", help="the search string")
    p_run.add_argument("--project", type=int, default=None, metavar="ID",
                       help=_PROJECT_HELP)
    p_run.add_argument("--pages", type=int, default=5,
                       help="SERP pages to retrieve; 10 results each (default: 5)")
    p_run.add_argument("--engine", default="google",
                       help="'google' (or any SearchApi.io engine, needs "
                            "SEARCHAPI_API_KEY) or 'arxiv' (arXiv's own API, "
                            "free and keyless)")
    p_run.add_argument("--gl", default=None, help="country code, e.g. at, de, us")
    p_run.add_argument("--hl", default=None, help="interface language, e.g. en, de")
    p_run.add_argument("--location", default=None, help="canonical location string")
    p_run.add_argument("--render-js", action="store_true",
                       help="render JavaScript (5 credits instead of 1)")
    p_run.add_argument("--premium-proxy", action="store_true",
                       help="use premium proxies (10 credits, 25 with --render-js)")
    p_run.add_argument("--stealth-proxy", action="store_true",
                       help="stealth proxies for JS challenge walls (75 credits); "
                            "use only after --premium-proxy has failed")
    p_run.add_argument("--wait", type=int, default=None, metavar="MS",
                       help="wait N ms after load before returning (needs "
                            "--render-js); lets a passed JS challenge finish "
                            "redirecting to the real content")
    p_run.add_argument("--snowball-depth", type=int, default=0, metavar="N",
                       help="follow selected outgoing links N levels deep "
                            "(default 0 = off)")
    p_run.add_argument("--snowball-max-links", type=int, default=20, metavar="N",
                       help="max links followed per document (default 20)")
    p_run.add_argument("--ocr", action="store_true",
                       help="OCR PDFs that have no text layer "
                            "(needs: pip install -r requirements-optional.txt, plus tesseract)")
    p_run.add_argument("--describe-figures", action="store_true",
                       help="fetch and describe figures with a vision model "
                            "(needs: pip install -r requirements-optional.txt, plus ANTHROPIC_API_KEY)")
    p_run.add_argument("--vision-model", default=vision.DEFAULT_MODEL, metavar="ID",
                       help=f"model for figure descriptions (default: {vision.DEFAULT_MODEL})")
    p_run.add_argument("--max-figures", type=int, default=5, metavar="N",
                       help="max figures described per document (default 5)")
    p_run.add_argument("--report", type=Path, default=None, metavar="PATH",
                       help="also write a Markdown retrieval report")
    p_run.add_argument("--refetch", action="store_true",
                       help="re-fetch documents that already have a snapshot")
    p_run.add_argument("--delay", type=float, default=1.0,
                       help="seconds between fetches (default: 1.0)")
    p_run.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    p_run.add_argument("--out", type=Path, default=Path("results.csv"))
    p_run.set_defaults(func=cmd_run)

    p_batch = subparsers.add_parser("batch", help="run a whole query set from a TOML file")
    p_batch.add_argument("config", type=Path, help="path to the query set, e.g. queries.toml")
    p_batch.add_argument("--project", type=int, default=None, metavar="ID",
                         help=_PROJECT_HELP)
    p_batch.add_argument("--out", type=Path, default=Path("results.csv"))
    p_batch.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    p_batch.add_argument("--delay", type=float, default=1.0)
    p_batch.add_argument("--refetch", action="store_true")
    p_batch.add_argument("--ocr", action="store_true",
                         help="OCR PDFs without a text layer")
    p_batch.add_argument("--describe-figures", action="store_true")
    p_batch.add_argument("--vision-model", default=vision.DEFAULT_MODEL)
    p_batch.add_argument("--max-figures", type=int, default=5)
    p_batch.add_argument("--report", type=Path, default=None, metavar="PATH",
                         help="also write a Markdown retrieval report")
    p_batch.set_defaults(func=cmd_batch)

    p_refetch = subparsers.add_parser(
        "refetch",
        help="retry only the documents an earlier run could not use",
        description="Retry the documents of a run or batch whose recorded cause "
                    "a second attempt could change. No search is issued and "
                    "nothing already recorded is modified: the retry is a new "
                    "run, and re-exporting the original scope afterwards picks "
                    "up whatever it recovered.",
    )
    p_refetch.add_argument("id", help="a run_id or a batch_id")
    p_refetch.add_argument("--dry-run", action="store_true",
                           help="list the candidates and the estimated credit "
                                "cost, fetch nothing")
    p_refetch.add_argument("--only", nargs="+", metavar="REASON", default=None,
                           help="retry only these causes, e.g. --only "
                                "no_main_content; see the retrieval report for "
                                "which apply")
    p_refetch.add_argument("--render-js", action="store_true",
                           help="render JavaScript (5 credits instead of 1); the "
                                "usual remedy for a page that carried no text")
    p_refetch.add_argument("--premium-proxy", action="store_true",
                           help="use premium proxies (10 credits, 25 with --render-js)")
    p_refetch.add_argument("--stealth-proxy", action="store_true",
                           help="stealth proxies for JS challenge walls (75 credits)")
    p_refetch.add_argument("--wait", type=int, default=None, metavar="MS",
                           help="wait N ms after load before returning (needs --render-js)")
    p_refetch.add_argument("--ocr", action="store_true",
                           help="OCR PDFs that have no text layer")
    p_refetch.add_argument("--delay", type=float, default=1.0,
                           help="seconds between fetches (default: 1.0)")
    p_refetch.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    p_refetch.set_defaults(func=cmd_refetch)

    p_reex = subparsers.add_parser(
        "reextract",
        help="re-run extraction from the archive — no network, no credits",
        description="Re-read documents out of the WARC and extract them again. "
                    "Use --all after an extractor change or to fill a field "
                    "that was not being collected before; without it, only the "
                    "documents whose recorded cause was an extraction failure "
                    "are re-read. Each replaced extraction is kept in "
                    "extraction_history.",
    )
    p_reex.add_argument("id", help="a run_id or a batch_id")
    p_reex.add_argument("--all", action="store_true",
                        help="re-extract every archived document in scope, not "
                             "only the ones a recorded cause points at")
    p_reex.add_argument("--only", nargs="+", metavar="REASON", default=None,
                        help="restrict to these causes, e.g. --only no_text_layer")
    p_reex.add_argument("--ocr", action="store_true",
                        help="OCR PDFs that have no text layer "
                             "(needs: pip install -r requirements-optional.txt, plus tesseract)")
    p_reex.add_argument("--dry-run", action="store_true",
                        help="list what would be re-extracted, change nothing")
    p_reex.set_defaults(func=cmd_reextract)

    p_config = subparsers.add_parser("init-config", help="write a starter query set")
    p_config.add_argument("path", type=Path, nargs="?", default=Path("queries.toml"))
    p_config.set_defaults(func=cmd_init_config)

    p_rep = subparsers.add_parser("report", help="write a Markdown retrieval report")
    p_rep.add_argument("id", help="a run_id or a batch_id")
    p_rep.add_argument("--out", type=Path, default=Path("report.md"))
    p_rep.set_defaults(func=cmd_report)

    p_adopt = subparsers.add_parser(
        "adopt",
        help="take a corpus from a separate retrieval database into this one",
    )
    p_adopt.add_argument("source", type=Path,
                         help="the old SQLite file, e.g. data/glr.sqlite3")
    p_adopt.add_argument("--project", type=int, default=None, metavar="ID",
                         help="the review the adopted runs belong to. Without "
                              "it they belong to none, and their snapshots stay "
                              "visible to every project")
    p_adopt.add_argument("--dry-run", action="store_true",
                         help="do the work and roll it back; reports exactly "
                              "what the real run would write")
    p_adopt.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR,
                         help="where the WARC files are expected, as "
                              "<runs-dir>/<run_id>/. Checked, never written")
    p_adopt.set_defaults(func=cmd_adopt)

    p_export = subparsers.add_parser("export", help="re-export an earlier run")
    p_export.add_argument("run_id")
    p_export.add_argument("--out", type=Path, default=Path("results.csv"))
    p_export.set_defaults(func=cmd_export)

    p_json = subparsers.add_parser(
        "export-json",
        help="write a provenance-carrying JSON package for a run or batch",
    )
    p_json.add_argument("id", help="a run_id or a batch_id")
    p_json.add_argument("--out", type=Path, default=Path("records.json"))
    p_json.add_argument("--no-text", action="store_true",
                        help="omit the extracted text (a much smaller file)")
    p_json.add_argument("--no-figures", action="store_true",
                        help="omit figures and their generated descriptions")
    p_json.add_argument("--only-usable", action="store_true",
                        help="omit blocked and failed retrievals; the counts "
                             "will then no longer reconcile with the report")
    p_json.set_defaults(func=cmd_export_json)

    return parser


def main(argv: list[str] | None = None) -> int:
    _install_termination_handler()
    args = build_parser().parse_args(argv)
    if args.db is None:
        args.db = default_db()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
