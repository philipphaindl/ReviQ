# Walking Skeleton — Implementierungsplan

Werkzeug zur Unterstützung von Grey-Literature- und Multivocal-Literature-Reviews
nach Garousi, Felizardo & Mäntylä (IST, 2019).

Stand: 2026-08-11 · Status: umgesetzt; historisches Dokument

> **Nachtrag, 2026-08-12.** Dieser Plan entstand, als der Abruf ein eigenständiges
> Werkzeug (`glr`) in einem eigenen Repository unter MIT werden sollte, mit einer
> SoftwareX-Einreichung als Ziel. Beides ist überholt: publiziert ist ReviQ, der Abruf
> ist ein Teil davon und steht unter GPL-3.0. Die Passagen, die daran hingen, sind unten
> als überholt gekennzeichnet statt gelöscht — sie begründen technische Entscheidungen,
> die weiterhin gelten, und ein Plan, aus dem die Prämissen herausgeschnitten wurden,
> lässt sich nicht mehr nachvollziehen. Die Entscheidungen selbst stehen in
> `decisions.md` (D1–D26).

---

## 0. Vorbemerkung zur Recherchelage

Die Vorgabe war, keine Endpunkte oder Parameter aus dem Gedächtnis zu setzen. In dieser
Session ist der direkte Abruf von Webseiten durch den Egress-Proxy gesperrt
(`searchapi.io`, `scrapingbee.com`, `pypi.org`, `readthedocs.io`, `github.com` — alle
`EGRESS_BLOCKED`). Verfügbar war nur die indizierte Websuche. Alle unten genannten
Fakten stammen daher aus dem Suchindex der jeweiligen Originaldokumentation, nicht aus
einem Direktabruf.

Konsequenz für den Plan: Die exakte Parameterfläche beider APIs ist in **je einem
kleinen Modul** gekapselt (`serp.py`, `fetch.py`), und **Schritt 4 und 5** der
Umsetzung beginnen jeweils mit einem Live-Call gegen das Free-Kontingent
(SearchApi: 100 Requests, ScrapingBee: 1.000 Credits). Eine falsche Annahme kostet
damit fünf Minuten, nicht die Architektur.

Fakten mit dem Vermerk **[live prüfen]** sind vor der Implementierung gegen die
Originaldoku zu verifizieren.

---

## 1. Zielarchitektur

Ein lokales Python-CLI, das eine Suchanfrage in einer linearen Pipeline verarbeitet:

```
Query ──► SearchApi.io ──► Kanonisierung/Dedup ──► ScrapingBee ──► WARC-Snapshot
          (SERP-JSON)      (courlan)              (Bytes+Header)   (+ SHA-256)
                                                                        │
                          CSV ◄── SQLite ◄── Textextraktion ◄───────────┘
                                             (trafilatura / pdfminer.six)
```

Drei Entwurfsentscheidungen tragen den wissenschaftlichen Kern:

1. **Beobachtung und Entität sind getrennt.** Ein `document` ist eine kanonische URL und
   existiert genau einmal. Ein `serp_result` ist die Beobachtung „diese URL stand am
   Zeitpunkt T bei Engine E auf Position N für Suchstring Q" und wird pro Lauf neu
   geschrieben. Das ist die Grundlage für Provenienz *und* für Idempotenz — ein zweiter
   Lauf erzeugt neue Beobachtungen, aber keine doppelten Dokumente.

2. **Jeder Lauf ist ein Datensatz.** `run_id` hängt an jedem Datensatz. Nichts wird je
   überschrieben, kein `UPDATE` auf inhaltstragenden Feldern. Wiederholbarkeit heißt
   hier: alte Läufe bleiben unverändert abrufbar.

3. **Der Snapshot ist die Belegkette.** Der Rohinhalt wird als WARC-Record abgelegt,
   bevor irgendetwas extrahiert wird. Extraktion ist damit jederzeit ohne erneuten
   Netzzugriff wiederholbar — auch wenn die Seite verschwunden ist, und auch wenn ich
   später den Extraktor wechsle.

