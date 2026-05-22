"""
PDF report generator — 10-section A4 document covering protocol through results.

Sections 1–9 use fpdf2; section 10 (per-paper summaries) uses ReportLab Platypus
because fpdf2 can't wrap text inside table cells. The two halves are merged with pypdf.
An optional PRISMA SVG from the frontend is converted to a vector page via svglib.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from itertools import groupby
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from pydantic import BaseModel
from sqlmodel import Session, select

from ..database import get_session
from ..models import (
    ConflictLog, DatabaseSearchString, ExclusionCriterion, ExtractionField,
    ExtractionRecord, FinalDecision, InclusionCriterion, Paper,
    PaperDatabaseLink, Project, QACriterion, QAScore, Reviewer,
    ReviewerDecision, SnowballingIteration, TaxonomyEntry,
)
from ..services.kappa_service import calculate_kappa

router = APIRouter(prefix="/projects", tags=["report"])

# ── Colours ───────────────────────────────────────────────────────────────────
_BLACK   = (0, 0, 0)
_DARK    = (51, 51, 51)
_GRAY    = (107, 114, 128)
_GRAY_LT = (156, 163, 175)
_GRAY_BG = (249, 250, 251)
_TH_BG   = (240, 240, 240)
_BORDER  = (209, 213, 219)
_WHITE   = (255, 255, 255)

_CW = 170.0  # content width mm (A4 - 20mm margins)

_DB_DISPLAY = {
    "acm": "ACM Digital Library", "dblp": "DBLP", "ieee": "IEEE Xplore",
    "scopus": "Elsevier Scopus", "springerlink": "SpringerLink",
    "wiley": "Wiley Online Library",
}
_DB_ALIASES = {
    "springer": "springerlink", "springer link": "springerlink", "springerlink": "springerlink",
    "ieee xplore": "ieee", "ieee explore": "ieee", "ieee": "ieee",
    "scopus": "scopus", "elsevier": "scopus", "elsevier scopus": "scopus",
    "acm": "acm", "acm digital library": "acm",
    "wiley": "wiley", "wiley online library": "wiley",
    "dblp": "dblp", "dblp library": "dblp",
}


def _s(v, maxlen=0):
    """Sanitise a value for fpdf2's latin-1-only text engine.
    Replaces common Unicode chars (curly quotes, em-dash, kappa, etc.) with
    ASCII equivalents, then force-encodes to latin-1 with replacement."""
    if v is None: return "-"
    t = (str(v).replace("\u2026","...").replace("\u2014","-").replace("\u2013","-")
         .replace("|",".").replace("\u00d7","x").replace("\u2019","'").replace("\u2018","'")
         .replace("\u201c",'"').replace("\u201d",'"').replace("\u03ba","k")
         .replace("\u2265",">=").replace("\u2264","<=")
         .encode("latin-1",errors="replace").decode("latin-1"))
    if maxlen and len(t)>maxlen: t=t[:maxlen-3]+"..."
    return t

def _norm_db(r): return _DB_ALIASES.get(r.lower().strip(), r.lower().strip())
def _db_name(c): return _DB_DISPLAY.get(c, c.replace("_"," ").title())


# ── Pure helpers for the four synthesis charts (R1.C2) ───────────────────────
# These mirror the TypeScript helpers in frontend/src/utils/charts.ts so the
# web charts and the PDF report stay in lock-step.

# Status palette in 0..255 RGB. Aligned with the design tokens
# (#8B1A1A exclude / #8B6914 uncertain / #2D6A4F include).
_BAND_RGB = {
    "low":    (139, 26, 26),
    "medium": (139, 105, 20),
    "high":   (45, 106, 79),
}
# Muted accent blue (#1E3A5F) — used for non-status bar charts.
_BAR_BLUE = (30, 58, 95)


def _band_for_bin(lower_pct: float, medium: float, high: float) -> str:
    """Pick a band for a bin using its lower edge — matches bandForBin() in TS."""
    if lower_pct >= high:   return "high"
    if lower_pct >= medium: return "medium"
    return "low"


def _band_for_pct(pct: float, medium: float, high: float) -> str:
    if pct >= high:   return "high"
    if pct >= medium: return "medium"
    return "low"


def compute_qa_bins(percentages, medium: float, high: float):
    """10 equal-width bins [0,10)…[90,100]; 100% clamps into the top bin.

    Each bin additionally records the per-band split (low/medium/high) so a bin
    straddling a threshold can be rendered as a stacked bar reflecting the
    actual classification of its papers.
    """
    bins = [{"lower": i*10, "upper": (i+1)*10, "count": 0,
             "low": 0, "medium": 0, "high": 0,
             "band": _band_for_bin(i*10, medium, high)} for i in range(10)]
    for pct in percentages:
        if pct is None: continue
        try: v = float(pct)
        except (TypeError, ValueError): continue
        if v != v: continue  # NaN
        v = max(0.0, min(100.0, v))
        idx = 9 if v == 100 else int(v // 10)
        band = _band_for_pct(v, medium, high)
        bins[idx]["count"] += 1
        bins[idx][band] += 1
    # Recompute the dominant-band annotation now that we know the split.
    for b in bins:
        if b["count"] == 0: continue
        b["band"] = max(("low", "medium", "high"), key=lambda k: (b[k], "lmh".index(k[0])))
    return bins


def compute_qa_stats(percentages):
    """{n, mean, median} over the supplied percentages."""
    vals = sorted(float(p) for p in percentages if p is not None)
    n = len(vals)
    if n == 0: return {"n": 0, "mean": 0.0, "median": 0.0}
    mean = sum(vals) / n
    if n % 2 == 1:
        median = vals[(n - 1) // 2]
    else:
        median = (vals[n // 2 - 1] + vals[n // 2]) / 2
    return {"n": n, "mean": mean, "median": median}


def aggregate_taxonomy(papers, taxonomy_key: str, schema_values):
    """Schema values always rendered (count=0 if unused); unseen extras appended."""
    counts: dict[str, int] = {v: 0 for v in schema_values}
    for p in papers:
        raw = p.get("values", {}).get(taxonomy_key) if isinstance(p, dict) else None
        if not raw: continue
        counts[raw] = counts.get(raw, 0) + 1
    total = len(papers)
    rows = [{"value": v, "count": c, "percentage": (c/total*100) if total > 0 else 0}
            for v, c in counts.items()]
    rows.sort(key=lambda r: (-r["count"], r["value"]))
    return rows


def aggregate_extraction_field(papers, field_name: str):
    """Count and sort distinct values for one extraction field across papers."""
    counts: dict[str, int] = {}
    for p in papers:
        raw = p.get("values", {}).get(field_name) if isinstance(p, dict) else None
        if raw is None or raw == "": continue
        counts[raw] = counts.get(raw, 0) + 1
    total = sum(counts.values())
    rows = [{"value": v, "count": c, "percentage": (c/total*100) if total > 0 else 0}
            for v, c in counts.items()]
    rows.sort(key=lambda r: (-r["count"], r["value"]))
    return rows


def pick_first_select_field(fields, taxonomy_keys):
    """First dropdown extraction field that isn't also a taxonomy dimension."""
    tax = set(taxonomy_keys)
    ordered = sorted(fields, key=lambda f: (getattr(f, "sort_order", 0), getattr(f, "id", 0)))
    for f in ordered:
        if getattr(f, "field_type", "") == "dropdown" and f.field_name not in tax:
            return f
    return None


# ── Venue type categorization + monochromatic scale (iteration 2) ───────────

# Default venue categories shown in every legend, even at count 0.
_VENUE_DEFAULT_CATS = ("Journal", "Conference", "Workshop", "Other")


def categorize_venue(entry_type: str | None, venue: str | None) -> str:
    """Mirror of the TS categorizeVenue() — keeps the web and PDF in lock-step."""
    e = (entry_type or "").lower().strip()
    v = (venue or "").lower()
    if e == "article":
        return "Journal"
    if e in ("inproceedings", "conference"):
        if "workshop" in v: return "Workshop"
        return "Conference"
    if e in ("incollection", "inbook"): return "Book chapter"
    if e == "techreport":               return "Technical report"
    if e in ("phdthesis", "mastersthesis"): return "Thesis"

    # Fallback: when entry_type absent (legacy imports), infer from venue name.
    # Order matters: workshop before conference, book chapter before journal.
    if e in ("", "misc", "unpublished"):
        if "workshop" in v: return "Workshop"
        if any(k in v for k in ("proceedings", "conference", "symposium",
                                 "colloquium", " meeting", "international conference",
                                 "lecture notes", " conf.", "int. conf",
                                 "intl. conf", " symposia")):
            return "Conference"
        import re
        if any(k in v for k in ("journal", "transactions", " letters", "magazine",
                                 "review", "quarterly", "annals",
                                 "practice and experience")) \
                or re.search(r'vol\.?\s*\d+.*issue\s*\d+', v):
            return "Journal"
        if any(k in v for k in ("thesis", "dissertation")): return "Thesis"
        if any(k in v for k in ("technical report", "techreport", "tech. rep")):
            return "Technical report"
        if any(k in v for k in ("book chapter", "chapter in", "in: ")):
            return "Book chapter"

        # Abbreviated venue lookup (ISSRE, VALUETOOLS, etc.)
        _CONF_ABBREVS = {
            'icse','fse','esec','issta','msr','saner','icsme','icsm','ease','esem',
            'scam','ssbse','csmr','wcre','icpc','icst','tap','cbi','promise',
            'issre','valuetools','mascots','qest','icpe','wosp','sipew',
            'dsn','srds','edcc','prdc','ladc','pldi','oopsla','ecoop','popl',
            'sosp','osdi','eurosys','atc','nsdi','sigcomm','infocom','icdcs',
            'kdd','sigmod','vldb','icde','icdm','aaai','ijcai','neurips',
            'nips','icml','iclr','cvpr','iccv','eccv','acl','emnlp','naacl',
            'coling','chi','cscw','uist','ccs','ndss','www','sigir','cikm',
        }
        _JOUR_ABBREVS = {
            'tse','jss','tosem','emse','ist','scp','stvr','rej','cacm',
            'toit','tods','tois','toplas','tocs','jacm','tdsc','tpds','tetc',
            'tc','spej','spe','sosym','infsof',
        }
        abbrev = re.sub(r'[^a-z0-9]', '', v)
        if abbrev in _CONF_ABBREVS: return "Conference"
        if abbrev in _JOUR_ABBREVS: return "Journal"

    return "Other"


def aggregate_venue_types(papers):
    """{value, count, percentage}-rows by category. Default 4 always present."""
    counts: dict[str, int] = {c: 0 for c in _VENUE_DEFAULT_CATS}
    for p in papers:
        cat = categorize_venue(getattr(p, "entry_type", None), getattr(p, "venue", None))
        counts[cat] = counts.get(cat, 0) + 1
    total = len(papers)
    out = []
    for cat in _VENUE_DEFAULT_CATS:
        c = counts.get(cat, 0)
        out.append({"value": cat, "count": c, "percentage": (c/total*100) if total > 0 else 0.0})
    # Extras (non-default categories that received counts), sorted desc.
    extras = [(k, v) for k, v in counts.items() if k not in _VENUE_DEFAULT_CATS and v > 0]
    extras.sort(key=lambda kv: (-kv[1], kv[0]))
    for k, v in extras:
        out.append({"value": k, "count": v, "percentage": (v/total*100) if total > 0 else 0.0})
    return out


def _hsl_to_rgb(h: float, s: float, l: float):
    """HSL (deg/%/%) → 0..255 RGB triple, mirrors the TS scale.ts implementation."""
    s, l = s / 100.0, l / 100.0
    c = (1 - abs(2 * l - 1)) * s
    hp = ((h % 360) + 360) % 360 / 60
    x = c * (1 - abs((hp % 2) - 1))
    if   hp < 1: r1, g1, b1 = c, x, 0
    elif hp < 2: r1, g1, b1 = x, c, 0
    elif hp < 3: r1, g1, b1 = 0, c, x
    elif hp < 4: r1, g1, b1 = 0, x, c
    elif hp < 5: r1, g1, b1 = x, 0, c
    else:        r1, g1, b1 = c, 0, x
    m = l - c / 2
    return (int(round((r1 + m) * 255)),
            int(round((g1 + m) * 255)),
            int(round((b1 + m) * 255)))


def _hex(rgb):
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


# Accent #1E3A5F in HSL: roughly (213.5°, 52.0%, 24.7%). Use the same hue+sat
# as the TS side and vary lightness from 22 % (darkest) to 70 % (lightest).
_ACCENT_HUE = 213.0
_ACCENT_SAT = 52.0
_SCALE_L_MIN = 22.0
_SCALE_L_MAX = 70.0


def monochromatic_scale(n: int) -> list[str]:
    """Same logic as frontend/components/charts/scale.ts generateMonochromaticScale."""
    if n <= 0: return []
    if n == 1: return [_hex(_hsl_to_rgb(_ACCENT_HUE, _ACCENT_SAT, _SCALE_L_MIN))]
    out = []
    for i in range(n):
        t = i / (n - 1)
        l = _SCALE_L_MIN + (_SCALE_L_MAX - _SCALE_L_MIN) * t
        out.append(_hex(_hsl_to_rgb(_ACCENT_HUE, _ACCENT_SAT, l)))
    return out


# ── Donut chart rendering (issue 5/6) ──────────────────────────────────────

def _donut_svg(rows, palette, total: int, unit: str = "papers", size: int = 200) -> bytes:
    """Build an SVG donut chart matching the web design (monochromatic).

    `rows` are {value, count, percentage} dicts; only count > 0 yield a slice,
    matching the front-end's "zero-counts in legend only" rule.
    """
    import math as _m
    cx, cy = size / 2, size / 2
    ro = size * 0.46
    ri = ro * 0.55
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
    ]
    if total <= 0:
        # Empty ring — uses neutral rule color.
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{(ro+ri)/2}" '
            f'fill="none" stroke="#E5E2DD" stroke-width="{ro - ri}"/>'
        )
    else:
        non_zero_rows = [row for row in rows if row["count"] > 0]
        single = len(non_zero_rows) == 1
        if single:
            # Full ring: SVG <path> arcs that sweep 360° collapse onto the
            # start point and crash fpdf2's parser. Emit two 180° outer arcs
            # plus two reversed inner arcs for a closed donut ring.
            color = palette[0]
            d = (f"M {cx + ro:.2f} {cy:.2f} "
                 f"A {ro:.2f} {ro:.2f} 0 1 1 {cx - ro:.2f} {cy:.2f} "
                 f"A {ro:.2f} {ro:.2f} 0 1 1 {cx + ro:.2f} {cy:.2f} "
                 f"M {cx + ri:.2f} {cy:.2f} "
                 f"A {ri:.2f} {ri:.2f} 0 1 0 {cx - ri:.2f} {cy:.2f} "
                 f"A {ri:.2f} {ri:.2f} 0 1 0 {cx + ri:.2f} {cy:.2f} Z")
            parts.append(
                f'<path d="{d}" fill="{color}" fill-rule="evenodd" '
                f'stroke="#FFFFFF" stroke-width="1"/>'
            )
        else:
            angle = -90.0
            for r, color in zip(non_zero_rows, palette):
                sweep = r["count"] / total * 360.0
                end = angle + sweep
                large = 1 if sweep > 180 else 0
                ar, er = _m.radians(angle), _m.radians(end)
                x1, y1 = cx + ro * _m.cos(ar), cy + ro * _m.sin(ar)
                x2, y2 = cx + ro * _m.cos(er), cy + ro * _m.sin(er)
                x3, y3 = cx + ri * _m.cos(er), cy + ri * _m.sin(er)
                x4, y4 = cx + ri * _m.cos(ar), cy + ri * _m.sin(ar)
                d = (f"M {x1:.2f} {y1:.2f} "
                     f"A {ro:.2f} {ro:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} "
                     f"L {x3:.2f} {y3:.2f} "
                     f"A {ri:.2f} {ri:.2f} 0 {large} 0 {x4:.2f} {y4:.2f} Z")
                parts.append(f'<path d="{d}" fill="{color}" stroke="#FFFFFF" stroke-width="1"/>')
                angle = end
    # Centred total + unit label.
    parts.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'font-family="Times" font-size="22" font-weight="500" fill="#2B2B2B">'
        f'{total}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
        f'font-family="Helvetica" font-size="8" fill="#888888" '
        f'letter-spacing="1.2">{unit.upper()}</text>'
    )
    parts.append('</svg>')
    return ''.join(parts).encode("utf-8")


def _draw_donut_chart(pdf, rows, *, label: str = "papers"):
    """Render the donut + legend block at the current pdf y-position."""
    import io as _io
    total = sum(r["count"] for r in rows)
    non_zero = [r for r in rows if r["count"] > 0]
    palette = monochromatic_scale(max(len(non_zero), 1))

    chart_h = 60.0
    donut_w = 55.0
    if pdf.get_y() + chart_h + 4 > pdf.page_break_trigger:
        pdf.add_page()
    chart_y = pdf.get_y() + 1

    svg = _donut_svg(rows, palette, total, unit=label)
    pdf.image(_io.BytesIO(svg), x=pdf.l_margin, y=chart_y, w=donut_w)

    # Legend column to the right of the donut.
    legend_x = pdf.l_margin + donut_w + 6
    legend_w = _CW - donut_w - 6
    row_h = 4.4
    pdf.set_font("Times", "", 8.5)
    color_map: dict[str, str] = {}
    for r, color in zip(non_zero, palette):
        color_map[r["value"]] = color

    cur_y = chart_y + 2
    for r in rows:
        if cur_y + row_h > pdf.page_break_trigger:
            pdf.add_page(); cur_y = pdf.get_y()
        is_zero = r["count"] == 0
        swatch_color = color_map.get(r["value"], "#E5E2DD")
        # swatch: filled 2.5 mm square
        rh, gh, bh = int(swatch_color[1:3], 16), int(swatch_color[3:5], 16), int(swatch_color[5:7], 16)
        pdf.set_fill_color(rh, gh, bh)
        pdf.rect(legend_x, cur_y + 0.7, 2.5, 2.5, "F")
        # name
        pdf.set_text_color(*(150, 150, 150) if is_zero else (51, 51, 51))
        pdf.set_xy(legend_x + 4, cur_y)
        name_w = legend_w - 28
        pdf.cell(name_w, row_h, _s(r["value"], 60))
        # count
        pdf.set_text_color(*(150, 150, 150) if is_zero else (43, 43, 43))
        pdf.set_xy(legend_x + 4 + name_w, cur_y)
        pdf.cell(10, row_h, f'{r["count"]:,}', align="R")
        # percentage
        pdf.set_text_color(*(150, 150, 150) if is_zero else (107, 114, 128))
        pdf.set_xy(legend_x + 14 + name_w, cur_y)
        pdf.cell(14, row_h, f'{r["percentage"]:.1f}%', align="R")
        cur_y += row_h

    pdf.set_text_color(*_BLACK); pdf.set_font("Times", "", 9)
    pdf.set_y(max(chart_y + chart_h, cur_y + 1))