Kein Adapter-Layer, keine Interfaces, keine Vererbung. Sechs Module mit Funktionen.
Die spätere Erweiterbarkeit entsteht aus dem Datenmodell, nicht aus Abstraktionen.

---

## 2. Stack: Python — Zustimmung, mit Begründung

Deine Annahme trägt, und zwar aus einem stärkeren Grund als der Bibliothekslage:

- **trafilatura** ist der einzige HTML-Extraktor mit publiziertem, peer-reviewtem
  Benchmark (Barbaresi, ACL 2021, System Demonstrations). In einer MLR muss ich die
  Textextraktion im Methodenteil zitierfähig begründen können. Das geht mit trafilatura,
  mit einer selbstgebauten BeautifulSoup-Heuristik nicht.
- **warcio** kommt von Webrecorder, also aus der Web-Archiving-Community selbst.
- **SQLite** ist in der Standardbibliothek (`sqlite3`), kein ORM nötig.
- Nachnutzbarkeit: Forschende in Software Engineering lesen Python. Wer das Repo klont,
  soll den Abrufteil in fünf Minuten verstehen. *(Ursprünglich mit einem SoftwareX-Reviewer
  als Adressat begründet — überholt, das Argument trägt ohne ihn.)*

Gegenargument, das ich geprüft und verworfen habe: Go oder Rust wären für die
Netzwerk-Nebenläufigkeit angenehmer. Bei ~50 URLs pro Lauf und einem ScrapingBee-Limit
von 1 gleichzeitigem Request im Freelance-Plan ist Nebenläufigkeit aber schlicht kein
Problem. Der Vorteil verfällt, die Kosten (Extraktions-Ökosystem, Zielgruppe) bleiben.

**Umgebung:** `uv` mit `pyproject.toml` und eingecheckter `uv.lock`. Die Lockfile mit
Hashes ist die belastbarste Reproduzierbarkeitsaussage, die ich im Paper machen kann
(*Annahme, siehe §9*). Python ≥ 3.11.

---

## 3. Snapshot-Format: WARC — geprüft und gewählt

Auftrag war, WARC zu prüfen. Ergebnis: WARC, mit einer wichtigen Einschränkung, die
dokumentiert gehört.

**Dafür:**

| Kriterium | WARC | Alternative (Rohdatei + JSON-Sidecar) |
|---|---|---|
| Standardisierung | ISO 28500 | keine |
| HTTP-Header konserviert | ja, im Record | nur was ich selbst hinschreibe |
| Payload-Hash im Format | `WARC-Payload-Digest` | selbst zu pflegen |
| Fremdwerkzeuge lesen es | pywb, ReplayWeb.page, warcio | nein |
| Community | Internet Archive, Nationalbibliotheken | — |

Der entscheidende Punkt für eine MLR: Ein Reviewer kann eine `.warc.gz` in
ReplayWeb.page ziehen und die Quelle so sehen, wie sie beim Abruf aussah. Das ist bei
Grey Literature — die notorisch verschwindet oder still editiert wird — der
Unterschied zwischen belegt und behauptet.

**Die Einschränkung, ehrlich benannt:** Ich rufe über ScrapingBee ab. Der WARC-Response-
Record enthält damit *die Antwort von ScrapingBee*, nicht die rohe Antwort des Origin-
Servers. Das ist kein Fehler, aber es muss im Paper stehen. Abgemildert wird es dadurch,
dass ScrapingBee die Origin-Fakten in eigenen Headern zurückgibt (`Spb-Initial-Status-Code`,
`Spb-Resolved-Url`), die ich sowohl in die DB als auch als `WARC-Metadata`-Record
schreibe.

**Konkret:**
- Eine Datei pro Lauf: `data/runs/<run_id>/snapshots.warc.gz`
- `gzip=True` → ein gzip-Member pro Record, Records bleiben einzeln adressierbar
- `warc_offset` in der DB → wahlfreier Zugriff ohne Volldurchlauf
- Pro Abruf zwei Records: `response` (Inhalt) + `metadata` (ScrapingBee-Header, Kosten)
- **SHA-256 der Payload zusätzlich in der DB.** warcio schreibt `WARC-Payload-Digest`
  konventionsgemäß als SHA-1/base32; SHA-1 will ich in einem Paper 2026 nicht als
  Integritätsnachweis anführen. **[live prüfen: ob warcio SHA-256 als Digest-Algorithmus
  akzeptiert — falls ja, beides setzen]**

---

## 4. Bibliotheken

Alle Lizenzen sind permissiv und fließen einseitig in ein GPL-3.0-Werk. *(Stand damals: Kompatibilität mit einem MIT-Release — die Anforderung ist seither strenger, das Ergebnis dasselbe.)*

| Zweck | Wahl | Lizenz | Begründung |
|---|---|---|---|
| HTTP-Client | `httpx` | BSD-3 | Explizite Timeouts (Default ist *kein* unendlicher Timeout, anders als `requests`), sauberer Umgang mit Redirects und Binärinhalten |
| SERP | direkt via `httpx` | — | Kein offizieller SearchApi-Python-Client nötig; der Aufruf ist ein GET mit Query-Parametern. Eine Abhängigkeit weniger, und ich sehe die Rohantwort |
| Scraping | direkt via `httpx` | — | dito. Der offizielle `scrapingbee`-Client verdeckt die `Spb-*`-Response-Header, die ich für die Provenienz brauche |
| HTML-Extraktion | `trafilatura` ≥ 2.0 | **Apache-2.0** (seit 1.8.0, davor GPLv3+) | Beste Precision/Recall im publizierten Benchmark, zitierfähig, liefert Metadaten (Titel, Datum, Autor) und Boilerplate-Entfernung in einem Aufruf |
| URL-Kanonisierung | `courlan` | **Apache-2.0** (seit v1, davor GPLv3+) | `clean_url()` entfernt Tracking-Parameter und normalisiert; vom selben Autor wie trafilatura, wird ohnehin als dessen Abhängigkeit installiert |
| PDF-Text | `pdfminer.six` | **MIT** | Bessere Layout-Analyse als `pypdf` bei mehrspaltigen Reports, was bei Grey Literature (Whitepaper, Behördenberichte) der Normalfall ist |
| WARC | `warcio` | **Apache-2.0** | ISO-28500-konform, WARC 1.0 und 1.1, minimale Abhängigkeiten |
| DB | `sqlite3` | stdlib | — |
| CSV | `csv` | stdlib | — |
| CLI | `argparse` | stdlib | Für sechs Flags braucht es kein Click |

### Bewusst abgelehnt

**PyMuPDF — abgelehnt wegen Lizenz.** PyMuPDF steht unter **AGPL-3.0**. Für ein Werkzeug,
das weitergegeben und nachgenutzt werden soll, hieße das: entweder das gesamte Werkzeug
unter AGPL stellen, oder eine kommerzielle Lizenz von Artifex kaufen
(Größenordnung fünfstellig pro Jahr). Beides ist für dieses Vorhaben inakzeptabel.
Technisch wäre PyMuPDF 10–50× schneller — bei ~50 PDFs pro Lauf ist das irrelevant.
**Diese Entscheidung sollte im Repo dokumentiert werden**, weil sie sonst später jemand
„optimierend" rückgängig macht.

`pdfplumber` (MIT) wäre die Alternative, bringt aber Tabellenerkennung mit, die ich
nicht brauche — und sitzt selbst auf `pdfminer.six` auf.

**Kein ORM, kein Pydantic, kein Config-Framework, kein Rich.** Alles davon ist im
Skelett Ballast.

---

## 5. Externe APIs — recherchierter Stand