# ── Chart rendering (fpdf2 native rects, no extra deps) ──────────────────────

def _draw_qa_distribution_chart(pdf, bins, t_medium, t_high):
    """10-bin QA score histogram with threshold annotation lines."""
    chart_x = pdf.l_margin
    chart_y = pdf.get_y() + 1
    chart_w = _CW
    chart_h = 52.0
    pad_l, pad_r, pad_t, pad_b = 9.0, 4.0, 4.0, 11.0
    inner_w = chart_w - pad_l - pad_r
    inner_h = chart_h - pad_t - pad_b
    n_bins = len(bins)
    bar_gap = 0.6
    bar_w = (inner_w - bar_gap * (n_bins - 1)) / n_bins
    max_count = max((b["count"] for b in bins), default=0)
    tick_step = max(1, -(-max(max_count, 1) // 4))
    y_max = tick_step * 4

    if pdf.get_y() + chart_h + 4 > pdf.page_break_trigger:
        pdf.add_page()
        chart_y = pdf.get_y() + 1

    base_y = chart_y + pad_t + inner_h

    pdf.set_draw_color(*_BORDER); pdf.set_line_width(0.15)
    pdf.set_font("Times", "", 6); pdf.set_text_color(*_GRAY)
    for tick in (0, tick_step, tick_step * 2, tick_step * 3, y_max):
        ty = base_y - (tick / y_max) * inner_h
        pdf.line(chart_x + pad_l, ty, chart_x + pad_l + inner_w, ty)
        pdf.set_xy(chart_x, ty - 1.4)
        pdf.cell(pad_l - 1, 2.5, str(tick), align="R")

    # Stacked-bar fill: render one rectangle per band that has count > 0 in
    # this bin, stacked low → medium → high from the baseline upward.
    for i, b in enumerate(bins):
        if b["count"] <= 0: continue
        bx = chart_x + pad_l + i * (bar_w + bar_gap)
        cursor_y = base_y
        for band in ("low", "medium", "high"):
            seg = b[band]
            if seg <= 0: continue
            seg_h = (seg / y_max) * inner_h
            pdf.set_fill_color(*_BAND_RGB[band])
            pdf.rect(bx, cursor_y - seg_h, bar_w, seg_h, "F")
            cursor_y -= seg_h

    pdf.set_draw_color(85, 85, 85); pdf.set_line_width(0.15)
    pdf.set_dash_pattern(dash=0.8, gap=0.8)
    for t_pct in (t_medium, t_high):
        tx = chart_x + pad_l + (t_pct / 100.0) * inner_w
        pdf.line(tx, chart_y + pad_t, tx, base_y)
    pdf.set_dash_pattern()
    pdf.set_text_color(85, 85, 85); pdf.set_font("Times", "", 6)
    for t_pct, label in ((t_medium, f"Medium >= {int(t_medium)}%"),
                         (t_high,   f"High >= {int(t_high)}%")):
        tx = chart_x + pad_l + (t_pct / 100.0) * inner_w
        pdf.set_xy(min(tx + 0.5, chart_x + pad_l + inner_w - 20), chart_y + pad_t)
        pdf.cell(20, 2.5, label)

    pdf.set_font("Times", "", 6); pdf.set_text_color(*_GRAY)
    for i, b in enumerate(bins):
        bx = chart_x + pad_l + i * (bar_w + bar_gap)
        pdf.set_xy(bx, base_y + 0.8)
        pdf.cell(bar_w, 2.5, str(b["lower"]), align="C")
    pdf.set_xy(chart_x + pad_l + inner_w - 6, base_y + 0.8)
    pdf.cell(6, 2.5, "100", align="R")

    legend_y = chart_y + chart_h - 3
    legend_x = chart_x + pad_l
    for band, label in (("low", "Low"), ("medium", "Medium"), ("high", "High")):
        pdf.set_fill_color(*_BAND_RGB[band])
        pdf.rect(legend_x, legend_y, 2, 2, "F")
        pdf.set_text_color(*_GRAY); pdf.set_font("Times", "", 6)
        pdf.set_xy(legend_x + 2.5, legend_y - 0.4)
        pdf.cell(20, 3, label)
        legend_x += 18

    pdf.set_draw_color(*_BLACK); pdf.set_text_color(*_BLACK); pdf.set_line_width(0.2)
    pdf.set_y(chart_y + chart_h + 1)


def _draw_taxonomy_bars(pdf, rows, title):
    """Compact horizontal bar list — one category per row, count + percentage."""
    if not rows: return
    pdf.set_font("Times", "B", 7.5); pdf.set_text_color(*_DARK)
    pdf.cell(0, 4, _s(title), ln=True)
    pdf.set_text_color(*_BLACK)
    max_count = max((r["count"] for r in rows), default=1) or 1
    label_w = 36
    value_w = 18
    bar_max_w = _CW - label_w - value_w - 4
    pdf.set_font("Times", "", 7.5)
    for r in rows:
        y0 = pdf.get_y()
        if y0 + 5 > pdf.page_break_trigger: pdf.add_page(); y0 = pdf.get_y()
        pdf.set_xy(pdf.l_margin, y0)
        pdf.set_text_color(*_DARK)
        pdf.cell(label_w, 3.6, _s(r["value"], 32))
        bx = pdf.l_margin + label_w
        bw = bar_max_w * (r["count"] / max_count)
        pdf.set_fill_color(*_BORDER)
        pdf.rect(bx, y0 + 0.4, bar_max_w, 2.8, "F")
        if r["count"] > 0:
            pdf.set_fill_color(*_BAR_BLUE)
            pdf.rect(bx, y0 + 0.4, bw, 2.8, "F")
        pdf.set_xy(bx + bar_max_w + 2, y0)
        pdf.set_text_color(*_BLACK); pdf.set_font("Times", "B", 7.5)
        pdf.cell(8, 3.6, str(r["count"]))
        pdf.set_text_color(*_GRAY); pdf.set_font("Times", "", 7)
        pdf.cell(10, 3.6, f"({r['percentage']:.0f}%)")
        pdf.ln(4)
    pdf.set_text_color(*_BLACK); pdf.set_font("Times", "", 9)
    pdf.ln(1)


def _draw_extraction_field_chart(pdf, rows):
    """Vertical bar chart of distinct values for one extraction field."""
    if not rows: return
    chart_x = pdf.l_margin
    chart_y = pdf.get_y() + 1
    chart_w = _CW
    chart_h = 50.0
    pad_l, pad_r, pad_t, pad_b = 9.0, 4.0, 4.0, 18.0
    inner_w = chart_w - pad_l - pad_r
    inner_h = chart_h - pad_t - pad_b
    n = len(rows)
    bar_gap = 1.5
    bar_w = (inner_w - bar_gap * (n - 1)) / max(n, 1)
    max_count = max((r["count"] for r in rows), default=1) or 1
    tick_step = max(1, -(-max_count // 4))
    y_max = tick_step * 4

    if pdf.get_y() + chart_h + 4 > pdf.page_break_trigger:
        pdf.add_page()
        chart_y = pdf.get_y() + 1

    base_y = chart_y + pad_t + inner_h
    pdf.set_draw_color(*_BORDER); pdf.set_line_width(0.15)
    pdf.set_font("Times", "", 6); pdf.set_text_color(*_GRAY)
    for tick in (0, tick_step, tick_step * 2, tick_step * 3, y_max):
        ty = base_y - (tick / y_max) * inner_h
        pdf.line(chart_x + pad_l, ty, chart_x + pad_l + inner_w, ty)
        pdf.set_xy(chart_x, ty - 1.4)
        pdf.cell(pad_l - 1, 2.5, str(tick), align="R")

    pdf.set_fill_color(*_BAR_BLUE)
    for i, r in enumerate(rows):
        bx = chart_x + pad_l + i * (bar_w + bar_gap)
        bh = (r["count"] / y_max) * inner_h
        by = base_y - bh
        pdf.rect(bx, by, bar_w, bh, "F")

    pdf.set_font("Times", "", 6); pdf.set_text_color(*_GRAY)
    for i, r in enumerate(rows):
        bx = chart_x + pad_l + i * (bar_w + bar_gap)
        with pdf.rotation(angle=35, x=bx + bar_w / 2, y=base_y + 1.5):
            pdf.set_xy(bx + bar_w / 2 - 18, base_y + 1.5)
            pdf.cell(18, 2.5, _s(r["value"], 22), align="R")

    pdf.set_draw_color(*_BLACK); pdf.set_text_color(*_BLACK); pdf.set_line_width(0.2)
    pdf.set_y(chart_y + chart_h + 1)


# ─────────────────────────────────────────────────────────────────────────────
class _Report(FPDF):
    """Times-Roman based A4 report with auto-wrapping tables."""

    def __init__(self, title):
        super().__init__("P","mm","A4")
        self.slr_title = _s(title, 80)
        self.set_margins(20,20,20)
        self.set_auto_page_break(True, margin=22)
        self._is_cover = True

    def header(self):
        if self._is_cover: return
        self.set_font("Times","I",7); self.set_text_color(*_GRAY_LT)
        self.cell(0,5,self.slr_title,align="L")
        self.cell(0,5,f"Page {self.page_no()}",align="R")
        self.ln(5)
        self.set_draw_color(*_BORDER); self.set_line_width(0.15)
        self.line(self.l_margin,self.get_y(),self.l_margin+_CW,self.get_y())
        self.ln(3); self.set_text_color(*_BLACK)

    def footer(self):
        if self._is_cover: return
        self.set_y(-12)
        self.set_draw_color(*_BORDER); self.set_line_width(0.15)
        self.line(self.l_margin,self.get_y(),self.l_margin+_CW,self.get_y())
        self.set_font("Times","",6.5); self.set_text_color(*_GRAY_LT)
        self.cell(0,8,f"Generated by ReviQ  .  {self.slr_title}  .  Page {self.page_no()}",align="C")
        self.set_text_color(*_BLACK)

    # ── Headings (4-level hierarchy) ─────────────────────────────────────────

    def section_sep(self):
        """~24pt spacer between sections (replaces forced page break)."""
        self.ln(8.5)

    def h2(self, text):
        """Level 1: Section heading — 13pt bold black, 18pt space before, black rule."""
        if self.get_y() + 25 > self.page_break_trigger: self.add_page()
        self.ln(6.5)  # ~18pt
        self.set_font("Times","B",13); self.set_text_color(*_BLACK)
        self.cell(0,7,_s(text),ln=True)
        y=self.get_y(); self.set_draw_color(*_BLACK); self.set_line_width(0.4)
        self.line(self.l_margin,y,self.l_margin+_CW,y)
        self.set_line_width(0.2); self.ln(2.5)

    def h3(self, text):
        """Level 2: Subsection — 11pt bold #333, 12pt space before, light gray underline."""
        if self.get_y() + 16 > self.page_break_trigger: self.add_page()
        self.ln(4.2)  # ~12pt
        self.set_font("Times","B",11); self.set_text_color(*_DARK)
        self.cell(0,5.5,_s(text),ln=True)
        y=self.get_y(); self.set_draw_color(*_GRAY_LT); self.set_line_width(0.18)
        self.line(self.l_margin,y,self.l_margin+_CW,y)
        self.set_draw_color(*_BLACK); self.set_line_width(0.2)
        self.ln(1.5); self.set_text_color(*_BLACK)

    def h4(self, text):
        """Level 3: Field label — 10pt bold #444, 8pt space before."""
        if self.get_y() + 10 > self.page_break_trigger: self.add_page()
        self.ln(2.8)  # ~8pt
        self.set_font("Times","B",10); self.set_text_color(68,68,68)  # #444
        self.cell(0,4.5,_s(text),ln=True)
        self.set_text_color(*_BLACK)

    def body(self, text):
        """Body text — 9pt regular #333."""
        self.set_x(self.l_margin); self.set_font("Times","",9); self.set_text_color(*_DARK)
        self.multi_cell(_CW,4.5,_s(text)); self.set_text_color(*_BLACK); self.ln(1)

    def note(self, text):
        self.set_x(self.l_margin); self.set_font("Times","I",8); self.set_text_color(*_DARK)
        self.multi_cell(_CW,4,_s(text,600)); self.set_text_color(*_BLACK); self.ln(1)

    def indent_text(self, text, indent=4):
        """Regular-weight indented text — 9pt #333."""
        self.set_x(self.l_margin + indent)
        self.set_font("Times","",9); self.set_text_color(*_DARK)
        self.multi_cell(_CW - indent, 4, _s(text))
        self.set_text_color(*_BLACK); self.ln(0.5)

    def _measure_mc(self, txt, w, font_name="Times", font_style="", font_size=8):
        """Estimate multi-cell height for text in given width."""
        self.set_font(font_name, font_style, font_size)
        line_h = font_size * 0.42
        words = _s(str(txt)).split(" ")
        lines = 1; cur_w = 0
        for word in words:
            ww = self.get_string_width(word + " ")
            if cur_w + ww > w and cur_w > 0: lines += 1; cur_w = ww
            else: cur_w += ww
        return max(lines * line_h, line_h)

    # ── Wrapping table ────────────────────────────────────────────────────────

    def _text_height(self, txt, w, font_name="Times", font_style="", font_size=8):
        """Estimate multi-cell height for text in given width."""
        self.set_font(font_name, font_style, font_size)
        # Use get_string_width to calculate lines needed
        words = _s(txt).split(" ")
        line_h = font_size * 0.45  # approx mm per line
        lines = 1; line_w = 0
        for word in words:
            word_w = self.get_string_width(word + " ")
            if line_w + word_w > w and line_w > 0:
                lines += 1; line_w = word_w
            else:
                line_w += word_w
        return max(lines * line_h, line_h)

    def wrapping_table(self, cols, rows):
        """Table with auto-wrapping cells. cols=[(label, frac), ...], rows=[[str,...],...]"""
        abs_cols = [(_s(label), _CW * frac) for label, frac in cols]
        line_h = 4.0

        # Header
        if self.get_y() + 12 > self.page_break_trigger: self.add_page()
        self.set_font("Times","B",7.5); self.set_fill_color(*_TH_BG)
        self.set_text_color(*_BLACK); self.set_draw_color(*_BORDER)
        for label, w in abs_cols:
            self.cell(w, 5.5, label, border=1, fill=True)
        self.ln(); self.set_fill_color(*_WHITE)

        # Rows
        for ri, row in enumerate(rows):
            # Calculate row height
            max_h = line_h
            for ci, (_, w) in enumerate(abs_cols):
                cell_text = _s(str(row[ci]) if ci < len(row) else "")
                h = self._text_height(cell_text, w - 2)
                if h > max_h: max_h = h
            row_h = max(max_h + 2, line_h + 1)

            if self.get_y() + row_h > self.page_break_trigger: self.add_page()

            fill = ri % 2 == 1
            self.set_fill_color(*(_GRAY_BG if fill else _WHITE))
            self.set_draw_color(*_BORDER)
            x0 = self.get_x(); y0 = self.get_y()

            # Draw cell backgrounds and borders
            for _, w in abs_cols:
                self.rect(self.get_x(), y0, w, row_h, "FD" if fill else "D")
                self.set_x(self.get_x() + w)

            # Render text
            for ci, (_, w) in enumerate(abs_cols):
                cell_text = _s(str(row[ci]) if ci < len(row) else "")
                x = x0 + sum(ww for _, ww in abs_cols[:ci])
                self.set_xy(x + 1, y0 + 0.5)
                self.set_font("Times", "B" if ci == 0 else "", 7.5)
                self.set_text_color(*_BLACK)
                self.multi_cell(w - 2, line_h, cell_text)

            self.set_xy(x0, y0 + row_h)
        self.set_fill_color(*_WHITE); self.ln(2)

    def kv_table(self, rows, label_frac=0.50):
        lw = _CW * label_frac; vw = _CW * (1 - label_frac)
        for i, (label, value) in enumerate(rows):
            # Calculate height
            lh = self._text_height(label, lw - 2)
            vh = self._text_height(value, vw - 2, font_style="B")
            row_h = max(lh + 2, vh + 2, 5.0)

            if self.get_y() + row_h > self.page_break_trigger: self.add_page()

            fill = i % 2 == 1
            self.set_fill_color(*(_GRAY_BG if fill else _WHITE))
            self.set_draw_color(*_BORDER)
            x0 = self.get_x(); y0 = self.get_y()

            self.rect(x0, y0, lw, row_h, "FD" if fill else "D")
            self.rect(x0 + lw, y0, vw, row_h, "FD" if fill else "D")

            self.set_xy(x0 + 1, y0 + 0.5)
            self.set_font("Times","",8); self.set_text_color(*_BLACK)
            self.multi_cell(lw - 2, 4, _s(label))

            self.set_xy(x0 + lw + 1, y0 + 0.5)
            self.set_font("Times","B",8)
            self.multi_cell(vw - 2, 4, _s(value))

            self.set_xy(x0, y0 + row_h)
        self.set_fill_color(*_WHITE); self.ln(2)


class ReportBody(BaseModel):
    prisma_svg:                Optional[str] = None
    quality_distribution_svg:  Optional[str] = None
    publications_year_svg:     Optional[str] = None
    research_type_svg:         Optional[str] = None
    contribution_type_svg:     Optional[str] = None
    venue_types_svg:           Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────

def _merge_prisma_pdf(main_pdf_bytes: bytes, prisma_svg: str, insert_after_page: int) -> bytes:
    """Convert SVG to a vector PDF page via svglib/reportlab and merge it into the main PDF."""
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return main_pdf_bytes  # dependencies not available, skip

    # Render SVG to vector PDF
    drawing = svg2rlg(io.BytesIO(prisma_svg.encode("utf-8")))
    if drawing is None:
        return main_pdf_bytes

    # Scale drawing to fit A4 width (170mm ≈ 482pt, at 72 dpi = 482pt)
    target_w = 482.0
    scale = target_w / drawing.width if drawing.width > 0 else 1.0
    drawing.width = target_w
    drawing.height = drawing.height * scale
    drawing.scale(scale, scale)

    prisma_pdf_bytes = renderPDF.drawToString(drawing)

    # Merge
    writer = PdfWriter()
    main_reader = PdfReader(io.BytesIO(main_pdf_bytes))
    prisma_reader = PdfReader(io.BytesIO(prisma_pdf_bytes))

    for i, page in enumerate(main_reader.pages):
        writer.add_page(page)
        if i == insert_after_page - 1 and prisma_reader.pages:
            writer.add_page(prisma_reader.pages[0])

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


import re as _re


def _preprocess_svg_for_rlg(svg_string: str) -> str:
    """Make an SVG string svglib-compatible.

    Two issues addressed:
    1. CSS ``style="width:100%;height:auto"`` on the root <svg> overrides the
       explicit width/height attributes that svglib relies on for sizing.
       Strip the style attribute from the root element only.
    2. Negative viewBox (e.g. "-115.6 -115.6 451.2 451.2") from donut charts —
       svglib may not correctly map content at negative user coordinates.
       Normalize the viewBox to (0,0,w,h) and wrap content in a translate group.
    """
    # 1. Remove inline style from root <svg> element
    svg_string = _re.sub(
        r'(<svg\b[^>]*?)\s+style="[^"]*"',
        r'\1',
        svg_string, count=1,
    )

    # 2. Normalize negative viewBox
    m = _re.search(
        r'viewBox="(-?[\d.]+)\s+(-?[\d.]+)\s+([\d.]+)\s+([\d.]+)"',
        svg_string,
    )
    if m:
        vbx, vby = float(m.group(1)), float(m.group(2))
        vbw, vbh  = float(m.group(3)), float(m.group(4))
        if vbx != 0.0 or vby != 0.0:
            # Replace viewBox so origin is (0,0)
            svg_string = (
                svg_string[:m.start()]
                + f'viewBox="0 0 {vbw} {vbh}"'
                + svg_string[m.end():]
            )
            # Wrap all SVG content in a translate that undoes the offset
            open_end = svg_string.index('>', svg_string.index('<svg')) + 1
            close_start = svg_string.rfind('</svg>')
            if close_start > open_end:
                tx, ty = -vbx, -vby
                svg_string = (
                    svg_string[:open_end]
                    + f'<g transform="translate({tx:.3f},{ty:.3f})">'
                    + svg_string[open_end:close_start]
                    + '</g></svg>'
                )
    return svg_string


def _svg_to_drawing(svg_string: str, max_width: float, max_height: float = None):
    """Convert an SVG string to a scaled ReportLab Drawing. Returns None on any failure."""
    try:
        from svglib.svglib import svg2rlg
    except ImportError:
        return None
    try:
        cleaned = _preprocess_svg_for_rlg(svg_string)
        drawing = svg2rlg(io.BytesIO(cleaned.encode('utf-8')))
    except Exception:
        return None
    if drawing is None or drawing.width == 0:
        return None
    try:
        scale = max_width / drawing.width
        if max_height and drawing.height > 0:
            scale = min(scale, max_height / drawing.height)
        drawing.width  *= scale
        drawing.height *= scale
        drawing.transform = (scale, 0, 0, scale, 0, 0)
        return drawing
    except Exception:
        return None


def _insert_chart_pages(main_bytes: bytes, insertions: list) -> bytes:
    """Insert chart SVG pages into the main PDF after specified page numbers.

    insertions: list of (after_page_1indexed, svg_string, max_width, caption).
    Each chart gets a tightly-sized page (no full-A4 blank space).
    Silently skips any entry where the SVG is missing or fails to render.
    """
    if not insertions:
        return main_bytes
    try:
        from reportlab.graphics import renderPDF
        from reportlab.pdfgen.canvas import Canvas
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return main_bytes

    ins_map: dict = {}
    for after_page, svg_str, max_width, caption in sorted(insertions, key=lambda x: x[0]):
        if not svg_str:
            continue
        try:
            drawing = _svg_to_drawing(svg_str, float(max_width))
            if drawing is None:
                continue

            # Tight page: sized to the chart so there is no blank space below
            margin_h = 28   # left/right margin in pts
            margin_v = 36   # top/bottom margin + caption row
            page_w = drawing.width  + margin_h * 2
            page_h = drawing.height + margin_v + (16 if caption else 0)

            chart_buf = io.BytesIO()
            c = Canvas(chart_buf, pagesize=(page_w, page_h))
            renderPDF.draw(drawing, c, margin_h, 16 if caption else 8)
            if caption:
                c.setFont("Times-Italic", 9)
                c.drawCentredString(page_w / 2, 5, caption)
            c.save()
            ins_map.setdefault(after_page, []).append(chart_buf.getvalue())
        except Exception:
            continue   # never let a single bad SVG crash the whole PDF

    if not ins_map:
        return main_bytes

    reader = PdfReader(io.BytesIO(main_bytes))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        writer.add_page(page)
        for cb in ins_map.get(i + 1, []):
            cr = PdfReader(io.BytesIO(cb))
            for cp in cr.pages:
                writer.add_page(cp)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _build_section10_pdf(
    included_pap, avg_qa, project, all_fns, fl, rec_map, section_num, slr_title,
):
    """Build Section 10 (Included Papers) as a standalone ReportLab PDF.

    Uses Platypus instead of fpdf2 here because we need text wrapping in table
    cells. Each paper is a KeepTogether block (title + citation table + extraction
    table). Result gets appended to the main PDF via pypdf.
    """
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=22*mm,
    )
    avail_w = doc.width  # ~170mm in points

    # Styles
    s_title = ParagraphStyle("PaperTitle", fontName="Times-Bold", fontSize=9,
                             leading=12, textColor=rl_colors.black, spaceAfter=2,
                             leftIndent=0, rightIndent=0)
    s_label = ParagraphStyle("Label", fontName="Times-Bold", fontSize=8,
                             leading=10, textColor=rl_colors.black)
    s_value = ParagraphStyle("Value", fontName="Times-Roman", fontSize=8,
                             leading=10, textColor=rl_colors.Color(0.2, 0.2, 0.2))
    s_heading = ParagraphStyle("SectionHeading", fontName="Times-Bold", fontSize=13,
                               leading=16, textColor=rl_colors.black, spaceAfter=4, spaceBefore=6)
    s_note = ParagraphStyle("Note", fontName="Times-Italic", fontSize=8,
                            leading=10, textColor=rl_colors.Color(0.2, 0.2, 0.2), spaceAfter=8)
    s_footer = ParagraphStyle("Footer", fontName="Times-Roman", fontSize=6.5,
                              leading=8, textColor=rl_colors.Color(0.6, 0.6, 0.6),
                              alignment=1)  # centered

    # Build header/footer for these pages
    title_safe = _s(slr_title, 80)

    def _on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Italic", 7)
        canvas.setFillColor(rl_colors.Color(0.6, 0.6, 0.6))
        canvas.drawString(20*mm, A4[1] - 14*mm, title_safe)
        canvas.drawRightString(A4[0] - 20*mm, A4[1] - 14*mm, f"Page {doc.page}")
        canvas.setStrokeColor(rl_colors.Color(0.82, 0.84, 0.86))
        canvas.setLineWidth(0.15*mm)
        canvas.line(20*mm, A4[1] - 15*mm, A4[0] - 20*mm, A4[1] - 15*mm)
        # Footer
        canvas.line(20*mm, 16*mm, A4[0] - 20*mm, 16*mm)
        canvas.setFont("Times-Roman", 6.5)
        canvas.drawCentredString(A4[0]/2, 10*mm,
            f"Generated by ReviQ  .  {title_safe}  .  Page {doc.page}")
        canvas.restoreState()

    story = []

    # Section heading
    story.append(Paragraph(
        f"{section_num}. Included Papers ({len(included_pap)})", s_heading))
    story.append(HRFlowable(width="100%", thickness=0.4*mm,
                             color=rl_colors.black, spaceAfter=3*mm))
    story.append(Paragraph(
        "Full bibliographic details are available in the BibTeX file in the replication package.",
        s_note))

    cit_col_w = [avail_w * 0.20, avail_w * 0.80]
    ext_col_w = [avail_w * 0.35, avail_w * 0.65]

    base_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ])

    sorted_inc = sorted(included_pap, key=lambda p: (p.year or 0, p.authors or ""))
    for i, p in enumerate(sorted_inc):
        block = []

        # Paper title
        block.append(Paragraph(
            f"<b>[{_s(p.citekey)}]</b> — {_s(p.title)}", s_title))

        # Citation table
        cit_data = []
        for label, val in [("Authors", p.authors), ("Venue", p.venue),
                           ("Year", p.year), ("DOI", getattr(p, 'doi', None))]:
            if not val: continue
            cit_data.append([
                Paragraph(f"<b>{_s(label)}:</b>", s_label),
                Paragraph(_s(str(val)), s_value),
            ])
        qa_pct = avg_qa.get(p.id)
        if qa_pct is not None:
            lvl = ("High" if qa_pct >= project.qa_high_threshold
                   else "Medium" if qa_pct >= project.qa_medium_threshold else "Low")
            cit_data.append([
                Paragraph("<b>Overall Quality Score:</b>", s_label),
                Paragraph(f"{qa_pct:.0f}% ({lvl})", s_value),
            ])
        if cit_data:
            ct = Table(cit_data, colWidths=cit_col_w, hAlign='LEFT')
            ct.setStyle(base_style)
            block.append(ct)

        # Thin separator
        block.append(Spacer(1, 2*mm))
        block.append(HRFlowable(width="90%", thickness=0.15*mm,
                                color=rl_colors.Color(0.82, 0.84, 0.86),
                                spaceAfter=2*mm))

        # Extraction fields table
        vals = rec_map.get(p.id, {})
        ext_data = []
        for fn in all_fns:
            val = vals.get(fn, "")
            if not val: continue
            label = fl.get(fn, fn)
            ext_data.append([
                Paragraph(f"<b>{_s(label)}:</b>", s_label),
                Paragraph(_s(str(val)), s_value),
            ])
        if ext_data:
            et = Table(ext_data, colWidths=ext_col_w, hAlign='LEFT')
            et.setStyle(base_style)
            block.append(et)

        # Wrap entire paper block in KeepTogether to avoid mid-block page splits
        # (platypus will break to next page if block doesn't fit)
        story.append(KeepTogether(block))

        # Spacer + heavy rule between papers
        if i < len(sorted_inc) - 1:
            story.append(Spacer(1, 3*mm))
            story.append(HRFlowable(width="100%", thickness=0.3*mm,
                                    color=rl_colors.Color(0.82, 0.84, 0.86),
                                    spaceAfter=3*mm))

    # End note
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.3*mm,
                            color=rl_colors.Color(0.82, 0.84, 0.86), spaceAfter=3*mm))
    # no trailing footer — report ends after the last paper

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