### SearchApi.io

- Endpunkt: `https://www.searchapi.io/api/v1/search`
- Auth: `api_key` als Query-Parameter **oder** `Authorization: Bearer <key>` — ich nehme
  den Header, damit der Key nicht in Logs landet
- Parameter: `engine=google`, `q`, `page` (Default 1), `gl`, `hl`, `location`, `device`
- Antwort: `search_metadata` mit `id`, `created_at`, `request_url`, `total_time_taken`;
  `organic_results[]` mit `position`, `title`, `link`, `domain`, `displayed_link`,
  `snippet`, ggf. `source`
- Abrechnung: nur erfolgreiche Requests (HTTP 200). 100 Requests kostenlos, kein
  Kreditkartenzwang. Bezahlt ab ca. $40/Monat, Developer-Plan ~$4 pro 1.000 Suchen

> **Wichtig und neu:** Google hat den `num`-Parameter am **11.09.2025** deaktiviert.
> Bei `engine=google` liefert ein Request jetzt fix **10 Treffer**; mehr geht nur über
> `page`. Für 50 Treffer pro Suchstring sind das 5 API-Calls (~2 Cent). Die Engine
> `google_rank_tracking` unterstützt weiterhin `num=1..100` in einem Call, ist aber ein
> anderes Antwortschema. **[live prüfen]**

### ScrapingBee

- Endpunkt: `https://app.scrapingbee.com/api/v1/`
- Pflichtparameter: `api_key`, `url`
- Relevante Parameter: `render_js` (**Default `true`**), `premium_proxy`, `stealth_proxy`,
  `json_response`
- Response-Header — **das ist der Provenienz-Jackpot**:
  - `Spb-Resolved-Url` — finale URL nach Redirects
  - `Spb-Initial-Status-Code` — HTTP-Status des Origin-Servers
  - `Spb-Cost` — verbrauchte Credits
- Credits: klassischer Proxy ohne JS **1**, mit JS **5**, Premium ohne JS **10**, mit JS **25**
- PDFs: funktionieren mit `render_js=false`, die API gibt die Binärdaten unverändert zurück
- Kontingent: 1.000 Credits kostenlos; Freelance $49/Monat mit 100k Credits, 1 paralleler Request

> **Kostenrelevant:** `render_js` ist per Default **an** und kostet damit 5 statt 1
> Credit. Das Skelett setzt `render_js=false` als Default (1 Credit) und bietet
> `--render-js` als Flag. Bei 50 URLs: 50 Credits statt 250. Das Free-Kontingent reicht
> so für rund 20 Testläufe.

---

## 6. Dateistruktur

```
glr/
├── README.md                  # Installation, ein Beispielaufruf, Datenmodell-Skizze
├── LICENSE                    # überholt: liegt heute bei ReviQ, GPL-3.0
├── pyproject.toml             # überholt: heute backend/requirements.txt
├── uv.lock
├── .env.example               # SEARCHAPI_API_KEY=, SCRAPINGBEE_API_KEY=
├── .gitignore                 # .env, data/, __pycache__
├── docs/
│   ├── PLAN.md                # dieses Dokument
│   └── decisions.md           # kurze ADRs: WARC, PyMuPDF/AGPL, num-Deprecation
├── src/glr/
│   ├── __init__.py            # __version__
│   ├── cli.py                 # argparse, orchestriert die Pipeline
│   ├── db.py                  # Verbindung, Migration, Insert-Helfer
│   ├── schema.sql             # DDL, als Datei — les- und diffbar
│   ├── urls.py                # Kanonisierung, Dedup-Schlüssel
│   ├── serp.py                # SearchApi-Client
│   ├── fetch.py               # ScrapingBee-Client
│   ├── archive.py             # WARC schreiben, SHA-256
│   ├── extract.py             # HTML/PDF-Dispatch, Textextraktion
│   └── export.py              # CSV
├── tests/
│   ├── fixtures/              # ein gespeichertes SERP-JSON, ein HTML, ein PDF
│   ├── test_urls.py           # Kanonisierung — reine Funktion, offline testbar
│   ├── test_extract.py        # gegen Fixtures, kein Netz
│   └── test_idempotency.py    # zweiter Lauf → keine Duplikate
└── data/                      # gitignored
    ├── glr.sqlite3
    └── runs/<run_id>/snapshots.warc.gz
```

Neun Quelldateien, keine davon über ~150 Zeilen.

---

## 7. Datenmodell

Fünf Tabellen. `*_at_utc` durchgängig ISO-8601 mit `Z`, erzeugt via
`datetime.now(timezone.utc)` — nie lokale Zeit.

### `runs` — ein CLI-Aufruf

| Feld | Typ | Anmerkung |
|---|---|---|
| `run_id` | TEXT PK | UUID4 |
| `query` | TEXT NOT NULL | der Suchstring, wörtlich |
| `engine` | TEXT NOT NULL | `google` |
| `search_params_json` | TEXT NOT NULL | `gl`, `hl`, `pages`, `device` — vollständig, für Reproduktion |
| `started_at_utc` | TEXT NOT NULL | |
| `finished_at_utc` | TEXT | NULL = abgebrochen |
| `tool_version` | TEXT NOT NULL | `glr.__version__` |
| `status` | TEXT NOT NULL | `running` / `completed` / `failed` |

### `serp_results` — die Beobachtung, pro Lauf neu

| Feld | Typ | Anmerkung |
|---|---|---|
| `serp_result_id` | INTEGER PK | |
| `run_id` | TEXT NOT NULL → runs | |
| `page` | INTEGER NOT NULL | |
| `position` | INTEGER NOT NULL | Position innerhalb der Seite, wie von der API geliefert |
| `global_rank` | INTEGER NOT NULL | `(page-1)*10 + position` — die zitierfähige Trefferposition |
| `raw_url` | TEXT NOT NULL | unverändert aus der SERP |
| `canonical_url` | TEXT NOT NULL | |
| `title` / `snippet` / `displayed_link` | TEXT | |
| `retrieved_at_utc` | TEXT NOT NULL | Abrufzeitpunkt der SERP |
| `searchapi_search_id` | TEXT | `search_metadata.id` — Beleg beim Anbieter |
| `document_id` | INTEGER → documents | |

`UNIQUE(run_id, page, position)` — macht den SERP-Abruf idempotent.

### `documents` — die stabile Entität, eine pro kanonischer URL

| Feld | Typ | Anmerkung |
|---|---|---|
| `document_id` | INTEGER PK | |
| `canonical_url` | TEXT NOT NULL **UNIQUE** | **der Dedup-Schlüssel** |
| `registered_domain` | TEXT | für spätere Quellenauswertung |
| `first_seen_run_id` | TEXT NOT NULL | |
| `first_seen_at_utc` | TEXT NOT NULL | |

### `snapshots` — ein tatsächlicher Abruf, versioniert

| Feld | Typ | Anmerkung |
|---|---|---|
| `snapshot_id` | INTEGER PK | |
| `document_id` | INTEGER NOT NULL → documents | |
| `run_id` | TEXT NOT NULL → runs | |
| `requested_url` | TEXT NOT NULL | |
| `final_url` | TEXT | aus `Spb-Resolved-Url` |
| `http_status` | INTEGER | aus `Spb-Initial-Status-Code` — der **Origin**-Status |
| `proxy_status` | INTEGER | der Status von ScrapingBee selbst |
| `content_type` | TEXT | |
| `content_length` | INTEGER | |
| `sha256` | TEXT NOT NULL | über die Roh-Bytes |
| `media_type` | TEXT NOT NULL | `html` / `pdf` / `other` |
| `fetched_at_utc` | TEXT NOT NULL | |
| `warc_path` / `warc_offset` / `warc_record_id` | TEXT/INT/TEXT | Rückverweis in den Snapshot |
| `credits_cost` | INTEGER | aus `Spb-Cost` — Kostenkontrolle |
| `fetch_error` | TEXT | NULL bei Erfolg |