def _build_pdf(
    project, reviewers, inc_criteria, exc_criteria, qa_criteria,
    search_strings, papers, rev_decisions, final_decisions,
    conflict_log, qa_scores, ext_fields, ext_records,
    snow_iterations, taxonomy, now,
    db_links=None, prisma_svg=None,
    quality_distribution_svg=None, publications_year_svg=None,
    research_type_svg=None, contribution_type_svg=None, venue_types_svg=None,
):
    # ── Stats ────────────────────────────────────────────────────────────────
    # Partition papers by origin: database searches vs. snowballing iterations.
    # Snowballing papers have source "snowballing:<iteration_number>".
    db_papers   = [p for p in papers if not p.source.startswith("snowballing:")]
    snow_papers = [p for p in papers if p.source.startswith("snowballing:")]
    dupes       = sum(1 for p in db_papers if p.dedup_status.startswith("duplicate_of:"))
    after_dedup = len(db_papers) - dupes
    scr_inc_ids = {d.paper_id for d in final_decisions if d.phase=="screening" and d.decision=="I"}
    scr_exc_ids = {d.paper_id for d in final_decisions if d.phase=="screening" and d.decision=="E"}
    ft_inc_ids  = {d.paper_id for d in final_decisions if d.phase=="full-text" and d.decision=="I"}
    ft_exc_ids  = {d.paper_id for d in final_decisions if d.phase=="full-text" and d.decision=="E"}
    snow_ids     = {p.id for p in snow_papers}
    snow_inc_ids = {d.paper_id for d in final_decisions if d.decision=="I" and d.paper_id in snow_ids}
    # "Included" = full-text included from DB searches + included from snowballing
    included_ids = ft_inc_ids | snow_inc_ids
    included_pap = [p for p in papers if p.id in included_ids]

    # QA percentage per paper: sum of raw scores / max possible score * 100
    by_paper: dict[int, list] = defaultdict(list)
    for s in qa_scores: by_paper[s.paper_id].append(s)
    max_qa = sum(c.max_score for c in qa_criteria) or 1.0
    avg_qa = {pid: sum(sc.score for sc in scores if sc.score is not None)/max_qa*100 for pid,scores in by_paper.items()}

    scr_conf_res = sum(1 for c in conflict_log if c.phase=="screening" and c.resolved)
    scr_conf_opn = sum(1 for c in conflict_log if c.phase=="screening" and not c.resolved)
    ft_conf_res  = sum(1 for c in conflict_log if c.phase=="full-text" and c.resolved)
    ft_conf_opn  = sum(1 for c in conflict_log if c.phase=="full-text" and not c.resolved)
    res_disc = sum(1 for c in conflict_log if c.resolution_method=="discussion")
    res_arb  = sum(1 for c in conflict_log if c.resolution_method=="arbitration")

    # Cohen's kappa for first two reviewers (R1 vs R2) in each phase
    kappa_results = {}
    if len(reviewers) >= 2:
        for phase in ("screening","full-text"):
            r1,r2 = reviewers[0],reviewers[1]
            r1d = {str(d.paper_id):d.decision for d in rev_decisions if d.reviewer_id==r1.id and d.phase==phase}
            r2d = {str(d.paper_id):d.decision for d in rev_decisions if d.reviewer_id==r2.id and d.phase==phase}
            kr = calculate_kappa(r1d, r2d)
            if kr: kappa_results[phase] = {"result":kr, "r1_name":r1.name, "r2_name":r2.name}

    # Per-database search metrics (precision/recall/F1).
    # Precision = included_from_DB / total_results_from_DB (how selective was this DB?)
    # Recall    = included_from_DB / total_included        (what fraction did this DB contribute?)
    # When PaperDatabaseLink rows exist, a paper can be credited to multiple DBs
    # (it was found in more than one search). Without links, only the primary source counts.
    search_metrics = []
    total_included = len(included_ids)
    use_links = db_links is not None and len(db_links) > 0
    link_map: dict[str, set] = {}
    if use_links:
        for lnk in db_links: link_map.setdefault(_norm_db(lnk.db_name), set()).add(lnk.paper_id)
    db_rc: dict[str, int|None] = {}
    for ss in search_strings:
        if ss.db_name:
            cn = _norm_db(ss.db_name)
            if cn not in db_rc: db_rc[cn] = ss.results_count
    for cn, rc in db_rc.items():
        paps = [p for p in db_papers if _norm_db(p.source)==cn and p.dedup_status=="original"]
        imp = len(paps)
        inc = len(link_map.get(cn,set())&included_ids) if use_links else sum(1 for p in paps if p.id in included_ids)
        ret = rc if rc is not None else imp
        pr = inc/ret if ret>0 else 0.0; re = inc/total_included if total_included>0 else 0.0
        f1 = (2*pr*re/(pr+re)) if (pr+re)>0 else 0.0
        search_metrics.append({"db":cn,"results":ret,"imported":imp,"included":inc,"precision":pr,"recall":re,"f1":f1})
    search_metrics.sort(key=lambda x: x["db"])

    rec_map: dict[int, dict[str,str]] = defaultdict(dict)
    for r in ext_records: rec_map[r.paper_id][r.field_name] = r.field_value or ""
    tax_types = sorted({t.taxonomy_type for t in taxonomy}) if taxonomy else []
    non_tax_fields = [f for f in sorted(ext_fields, key=lambda x: x.sort_order) if f.field_name not in set(tax_types)]
    all_fns = []; seen_fn = set()
    for fn in tax_types + [f.field_name for f in non_tax_fields]:
        if fn not in seen_fn: seen_fn.add(fn); all_fns.append(fn)
    fl = {t: t.replace("_"," ").title() for t in tax_types}
    fl.update({f.field_name: f.field_label for f in ext_fields})

    # ── Synthesis chart inputs (Reviewer R1, Comment R1.C2) ──────────────────
    # Build the dict-shaped paper records expected by aggregate_*() helpers.
    extraction_paper_records = [
        {"paper_id": pid, "values": rec_map.get(pid, {})}
        for pid in included_ids
    ]
    # Taxonomy schema: every taxonomy_type in the order it appears in setup —
    # one donut per dimension, matching iteration-2 issue 5 on the web side.
    tax_types_ordered = list(dict.fromkeys(
        t.taxonomy_type for t in sorted(taxonomy or [], key=lambda x: (x.sort_order, x.id or 0))
    ))
    def _values_for(key):
        return [t.value for t in sorted(
            (e for e in (taxonomy or []) if e.taxonomy_type == key),
            key=lambda x: (x.sort_order, x.id or 0))]
    taxonomy_donuts = [
        (key, aggregate_taxonomy(extraction_paper_records, key, _values_for(key)))
        for key in tax_types_ordered
    ]
    extraction_field = pick_first_select_field(ext_fields or [], tax_types_ordered)
    extraction_rows = (
        aggregate_extraction_field(extraction_paper_records, extraction_field.field_name)
        if extraction_field else []
    )
    # Venue-type donut: categorize every included paper for the new
    # "Composition" section in the report (replaces the iteration-1 venue bars
    # — which never existed in the PDF but the web side did have one).
    included_papers = [p for p in papers if p.id in included_ids]
    venue_rows = aggregate_venue_types(included_papers)
    venue_top10: list[tuple[str, str, int]] = []
    if included_papers:
        venue_counts: dict[str, dict] = {}
        for p in included_papers:
            name = (p.venue or "").strip()
            if not name: continue
            cat = categorize_venue(p.entry_type, p.venue)
            slot = venue_counts.setdefault(name, {"count": 0, "category": cat})
            slot["count"] += 1
        venue_top10 = sorted(
            ((name, info["category"], info["count"]) for name, info in venue_counts.items()),
            key=lambda t: (-t[2], t[0]),
        )[:10]

    # QA inputs: percentages for papers that completed the QA pass.
    qa_percentages_included = [pct for pid, pct in avg_qa.items() if pid in included_ids]
    qa_bins = compute_qa_bins(qa_percentages_included,
                              project.qa_medium_threshold, project.qa_high_threshold)
    qa_stats = compute_qa_stats(qa_percentages_included)

    fig_num = 0  # incremented as we emit each synthesis figure
    chart_insertions = []  # (after_page, svg_str, max_width, caption)

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = _Report(project.title)
    pdf.add_page()

    # ═══ COVER PAGE ══════════════════════════════════════════════════════════
    pdf.ln(55)
    pdf.set_font("Times","B",20); pdf.set_text_color(*_BLACK)
    pdf.multi_cell(_CW, 10, _s(project.title), align="C")
    pdf.ln(4)
    pdf.set_font("Times","",10); pdf.set_text_color(*_DARK)
    pdf.cell(0,5,"Supplementary Material: Search Protocol & Results",align="C",ln=True)
    pdf.ln(3)
    pdf.set_font("Times","",9)
    pdf.cell(0,4,now,align="C",ln=True)
    pdf.ln(3)
    # Horizontal rule
    pdf.set_draw_color(*_BORDER); pdf.set_line_width(0.2)
    pdf.line(70, pdf.get_y(), 140, pdf.get_y()); pdf.ln(3)
    # Reviewer count
    pdf.set_font("Times","",9); pdf.set_text_color(*_DARK)
    pdf.cell(0,4,f"{len(reviewers)} reviewer{'s' if len(reviewers)!=1 else ''}",align="C",ln=True)
    # Citation
    pdf.ln(2); pdf.set_font("Times","I",7); pdf.set_text_color(*_GRAY_LT)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(_CW, 3.5,
        "Generated with ReviQ. If you use ReviQ in your research, please cite: "
        "Haindl, Philipp (submitted). ReviQ: A Systematic Literature Review Workbench. SoftwareX.",
        align="C")
    pdf.set_text_color(*_BLACK)

    pdf._is_cover = False
    sn = 0   # section counter — increments only when a section is actually emitted
    prisma_insert_page = None

    # ═══ 1. RESEARCH PROTOCOL ═══════════════════════════════════════════════
    sn += 1; pdf.add_page()
    pdf.h2(f"{sn}. Research Protocol")
    if project.description:
        pdf.h3("Research Question / Scope"); pdf.body(project.description)
    def _ct(crit, title):
        if not crit: return
        pdf.h3(title)
        pdf.wrapping_table([("Label",0.10),("Phase",0.18),("Description",0.72)],
                           [[c.label, c.phase.replace("-"," ").title(), c.description] for c in crit])
    _ct(inc_criteria, "Inclusion Criteria"); _ct(exc_criteria, "Exclusion Criteria")
    if qa_criteria:
        pdf.h3("Quality Assessment Criteria")
        pdf.wrapping_table([("Label",0.12),("Description",0.70),("Max Score",0.18)],
                           [[c.label, c.description, c.max_score] for c in qa_criteria])
        pdf.note(f"Quality thresholds: High >= {project.qa_high_threshold}%, Medium >= {project.qa_medium_threshold}%")

    # ═══ 2. SEARCH STRATEGY ═════════════════════════════════════════════════
    sn += 1
    pdf.h2(f"{sn}. Search Strategy")
    if search_strings:
        for ss in search_strings:
            pdf.h3(f"Database: {_db_name(_norm_db(ss.db_name))}")
            kvs = []
            if ss.search_date: kvs.append(("Search Date", _s(ss.search_date)))
            if ss.filter_settings:
                kvs.append(("Filters", _s(ss.filter_settings).replace("Confererence","Conference")))
            if ss.results_count is not None: kvs.append(("Results Count", f"{ss.results_count:,}"))
            if kvs: pdf.kv_table(kvs, 0.25)
            if ss.query_string:
                pdf.set_font("Courier","",7); pdf.set_fill_color(*_GRAY_BG)
                pdf.set_x(pdf.l_margin+2)
                pdf.multi_cell(_CW-4, 3.5, _s(ss.query_string,500), fill=True)
                pdf.set_fill_color(*_WHITE); pdf.ln(2); pdf.set_font("Times","",9)
    else:
        pdf.body("No search strings recorded.")

    # ═══ 3. PRISMA 2020 FLOW DIAGRAM ════════════════════════════════════════
    sn += 1
    pdf.h2(f"{sn}. PRISMA 2020 Flow Diagram")
    if prisma_svg:
        # Record page number — we'll insert the vector PRISMA page after merging
        prisma_insert_page = pdf.page_no()
        pdf.note("See PRISMA flow diagram on the following page.")
    else:
        pdf.note("PRISMA flow diagram not available. To include it, visit the PRISMA tab before downloading the PDF.")

    # ═══ 4. SEARCH DATABASE METRICS ═════════════════════════════════════════
    if search_metrics:
        sn += 1
        pdf.h2(f"{sn}. Search Database Metrics")
        pdf.note("Precision = included / DB results  |  Recall = included from DB / total included  |  F1 = harmonic mean")
        pdf.wrapping_table(
            [("Database",0.22),("DB Results",0.13),("Imported",0.13),("Included",0.13),("Precision",0.13),("Recall",0.13),("F1",0.13)],
            [[_db_name(m["db"]),f'{m["results"]:,}',m["imported"],m["included"],
              f'{m["precision"]*100:.1f}%',f'{m["recall"]*100:.1f}%',f'{m["f1"]*100:.1f}%'] for m in search_metrics])

    # ═══ 5. SCREENING & SELECTION STATISTICS ═════════════════════════════════
    sn += 1
    pdf.h2(f"{sn}. Screening & Selection Statistics")
    pdf.kv_table([
        ("Total records retrieved (all sources)", f"{len(papers):,}"),
        ("Duplicates removed", f"{dupes:,}"),
        ("Records after deduplication", f"{after_dedup:,}"),
        ("Excluded at title/abstract screening", f"{len(scr_exc_ids):,}"),
        ("Included at screening (to full-text)", f"{len(scr_inc_ids):,}"),
        ("Excluded at full-text eligibility", f"{len(ft_exc_ids):,}"),
        ("Included from database searches", f"{len(ft_inc_ids):,}"),
        ("Included from snowballing", f"{len(snow_inc_ids):,}"),
        ("Total included studies", f"{len(included_ids):,}"),
    ], 0.60)
    pdf.note(
        "Note: 'Included from database searches' and 'Included from snowballing' are not additive; "
        "snowballed papers were assessed separately and the total of "
        f"{len(included_ids)} studies represents the combined non-overlapping set.")
    if conflict_log:
        pdf.h3("Conflict Resolution")
        pdf.kv_table([
            ("Screening conflicts (resolved)", f"{scr_conf_res:,}"),
            ("Screening conflicts (open)", f"{scr_conf_opn:,}"),
            ("Full-text conflicts (resolved)", f"{ft_conf_res:,}"),
            ("Full-text conflicts (open)", f"{ft_conf_opn:,}"),
            ("Resolved by discussion", f"{res_disc:,}"),
            ("Resolved by arbitration", f"{res_arb:,}"),
        ], 0.60)

    # ═══ 6. INTER-RATER AGREEMENT ═══════════════════════════════════════════
    if kappa_results:
        sn += 1
        pdf.h2(f"{sn}. Inter-Rater Agreement")
        pdf.body(f"Section {sn} reports inter-rater agreement statistics for each review phase.")
        for phase, data in kappa_results.items():
            kr = data["result"]; pl = phase.replace("-"," ").title()
            pdf.h3(f"{pl} - {_s(data['r1_name'])} vs. {_s(data['r2_name'])}")
            pdf.kv_table([
                ("Cohen's k", f"{kr.kappa:.4f}"),
                ("95% CI", f"[{kr.kappa_ci_lower:.4f}, {kr.kappa_ci_upper:.4f}]"),
                ("PABAK", f"{kr.pabak:.4f}"),
                ("Observed agreement (Po)", f"{kr.observed_agreement:.4f}"),
                ("Interpretation", kr.interpretation),
                ("Papers in sample", f"{kr.n_papers:,}"),
                ("Both Include", f"{kr.n_agree_include:,}"),
                ("Both Exclude", f"{kr.n_agree_exclude:,}"),
                ("Disagreements", f"{kr.n_disagree:,}"),
            ], 0.45)
        pdf.note(
            "Interpretation follows Landis, J.R. & Koch, G.G. (1977). The measurement of observer "
            "agreement for categorical data. Biometrics, 33(1), 159-174. PABAK adjusts for prevalence "
            "and bias: Byrt, T., Bishop, J., & Carlin, J.B. (1993). Bias, prevalence and kappa. "
            "Journal of Clinical Epidemiology, 46(5), 423-429.")

    # ═══ 7. QUALITY ASSESSMENT ═══════════════════════════════════════════════
    if qa_criteria:
        sn += 1
        pdf.h2(f"{sn}. Quality Assessment Results")
        qa_included = {pid: pct for pid, pct in avg_qa.items() if pid in included_ids}
        if qa_included:
            high = sum(1 for v in qa_included.values() if v>=project.qa_high_threshold)
            med  = sum(1 for v in qa_included.values() if project.qa_medium_threshold<=v<project.qa_high_threshold)
            low  = sum(1 for v in qa_included.values() if v<project.qa_medium_threshold)
            avg_all = sum(qa_included.values())/len(qa_included)
            # Synthesis chart 1: QA score distribution histogram.
            if qa_stats["n"] > 0:
                fig_num += 1
                pdf.body(f"Figure {fig_num} presents the distribution of quality assessment scores across all assessed studies.")
                pdf.note(f"n = {qa_stats['n']} · mean {qa_stats['mean']:.1f}% · median {qa_stats['median']:.1f}%")
                if quality_distribution_svg:
                    chart_insertions.append((
                        pdf.page, quality_distribution_svg, 460.0,
                        f"Figure {fig_num}: Quality Score Distribution (n={qa_stats['n']} papers assessed).",
                    ))
                else:
                    _draw_qa_distribution_chart(pdf, qa_bins,
                                                project.qa_medium_threshold, project.qa_high_threshold)
            pdf.kv_table([
                ("Papers assessed",f"{len(qa_included):,}"),("Average QA score",f"{avg_all:.1f}%"),
                ("High quality",f"{high:,}"),("Medium quality",f"{med:,}"),("Low quality",f"{low:,}"),
            ], 0.45)
            extra = len(avg_qa) - len(qa_included)
            if extra > 0:
                pdf.note(f"{extra} additional candidate(s) underwent QA assessment before being excluded "
                         f"at full-text stage; they are not counted in the {len(included_ids)} included studies.")
            qa_paps = sorted([p for p in included_pap if p.id in qa_included], key=lambda p: qa_included.get(p.id,0), reverse=True)
            if qa_paps:
                pdf.h3("Per-Paper Quality Scores")
                cc = [(c.label,0.06) for c in qa_criteria]
                bc = [("Paper Key",0.14),("Year",0.06)]; ec = [("Total",0.08),("Level",0.08)]
                fixed = sum(f for _,f in bc+ec)
                avail_frac = 1.0 - fixed
                cc = [(c.label, avail_frac/len(qa_criteria)) for c in qa_criteria]
                pdf.wrapping_table(bc+cc+ec,
                    [[f"[{p.citekey}]", p.year or "-"]
                     + [next((str(s.score) for s in by_paper.get(p.id,[]) if s.criterion_id==c.id and s.score is not None),"-") for c in qa_criteria]
                     + [f"{qa_included.get(p.id,0):.0f}%",
                        "High" if qa_included.get(p.id,0)>=project.qa_high_threshold else "Med" if qa_included.get(p.id,0)>=project.qa_medium_threshold else "Low"]
                     for p in qa_paps])

    # ═══ 8. SNOWBALLING ═════════════════════════════════════════════════════
    if snow_iterations:
        sn += 1
        pdf.h2(f"{sn}. Snowballing Iterations")
        rows = []
        for it in sorted(snow_iterations, key=lambda x: x.iteration_number):
            ip = [p for p in snow_papers if p.source==f"snowballing:{it.iteration_number}"]
            rows.append([f"Iteration {it.iteration_number}", it.iteration_type.title(), len(ip),
                         sum(1 for p in ip if p.id in included_ids), "Yes" if it.saturation_confirmed else "No"])
        pdf.wrapping_table([("Iteration",0.22),("Type",0.18),("Retrieved",0.20),("Included",0.20),("Saturated",0.20)], rows)

    # ═══ 9. DATA EXTRACTION SCHEMA ══════════════════════════════════════════
    sn += 1
    pdf.h2(f"{sn}. Data Extraction Schema")

    # Iteration-2 issue 5: one donut chart per taxonomy dimension (dynamic).
    # The web side renders one panel each — the PDF mirrors that with one
    # captioned figure per taxonomy in the same setup-defined order.
    _tax_svg_map = {
        'research_type':    research_type_svg,
        'contribution_type': contribution_type_svg,
    }
    for key, rows in taxonomy_donuts:
        if not rows or all(r["count"] == 0 for r in rows): continue
        fig_num += 1
        label = _s(key.replace("_", " ").title())
        pdf.body(f"Figure {fig_num} presents the distribution of included papers "
                 f"across the {label.lower()} taxonomy.")
        pdf.h3(label)
        svg_for_key = _tax_svg_map.get(key)
        if svg_for_key:
            chart_insertions.append((
                pdf.page, svg_for_key, 300.0,
                f"Figure {fig_num}: {label} Distribution.",
            ))
        else:
            _draw_donut_chart(pdf, rows, label="papers")

    # Iteration-1 chart 4: distribution across the first dropdown extraction
    # field — kept (a real synthesis dimension that's not a taxonomy).
    if extraction_field and extraction_rows:
        fig_num += 1
        pdf.body(f"Figure {fig_num} presents the distribution of papers across the "
                 f"{extraction_field.field_label} extraction field.")
        pdf.h3(f"Extraction — {_s(extraction_field.field_label)}")
        _draw_extraction_field_chart(pdf, extraction_rows)

    # Iteration-2 issue 6: Venue types donut + top-venues table.
    if included_papers:
        fig_num += 1
        pdf.body(f"Figure {fig_num} presents the distribution of included papers "
                 f"across the venue-type categorisation.")
        pdf.h3("Venue Types")
        if venue_types_svg:
            chart_insertions.append((
                pdf.page, venue_types_svg, 300.0,
                f"Figure {fig_num}: Venue Type Distribution.",
            ))
        else:
            _draw_donut_chart(pdf, venue_rows, label="papers")
        if venue_top10:
            pdf.set_font("Times", "B", 8.5); pdf.set_text_color(*_DARK)
            pdf.ln(2)
            pdf.cell(0, 4, _s("Top venues by name:"), ln=True)
            pdf.wrapping_table(
                [("Venue", 0.62), ("Category", 0.20), ("Count", 0.18)],
                [[_s(name, 80), cat, count] for name, cat, count in venue_top10],
            )
            pdf.set_text_color(*_BLACK)

        # Figure 5: publications per year
        if publications_year_svg:
            fig_num += 1
            pdf.body(f"Figure {fig_num} presents the temporal distribution of included papers "
                     f"across the study period.")
            # Determine year range from included papers for caption
            years = sorted({p.year for p in included_papers if p.year})
            yr_range = f"{years[0]}–{years[-1]}" if len(years) >= 2 else str(years[0]) if years else "n/a"
            chart_insertions.append((
                pdf.page, publications_year_svg, 460.0,
                f"Figure {fig_num}: Publications per Year ({yr_range}).",
            ))

    if taxonomy:
        pdf.h3("Taxonomy Categories")
        tax_sorted = sorted(taxonomy, key=lambda t: (t.taxonomy_type, t.sort_order))
        for tt, entries in groupby(tax_sorted, key=lambda t: t.taxonomy_type):
            lbl = tt.replace("_"," ").title()
            vals = ", ".join(_s(e.value) for e in entries)
            pdf.h4(f"{_s(lbl)}:")
            pdf.indent_text(vals, indent=12)

    if non_tax_fields:
        pdf.h3("Custom Extraction Fields")
        for f in non_tax_fields:
            tm = {"text":"Free text","number":"Number","boolean":"Boolean - Yes / No","dropdown":"Select"}
            tl = tm.get(f.field_type, f.field_type)
            if f.field_type == "dropdown" and f.options:
                try: tl += " - " + " / ".join(str(o) for o in json.loads(f.options))
                except: tl += " - " + str(f.options)
            pdf.h4(_s(f.field_label))
            pdf.indent_text(f"Type: {_s(tl, 200)}", indent=12)

    # Sections 1-9 complete. Output the fpdf2 PDF.
    main_bytes = bytes(pdf.output())

    # Merge chart SVG pages at their tracked positions
    if chart_insertions:
        main_bytes = _insert_chart_pages(main_bytes, chart_insertions)

    # Merge PRISMA vector PDF if available (must come after chart insertions so
    # the PRISMA page count offset is applied to the already-enlarged document)
    if prisma_svg and prisma_insert_page:
        main_bytes = _merge_prisma_pdf(main_bytes, prisma_svg, prisma_insert_page)

    # ═══ 10. INCLUDED PAPERS (built with ReportLab Platypus) ════════════════
    sn += 1
    if included_pap:
        sec10_bytes = _build_section10_pdf(
            included_pap, avg_qa, project, all_fns, fl, rec_map,
            section_num=sn, slr_title=project.title,
        )
        # Append Section 10 PDF pages to the main PDF
        try:
            from pypdf import PdfReader, PdfWriter
            writer = PdfWriter()
            for page in PdfReader(io.BytesIO(main_bytes)).pages:
                writer.add_page(page)
            for page in PdfReader(io.BytesIO(sec10_bytes)).pages:
                writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            main_bytes = buf.getvalue()
        except ImportError:
            pass  # pypdf not available — Section 10 skipped

    return main_bytes