`UNIQUE(document_id, run_id)` — pro Lauf höchstens ein Abruf je Dokument.

### `extractions` — Text zu einem Snapshot

| Feld | Typ | Anmerkung |
|---|---|---|
| `extraction_id` | INTEGER PK | |
| `snapshot_id` | INTEGER NOT NULL **UNIQUE** → snapshots | |
| `extractor` | TEXT NOT NULL | z.B. `trafilatura-2.2.0` — Extraktorwechsel bleibt nachvollziehbar |
| `title` / `author` / `publication_date` / `language` | TEXT | aus trafilatura-Metadaten |
| `text` | TEXT | |
| `word_count` | INTEGER | |
| `extracted_at_utc` | TEXT NOT NULL | |
| `extraction_error` | TEXT | |

### Wie daraus Idempotenz und Dedup entstehen

- **Gleiche Query zweimal** → neuer `run_id`, neue `serp_results`. Bestehende `documents`
  werden per `INSERT ... ON CONFLICT(canonical_url) DO NOTHING` wiederverwendet.
  Keine Duplikate, aber die neue Trefferposition ist dokumentiert.
- **Gleiche URL auf zwei Positionen** → ein `document`, zwei `serp_results`.
- **Zwei URLs, gleicher Inhalt** (Redirect, Spiegel) → zwei `documents`, aber identischer
  `sha256`. Beim Export als `content_duplicate_of` per SQL aufgelöst, nicht redundant
  gespeichert.
- **Re-Fetch:** Default ist *kein* erneuter Abruf, wenn schon ein Snapshot existiert
  (*Annahme, siehe §9*). `--refetch` erzwingt einen neuen.

---

## 8. Implementierungsreihenfolge

Sequenziert so, dass nach jedem Schritt etwas Lauffähiges existiert. Zeiten sind
Schätzungen für konzentriertes Arbeiten.

**Abend 1 — Gerüst und Datenfluss (ca. 3,5 h)**

| # | Schritt | Ergebnis | ~ |
|---|---|---|---|
| 1 | Repo-Grundgerüst: `pyproject.toml`, `LICENSE`, `.gitignore`, `.env.example`, `uv sync` | `uv run glr --help` läuft | 20 min |
| 2 | `schema.sql` + `db.py` + `glr init` | DB-Datei mit fünf Tabellen | 30 min |
| 3 | `urls.py` + `test_urls.py` | Kanonisierung grün, ohne Netz | 30 min |
| 4 | `serp.py` + `glr search "..." --dry-run` | **erster Live-Call**, SERP-JSON auf stdout | 45 min |
| 5 | SERP-Persistierung: `runs` + `serp_results` + `documents` | `glr search` schreibt in die DB | 45 min |
| 6 | `fetch.py` + `glr fetch <url>` | **zweiter Live-Call**, Bytes + `Spb-*`-Header | 40 min |

Nach Abend 1 steht die riskante Hälfte: beide API-Verträge sind verifiziert, das
Datenmodell hält echte Daten.

**Abend 2 — Snapshot, Text, Export (ca. 3 h)**

| # | Schritt | Ergebnis | ~ |
|---|---|---|---|
| 7 | `archive.py`: WARC schreiben, SHA-256, `snapshots` füllen | `.warc.gz` mit ReplayWeb.page prüfbar | 45 min |
| 8 | `extract.py`: Dispatch über Magic Bytes (`%PDF-`), trafilatura + pdfminer.six | `extractions` gefüllt | 45 min |
| 9 | `cli.py`: `glr run "query"` verdrahtet die ganze Kette | End-to-End-Durchlauf | 40 min |
| 10 | `export.py`: CSV | die Datei aus der Definition of Done | 25 min |
| 11 | `test_idempotency.py`: zweiter Lauf, keine Duplikate | grün | 20 min |
| 12 | README + Smoke-Test mit echtem Suchstring | Sichtprüfung | 25 min |