# ─────────────────────────────────────────────────────────────────────────────

def _generate(pid, session, prisma_svg=None,
              quality_distribution_svg=None, publications_year_svg=None,
              research_type_svg=None, contribution_type_svg=None, venue_types_svg=None):
    project = session.get(Project, pid)
    if not project: raise HTTPException(404, "Project not found")
    def q(m): return session.exec(select(m).where(m.project_id == pid)).all()
    now = datetime.utcnow().strftime("%B %d, %Y")
    buf = io.BytesIO(_build_pdf(
        project, q(Reviewer), q(InclusionCriterion), q(ExclusionCriterion), q(QACriterion),
        q(DatabaseSearchString), q(Paper), q(ReviewerDecision), q(FinalDecision),
        q(ConflictLog), q(QAScore), q(ExtractionField), q(ExtractionRecord),
        q(SnowballingIteration), q(TaxonomyEntry), now,
        db_links=q(PaperDatabaseLink), prisma_svg=prisma_svg,
        quality_distribution_svg=quality_distribution_svg,
        publications_year_svg=publications_year_svg,
        research_type_svg=research_type_svg,
        contribution_type_svg=contribution_type_svg,
        venue_types_svg=venue_types_svg))
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project.title)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="reviq_protocol_{safe}.pdf"'})


@router.post("/{pid}/report/pdf")
def download_report_post(pid: int, body: ReportBody, session: Session = Depends(get_session)):
    return _generate(pid, session,
                     prisma_svg=body.prisma_svg,
                     quality_distribution_svg=body.quality_distribution_svg,
                     publications_year_svg=body.publications_year_svg,
                     research_type_svg=body.research_type_svg,
                     contribution_type_svg=body.contribution_type_svg,
                     venue_types_svg=body.venue_types_svg)

@router.get("/{pid}/report/pdf")
def download_report_get(pid: int, session: Session = Depends(get_session)):
    return _generate(pid, session)