**Gesamt ≈ 6,5 h.** Puffer ist absichtlich in den API-Schritten 4 und 6, weil dort die
ungeprüften Annahmen sitzen.

> **Magic Bytes statt Content-Type:** Der `Content-Type`-Header lügt bei Grey Literature
> regelmäßig (PDFs als `text/html`, `application/octet-stream`). Der Dispatch prüft die
> ersten fünf Bytes auf `%PDF-`. Kostet drei Zeilen und erspart stille Fehlextraktionen.

### CSV-Ausgabe

Eine Zeile pro Dokument pro Lauf:

```
run_id, query, engine, global_rank, retrieved_at_utc,
raw_url, canonical_url, final_url, http_status,
title, snippet, publication_date, language,
media_type, sha256, word_count,
warc_path, warc_offset, content_duplicate_of, extraction_error
```

Damit ist jede Zeile bis zur archivierten Byte-Folge rückverfolgbar — und genau das ist
die Provenienz-Anforderung.

---

## 9. Getroffene Annahmen

Vier Fragen blieben offen; ich habe entschieden, damit der Plan vollständig ist. Jede
lässt sich in einer Zeile ändern:

| # | Annahme | Änderung kostet |
|---|---|---|
| 1 | **SERP-Tiefe:** `engine=google` + Page-Loop, `--pages` (Default 5 = 50 Treffer) | `google_rank_tracking` wäre ein anderes Antwortschema in `serp.py` |
| 2 | **Re-Fetch:** bekannte URLs werden nicht erneut abgerufen, `--refetch` erzwingt es | eine `if`-Bedingung in `cli.py` |
| 3 | ~~**Lizenz: MIT**~~ — überholt. Der Abruf ist Teil von ReviQ und damit GPL-3.0; alle gewählten Abhängigkeiten sind damit weiterhin verträglich | erledigt |
| 4 | **Tooling: `uv` + `uv.lock`** | `requirements.txt` stattdessen |

---

## 10. Risiken und offene Entscheidungen

**R1 — SERP-Ergebnisse sind nicht reproduzierbar.** Google liefert personalisiert,
lokalisiert und zeitabhängig. Derselbe Suchstring liefert morgen andere Treffer. Das ist
die bekannteste Bedrohung der Validität bei MLRs und *nicht* behebbar. Abmilderung: `gl`
und `hl` explizit setzen und im Lauf protokollieren, `retrieved_at_utc` je Treffer,
Snapshots als Beleg. Im Paper gehört das in die Threats to Validity.

**R2 — `num`-Deprecation (11.09.2025) treibt Kosten und Laufzeit.** 10 Treffer pro Call
statt 100. Bei 20 Suchstrings à 50 Treffern sind das 100 Calls statt 20. Bei
$4/1.000 unkritisch (~40 Cent), bei größerem Review relevant. Offene Entscheidung:
`google_rank_tracking` evaluieren.

**R3 — WARC bildet die Proxy-Antwort ab, nicht die Origin-Antwort.** Siehe §3. Muss im
Paper stehen. Zu prüfen: ob `Spb-Initial-Status-Code` bei Redirect-Ketten den *ersten*
oder den *letzten* Status meldet — das entscheidet, ob die Provenienzangabe „HTTP-Status"
korrekt benannt ist. **[live prüfen]**

**R4 — Textextraktion scheitert stillschweigend.** trafilatura gibt bei
JS-Seiten oder ungewöhnlichem Markup `None` zurück. Ohne Gegenmaßnahme entsteht eine CSV
mit leeren Textspalten, die wie ein Datenproblem aussieht. Abmilderung: `word_count` und
`extraction_error` in der CSV, plus eine Warnung am Laufende („7 von 50 Dokumenten ohne
Text"). Dann ist der `--render-js`-Zweitversuch eine bewusste Entscheidung.

**R5 — Rechtliche und ethische Lage.** Ein kommerzieller Scraping-Dienst umgeht
Blocker; robots.txt wird dabei faktisch nicht respektiert. Für eine wissenschaftliche
Publikation braucht das eine explizite Position im Paper (Zweck, Umfang, keine
Massenabfrage, keine Umgehung von Paywalls). Das ist keine Code-Frage, aber es sollte
*jetzt* entschieden werden, nicht beim Schreiben. Empfehlung: `data/` bleibt lokal,
Snapshots werden **nicht** mitveröffentlicht — im Repo nur der Code, im Artefakt-Anhang
höchstens Hashes und URLs.

**R6 — Keine Ratenbegrenzung im Skelett.** Bei 1 parallelem Request (Freelance-Plan) und
sequenzieller Verarbeitung ist das unkritisch, ein `time.sleep` zwischen Requests und ein
einfacher Retry bei 429/5xx sind aber im Schritt 6 mit einzuplanen. Keine zusätzliche
Abhängigkeit (`tenacity`) nötig.

**R7 — Kanonisierung kann übertreiben.** `courlan.clean_url()` entfernt Query-Parameter.
Bei Grey Literature sind manche davon inhaltstragend (`?id=`, `?doc=`). Aggressive
Normalisierung würde verschiedene Dokumente zu einem verschmelzen — ein stiller
Datenverlust. Deshalb wird **`raw_url` immer zusätzlich gespeichert** und in Schritt 3
gegen echte URLs aus dem Reviewthema getestet.

---

## 11. Empfehlungen — bewusst NICHT im Plan

Diese Punkte halte ich mittelfristig für notwendig, sie gehören aber nicht in dieses
Skelett:

1. **Konfigurationsdatei für Query-Sets.** Sobald du 20 Suchstrings systematisch fährst,
   ist der CLI-Aufruf pro Query nicht mehr praktikabel. Das Datenmodell trägt es
   bereits (`runs.search_params_json`); es fehlt nur ein Loader. **Erster Kandidat nach
   dem Skelett.**
2. **Abbruchkriterium / theoretische Sättigung** (Garousi §5.3) — die Guidelines fordern
   ein explizites Stopping-Criterion. Braucht `serp_results` über mehrere Läufe, also
   genau die Daten, die das Skelett schon erhebt.
3. **Export nach BibTeX/RIS** für die Übernahme in Zotero.
4. **LLM-gestütztes Screening** — ausdrücklich Nicht-Ziel, aber das Datenmodell ist
   vorbereitet: eine Tabelle `screenings(document_id, run_id, verdict, rationale)` würde
   genügen, ohne Bestehendes anzufassen.
5. ~~**`CITATION.cff` und Zenodo-DOI**~~ — überholt. Zitiert wird ReviQ (SoftwareX 35, 2026, `10.1016/j.softx.2026.102814`); der Abruf ist ein Teil davon.
6. **Deduplizierung über Near-Duplicates** (SimHash/MinHash) — exakte SHA-256-Gleichheit
   findet nur identische Bytes; dieselbe Pressemitteilung auf drei Portalen bleibt
   dreimal drin.

---

## 12. Definition of Done

```bash
export SEARCHAPI_API_KEY=...  SCRAPINGBEE_API_KEY=...
uv run glr init
uv run glr run "AI maturity assessment model" --pages 5 --out results.csv
```

Erwartetes Ergebnis:
- `results.csv` mit ~50 Zeilen und den Spalten aus §8
- `data/runs/<run_id>/snapshots.warc.gz` mit den Rohinhalten
- `data/glr.sqlite3` mit fünf befüllten Tabellen
- ein zweiter identischer Aufruf erzeugt einen zweiten `run_id` — **und keine doppelten
  `documents`**

Kein Feature darüber hinaus.
