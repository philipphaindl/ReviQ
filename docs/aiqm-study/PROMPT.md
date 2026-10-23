# Prompt: LLM-gestützte, validierte Herleitung eines Qualitätsmodells für KI-Einführung in Organisationen (ReviQ + Grey Literature)

Stand: 23.10.2026 · Autoren: Philipp Haindl, Oliver Eigner · Arbeitstitel des Modells: `<MODELLNAME>` (erst nach Markenprüfung festlegen)

**Verwendung:** Dieses Dokument im ReviQ-Repo als `docs/aiqm-study/PROMPT.md` ablegen und Claude Code damit starten: "Lies docs/aiqm-study/PROMPT.md vollständig und beginne mit WP0." Teil A ist der Arbeitsauftrag, Teile B-F sind die verbindliche fachliche Grundlage, auf die Teil A verweist.

---

## Teil A - Auftrag an Claude Code

### A.1 Kontext

ReviQ (`github.com/philipphaindl/reviq`, SoftwareX 35, 102814) ist das System of Record dieser Studie. Es kann bereits:

- SLR und MLR nach Kitchenham & Charters bzw. Garousi et al. mit 8 Phasen und PRISMA 2020 (eigene Spalte für Grey Literature)
- Grey-Retrieval über `python -m app.retrieval` ("creel"): SearchApi.io bzw. arXiv als Suchmaschine, ScrapingBee für den Abruf, WARC-Archiv mit SHA-256, Zugriffsprotokoll, Query-Set als TOML
- bis zu 5 Reviewer (R1-R5), Entscheidungsaustausch als JSON (`POST /api/projects/{id}/import/reviewer-decisions`), Konflikterkennung, Cohen's κ mit 95%-KI und PABAK
- QA-Schema (0/0.5/1), Extraktionsschema, Snowballing, deterministisches Replication Package

Es fehlt alles LLM-Gestützte: Suchstring-Bewertung, Screening- und Extraktions-Judges, Mehr-Rater-Statistik (Krippendorffs α, Gwet's AC1, MCC), Abstraktion zu einem Modell, Sättigung und Traceability. Das baust du.

### A.2 Architekturentscheidung

- Neues Paket `backend/app/judging/` als **CLI analog zu creel** (`python -m app.judging <command>`). Kommando statt Button, weil Läufe Geld kosten und als Protokoll zitierbar sein müssen.
- **ReviQ bleibt unverändert in seinem Verhalten.** Die Judges sind normale Reviewer (R3, R4, R5) und speisen ihre Entscheidungen über das bestehende JSON-Austauschformat ein (`reviewer_name`, `reviewer_role`, `decisions[]` mit `paper_citekey`, `phase`, `decision` I/E/U, `criterion_label`, `rationale`). R1 = Philipp, R2 = Oliver.
- Alles, was ReviQs Datenmodell nicht abbildet (Kandidatenaussagen, Cluster, Modellhierarchie, LLM-Cache), kommt in eigene Tabellen mit Migration. Bestehende Tabellen nur lesen.
- Die Studie ist ein ReviQ-Projekt vom Typ **multivocal**.

### A.3 Grundsätze (nicht verhandelbar)

1. **Determinismus und Nachvollziehbarkeit.** Jeder LLM-Aufruf wird mit Hash über (Modell-ID, Parameter, Prompt-Version, Input) im Cache gespeichert, inklusive Rohantwort, Zeitstempel und Kosten. Ein erneuter Lauf ohne API-Key reproduziert alle Ergebnisse aus dem Cache. Der Cache ist Teil des Replication Package.
2. **Prompts sind versionierte Dateien** (`judging/prompts/*.md` mit Versionsnummer im Frontmatter). Nach dem Freeze (Gate G2) ändert sich keine Prompt-Datei mehr. Jede spätere Änderung ist eine dokumentierte Protokollabweichung.
3. **Modell-IDs exakt pinnen** (keine Aliase wie "latest"). Mindestens drei Judges aus drei verschiedenen Modellfamilien, davon eines open-weight und lokal (Ollama). Kein Judge bewertet Text, den ein Modell derselben Familie erzeugt oder zusammengefasst hat.
4. **API-Keys nur aus der Umgebung**, nie in DB, Logs oder Fehlermeldungen. `app/retrieval/redact.py` wiederverwenden.
5. **Jede Zahl im Paper wird von Code erzeugt**, nicht von Hand übertragen. `python -m app.judging report` erzeugt alle Tabellen und Abbildungen (CSV, LaTeX, SVG).
6. **Kosten vor Ausführung zeigen.** Jedes kostenpflichtige Kommando hat `--dry-run` mit Schätzung (Anzahl Aufrufe, Tokens, Credits).
7. **Statistik nicht selbst erfinden.** Etablierte Bibliotheken verwenden (z. B. `krippendorff`, `scikit-learn` für MCC/ARI/F1, `irrCAC` oder geprüfte Eigenimplementierung für Gwet's AC1 mit Tests gegen publizierte Beispielwerte). Bootstrap-KIs mit festem Seed.
8. **Tests:** jede Statistikfunktion gegen bekannte Referenzwerte, jeder Translator für Suchstrings gegen Golden Files, Cache-Roundtrip, Replikation aus dem Cache. Bestehende Tests müssen grün bleiben.
9. **Eskalation:** Strategische oder inhaltliche Entscheidungen (Schwellwerte ändern, Kriterien umformulieren, Ausgangsmodelle ändern, Ergebnisse interpretieren) triffst du nicht selbst. Du hältst an, beschreibst die Optionen knapp und wartest. Mechanische Entscheidungen triffst du selbst und listest sie im Änderungsprotokoll.
10. **Abrechnung: API für alle Studienläufe, Abo nur für die Entwicklung.**
    - Alle Judge-Aufrufe im Code laufen ausschließlich über die Claude API (API-Key aus der Umgebung) bzw. die APIs der anderen Anbieter und das lokale Open-Weight-Modell. Kein Aufruf der Claude-Code-CLI (`claude -p`) und kein Agent SDK mit claude.ai-Login als Judge-Backend, auch nicht optional. Begründung: gepinnte Modelle, kontrollierte Parameter und rohe Ein-/Ausgaben ohne zusätzlichen System-Prompt sind Voraussetzung für die Reproduzierbarkeit; zudem erlauben die Anthropic-Bedingungen keinen claude.ai-Login in Drittanwendungen.
    - Wo die Anbieter-API Batch-Verarbeitung anbietet, nutzt du sie für Hauptläufe (Screening, Extraktion) und weist den Kostenunterschied im `--dry-run` aus.
    - Die Entwicklung des Judging-Moduls und die interaktive Prompt-Entwicklung bis zum Freeze (G2) laufen über Philipps Claude-Abo in Claude Code. Alles, was in Kennzahlen des Papers eingeht, stammt aus API-Läufen ab dem Freeze.

### A.4 Arbeitspakete

Jedes WP endet mit: kurze Zusammenfassung, geänderte Dateien, Testergebnis, nächster Schritt. Gates (G) brauchen eine explizite Freigabe von Philipp.

**WP0 - Bestandsaufnahme und Plan**
- Repo, `CLAUDE.md`, Datenmodell, Migrationen, creel und Entscheidungsimport lesen.
- Implementierungsplan für WP1-WP9 als `docs/aiqm-study/PLAN.md`, inklusive Kostenschätzung (Größenordnung) und Liste der benötigten Keys.
- Suchsyntax der Datenbanken (Teil C.3) gegen die offizielle Hilfe der Anbieter prüfen und Abweichungen melden. Nichts aus dem Gedächtnis übernehmen.

**WP1 - Protokoll-Skelett**
- `docs/aiqm-study/protocol.md` aus Teil B und C erzeugen, mit Platzhaltern für alles, was erst nach der Kalibrierung feststeht.
- ReviQ-Projekt anlegen (multivocal), Ein-/Ausschlusskriterien mit `short_label`, QA-Kriterien, Reviewer R1-R5.
- **G0:** Protokoll freigeben, auf OSF oder Zenodo mit Zeitstempel ablegen (Philipp).

**WP2 - Quasi-Gold-Standard (QGS) und Suchstring-Judge**
- QGS-Kandidaten importieren: Quellen der Ausgangsmodelle (B.4) und der bekannten Reviews (Teil D), dazu die Referenzliste aus Teil F. Metadaten über OpenAlex anreichern.
- QGS deterministisch (Seed) in **Dev (60 %)** und **Holdout (40 %)** teilen. Der Holdout wird bis zum Freeze nicht angefasst.
- Suchstrings aus einer kanonischen Darstellung erzeugen (Konzeptblöcke in `search/concepts.toml`) und pro Datenbank übersetzen (Translator mit Golden-File-Tests).
- Suchstring-Judge (Details C.4): Kandidaten erzeugen, objektiv bewerten (lokale Boolesche Auswertung auf QGS-Dev, Trefferzahl über OpenAlex `meta.count`, Präzisionsschätzung durch die Jury auf einer Zufallsstichprobe), nach fester Regel auswählen.
- **G1:** Suchstrings freigeben. Danach einmalig Quasi-Sensitivität auf dem Holdout berichten.

**WP3 - Retrieval**
- Automatisch: OpenAlex (`title_and_abstract.search`, Cursor-Paging) und Semantic Scholar Bulk Search -> BibTeX in `bib_data/db_search/`.
- Manuell (einziger manueller Suchschritt): Exporte aus Scopus, Web of Science, IEEE Xplore, ACM DL mit den freigegebenen Strings. Du erzeugst dafür eine Checkliste mit exakten Strings, Filtern und Exportformat.
- Grey: creel mit dem Query-Set aus C.5 (`--project <id>`), danach `report`, gegebenenfalls `refetch --dry-run`, Import über die Oberfläche bzw. den bestehenden Endpunkt.
- Deduplizierung über ReviQ. Retrieval-Report für den Methodenteil erzeugen.

**WP4 - Screening-Jury**
- `python -m app.judging screen --phase screening --judges J1,J2,J3`
- Jeder Judge liefert pro Record: Entscheidung I/E/U, das maßgebliche Kriterium (`criterion_label`), eine kurze Begründung, Konfidenz 0-1. Ausgabe als Strukturformat (JSON-Schema-validiert); unparsebare Antworten zählen als **U** (wie Include behandelt) und werden gezählt.
- 3 Läufe pro Judge auf der Kalibrierungsstichprobe, um Lauf-zu-Lauf-Stabilität zu messen; im Hauptlauf 1 Lauf pro Judge, bei U oder Konfidenz < 0,6 ein zweiter.
- Entscheidungsregel (recall-first): **Exclude nur bei 3/3 Exclude.** Mindestens ein Include -> Include in die nächste Phase. Uneinigkeit oder U -> menschliche Entscheidung über den bestehenden Konfliktmechanismus.
- Export pro Judge als ReviQ-Decision-JSON und Import als R3-R5.
- Kalibrierung (Details B.6): Prompts auf dem Kalibrierungsset abstimmen, **G2: Prompt-Freeze**, dann Validierung auf der davon getrennten Validierungsstichprobe.
- Audit der einstimmigen Ausschlüsse (B.6, Rule of Three).

**WP5 - Eligibility (Volltext) und QA**
- Gleiche Jury-Logik auf Volltexten (akademisch: OA-PDF über OpenAlex/Unpaywall-Link bzw. manuell abgelegt; grey: creel-Volltext).
- QA: akademisch nach den Kriterien aus C.7, grey nach der Garousi-Checkliste (C.7). Jury schlägt Scores vor, Menschen prüfen eine Stichprobe; Agreement wird berichtet.

**WP6 - Extraktion von Kandidatenaussagen**
- Pro eingeschlossener Quelle extrahieren zwei Judges unabhängig Kandidatenaussagen nach dem Schema in B.5.
- **Span-Verifikation:** Jede Aussage muss eine wörtliche Belegstelle haben, die im archivierten Volltext nach Normalisierung exakt gefunden wird. Nicht auffindbare Belege werden verworfen und als Halluzinationsrate berichtet.
- Abgleich der beiden Judges über Span-Überlappung (IoU ≥ 0,5) -> Präzision/Recall/F1 zwischen Judges; Vereinigungsmenge geht weiter, Einzelfunde werden markiert.
- Menschliche Validierung einer Stichprobe (B.6).

**WP7 - Abstraktion zum FCM-Modell**
- Deduktiv-induktiv: Die Elemente der Ausgangsmodelle bilden das Start-Codebuch; neue Cluster erweitern es.
- Embeddings mit einem lokal gepinnten Open-Source-Modell, deterministisches Clustering (z. B. agglomerativ, Schwellwert auf dem Kalibrierungsset gegen eine menschliche Gruppierung per ARI bestimmt und dann eingefroren).
- Jury benennt Cluster (Label + Definition), Reihenfolge der Beispiele randomisiert und vertauscht (Positionsbias).
- Hierarchie: Kandidaten -> Metriken -> Kriterien -> Dimensionen (FCM, siehe B.3). Evidenzregel für Metriken (B.3).
- Validierung: menschliche Zuordnung einer Stichprobe zu Kriterien (geschlossenes Card Sorting), Bootstrap-Stabilität, Lauf-zu-Lauf-Stabilität (B.6).
- **G3:** Modellentwurf mit Labels und Definitionen fachlich freigeben (Philipp, Oliver).

**WP8 - Sättigung, Abdeckung, Traceability, Regulatorik**
- Sättigungskurve nach Guest et al. (2020) über 100 zufällige Permutationen der Quellreihenfolge (Median und Band).
- Abdeckungsmatrix: Jedes Element jedes Ausgangsmodells -> Kriterium oder "verworfen" mit Grund.
- Traceability: Jede Metrik -> Kriterium -> Dimension mit allen Belegstellen (Quelle, Span, Zugriffszeitpunkt, SHA-256 bei Grey).
- Regulatorischer Crosswalk: Pflichten aus der Verordnung (EU) 2024/1689 (AI Act), ISO/IEC 42001 (Klauseln und Annex-A-Controls), NIST AI RMF (Subkategorien) -> Kriterien. Zwei Judges, menschliche Prüfung einer Stichprobe, nicht abgedeckte Pflichten explizit ausweisen.

**WP9 - Reporting und Replication Package**
- `report`: alle Kennzahlen (B.6), PRISMA 2020 (drei Spalten), Sättigungskurve, Abdeckungs- und Crosswalk-Matrix, Modelltabelle, Related-Work-Vergleichstabelle (aus `docs/aiqm-study/related-work.yaml`, siehe Teil D).
- Checkliste nach Baltes et al. (LLM-Guidelines) ausgefüllt als Anhang.
- Replication Package: ReviQ-Export + LLM-Cache + Prompts + Konfiguration + WARC-Manifest (ohne Volltexte urheberrechtlich geschützter Quellen) + Skripte, versioniert getaggt.

### A.5 Was Menschen tun (bewusst minimal)

| Schritt | Wer | Aufwand (Schätzung) |
|---|---|---|
| G0 Protokoll freigeben und registrieren | Philipp | 1-2 h |
| QGS-Liste gegenlesen | beide | 1 h |
| G1 Suchstrings freigeben, 4 Datenbank-Exporte | Philipp | 1-2 h |
| Kalibrierung Screening (50 Records) | beide unabhängig | je 1 h |
| Validierung Screening (Stichprobe ca. 300) | beide unabhängig | je 4-5 h |
| Audit einstimmiger Ausschlüsse (300) | einer | 3 h |
| Konflikte der Jury entscheiden | einer, Rest nach Bedarf | variabel |
| Extraktion validieren (ca. 100 Aussagen) | beide unabhängig | je 2-3 h |
| Card Sorting Abstraktion (ca. 150 Zuordnungen) | beide unabhängig | je 2-3 h |
| G3 Modell fachlich freigeben | beide | 2-3 h |

---

## Teil B - Forschungsdesign

### B.1 Zuschnitt

- **Beitrag:** ein evidenzbasiert hergeleitetes Qualitätsmodell für die Einführung von KI in Organisationen, dessen **Herleitung** auf jeder Stufe gegen menschliche Codierung validiert ist. Die Anwendung des Modells in Organisationen wird **nicht** evaluiert (explizit Future Work).
- **Struktur:** Factor-Criteria-Metric (McCall et al. 1977), operationalisiert nach Quamoco (Wagner et al. 2015) und GQM (Basili et al. 1994).
- **Keine Gewichte.** Ergebnis ist ein Profil pro Dimension. Innerhalb einer Dimension ungewichteter Mittelwert der Kriterien, über Dimensionen hinweg kein Gesamtscore. Begründung im Paper als Designentscheidung, empirisch fundierte Gewichte sind Future Work.
- **Unabhängigkeit vom Produkt:** Ascios Assess fließt **nicht** als Ausgangsmodell ein. Der Abgleich Assess <-> Modell erfolgt nach der Publikation. Das Competing-Interests-Statement nennt die geplante kommerzielle Nutzung.

### B.2 Forschungsfragen und Beiträge

- **RQ1:** Which dimensions, criteria and metrics characterise the quality of AI adoption in organisations, as derived from existing models and multivocal evidence?
- **RQ2:** How reliable and valid is an LLM-jury-based derivation of such a model compared with human coding, at the stages of search, screening, extraction and abstraction?
- **RQ3:** How completely does the derived model cover existing AI maturity/readiness models and regulatory frameworks (EU AI Act, ISO/IEC 42001, NIST AI RMF), and how traceable is each metric to its evidence?

Beiträge:
- **C1** das Modell (Dimensionen, Kriterien, Metriken mit Messvorschrift und Evidenzgrad)
- **C2** ein stufenweise validiertes, reproduzierbares Verfahren zur LLM-gestützten Modellherleitung aus multivokaler Evidenz
- **C3** Abdeckungs- und Crosswalk-Analyse gegenüber Ausgangsmodellen und Regulatorik
- **C4** offenes Replication Package (ReviQ-Projekt, LLM-Cache, Prompts)

### B.3 Modellstruktur (FCM)

| Ebene | Definition | Quelle der Ableitung |
|---|---|---|
| Dimension (Factor) | Qualitätsmerkmal der KI-Einführung aus Sicht der Organisation | Clusterung der Kriterien, verankert an den Dimensionen der Ausgangsmodelle |
| Kriterium (Criterion) | beobachtbare Eigenschaft, die zur Dimension beiträgt | Clusterung der Kandidatenaussagen |
| Metrik (Metric) | Messvorschrift mit Skala (ordinal 0-4 mit verbalen Ankern, binär oder quantitativ), Messmethode, Datenquelle | Kandidaten vom Typ "metric/indicator", formuliert nach GQM |

Evidenzregel: Eine Metrik wird nur aufgenommen, wenn sie von **mindestens zwei unabhängigen Quellen** gestützt ist, davon mindestens eine akademisch oder Grey mit QA-Level "high". Evidenzgrad A-D aus Anzahl und Qualität der Quellen (Regel im Protokoll festlegen).

### B.4 Ausgangsmodelle (Seed)

Auswahlkriterien: öffentlich zugänglich, Gegenstand ist die KI-Einführung bzw. KI-Fähigkeit von Organisationen (nicht einzelne KI-Systeme), explizite Struktur (mindestens Dimensionen), ab 2018.

Vorschlag (Endauswahl in G0):
- akademisch: Jöhnk et al. 2021 (BISE), Hansen et al. 2024 (ISF), Fukas et al. 2021 (ECIS), Akbarighatar 2022 (MCIS), Holmström 2022 (Business Horizons), Heger et al. 2025 (PACM HCI/CSCW), Dreyling et al. 2024 (Public Sector)
- Praxis/Standards: MITRE AI Maturity Model (2023), Microsoft Cloud Adoption Framework AI, Google Cloud AI Adoption Framework (2020), AWS CAF-AI (2024), NIST AI RMF 1.0, ISO/IEC 42001:2023
- als Systemqualitäts-Referenz (nicht Seed, aber Abgrenzung): ISO/IEC 25059, Siebert et al. 2022
- Gartner AI Maturity Model nur, wenn öffentlich ausreichend beschrieben, sonst begründet ausschließen

### B.5 Extraktionsschema (Kandidatenaussage)

`statement_id, source_id, evidence_span (wörtlich), span_offsets, candidate_type {dimension | criterion | metric/indicator | practice}, construct_label, polarity {enabler | barrier | indicator}, measurability {quantitative | ordinal | binary | qualitative}, measurement_method (falls genannt), org_context {SME | large | public | any}, lifecycle_phase, regulatory_reference (falls genannt), evidence_type {empirical | case | experience report | opinion | standard}`

Faktische Felder (bibliografisch, Quellentyp) werden mit Stichproben geprüft. Interpretative Felder (`candidate_type`, `construct_label`, `measurability`) werden immer menschlich auf einer Stichprobe validiert, weil LLM-Extraktion dort deutlich schlechter ist und Werte erfindet (Felizardo et al. 2024).

### B.6 Validierung der Herleitung - Kennzahlen und Schwellwerte

Schwellwerte a priori im Protokoll; Abweichungen werden berichtet, nicht stillschweigend angepasst.

| Stufe | Vergleich | Kennzahlen | Schwellwert (Vorschlag) |
|---|---|---|---|
| Suche | Strings vs. QGS-Holdout | Quasi-Sensitivität (Zhang et al. 2011), Trefferzahl, geschätzte Präzision | Quasi-Sensitivität ≥ 0,80 |
| Gold-Standard | R1 vs. R2 | Cohen's κ, Krippendorffs α, PABAK | α ≥ 0,667, sonst Codierregeln schärfen |
| Screening | Jury-Regel vs. Gold | Recall, Präzision, F1, **MCC**, volle Konfusionsmatrix, Work Saved | Recall ≥ 0,95 |
| Screening | Judge vs. Judge, Lauf vs. Lauf | Krippendorffs α, Gwet's AC1 (schiefe Prävalenz) | berichten |
| Screening | LLM ersetzt Menschen? | Alternative Annotator Test (Calderon et al. 2025) | Test bestanden; Anzahl nötiger Codierer prüfen, ggf. dritte Person |
| Ausschluss-Audit | einstimmige Excludes, Zufallsstichprobe n = 300 | gefundene Includes | 0 Treffer -> obere 95%-Grenze der Fehlerrate ca. 1 % (Rule of Three) |
| Extraktion | Span-Verifikation | Anteil verifizierter Belege, Halluzinationsrate | alle unverifizierten verworfen und gezählt |
| Extraktion | Judge vs. Mensch (Stichprobe ca. 100) | Feldgenauigkeit, κ pro interpretativem Feld | ≥ 0,80 Genauigkeit bzw. α ≥ 0,667 |
| Abstraktion | Pipeline vs. menschliches Card Sorting (ca. 150) | Krippendorffs α, ARI | α ≥ 0,667 |
| Abstraktion | Bootstrap über Quellen (n = 200), Lauf vs. Lauf | ARI (Median, 95%-Band) | im Protokoll festlegen und begründen |
| Sättigung | neue Kriterien pro Block | Guest et al. 2020 (Base Size, Run Length, Schwelle) | ≤ 5 % neue Kriterien über zwei Blöcke |
| Abdeckung | Seed-Elemente | Anteil abgedeckt / verworfen mit Grund | 100 % zugeordnet |

Stichproben:
- **Kalibrierung** (Prompt-Entwicklung): 50 Records, geschichtet akademisch/grey; danach verbrannt.
- **Validierung:** ca. 300 Records, geschichtet nach Strom (akademisch/grey) und nach Jury-Ergebnis (einstimmig I, einstimmig E, gemischt), damit Recall nicht nur auf einfachen Fällen gemessen wird. Kalibrierung und Validierung sind disjunkt.
- Gold-Standard = unabhängige Codierung R1/R2, Uneinigkeiten im Gespräch aufgelöst und dokumentiert.

### B.7 Reporting

- PRISMA 2020 mit drei Spalten (Datenbanken, Snowballing, Grey), wie ReviQ sie erzeugt
- Garousi et al. (2019) für Grey: Suchmaschine, Ländereinstellung, Seitenzahl, Stoppkriterium, Zugriffsprotokoll; der ScrapingBee-Hinweis aus `creel report` geht wörtlich in den Methodenteil
- Baltes et al. (EMSE 2026, accepted): Rolle der LLMs, Modellversionen, Konfiguration, Prompts, Traces, Baselines, Open-Weight-Modell, Validierung gegen Menschen, Limitationen
- Madeyski, Kitchenham, Shepperd (2025): Recall priorisieren, MCC statt Accuracy, Konfusionsmatrix, Nicht-LLM-Baseline (z. B. TF-IDF + logistische Regression auf dem Kalibrierungsset)

### B.8 Threats to Validity (Gerüst)

Gliederung nach Ampatzoglou et al. (2019) für Sekundärstudien plus LLM-spezifische Bedrohungen:
- **Studienauswahl:** Suchstring-Bias (QGS-Holdout), fehlende Datenbanken, Grey-Bias durch Suchmaschinenranking und kommerzielle Interessen der Quellen (QA nach Garousi)
- **Datenvalidität:** Halluzination (Span-Verifikation), Nichtdeterminismus (Lauf-zu-Lauf-Stabilität, Cache), Self-Preference (Jury aus verschiedenen Familien), Positionsbias (Randomisierung), Datenkontamination (Modelle kennen evtl. die Quellen; Effekt auf die Herleitung diskutieren)
- **Forschungsvalidität:** Abstraktion als interpretativer Schritt (Card Sorting, Bootstrap), Autoren als einzige Codierer, Interessenkonflikt durch geplante kommerzielle Nutzung (offengelegt, Assess nicht als Seed)
- **Generalisierbarkeit:** nur Herleitung validiert, keine Anwendung in Organisationen

---

## Teil C - Suchstrategie

### C.1 Konzeptblöcke (kanonisch, `search/concepts.toml`)

- **A - KI:** "artificial intelligence", "machine learning", "generative AI", "GenAI", "large language model(s)", "AI system(s)"
- **O - Organisation/Einführung:** adoption, implementation, deployment, integration, governance, readiness, maturity, capability/capabilities, transformation
- **M - Modellartefakt:** "maturity model", "readiness model", "maturity assessment", "readiness assessment", "capability model", "quality model", "assessment framework", "assessment model", "maturity framework", "readiness framework", "adoption framework", "governance framework"
- **E - Evidenz zu Faktoren/Metriken:** "success factor(s)", "critical factor(s)", barrier(s), enabler(s), "best practice(s)", "lessons learned", metric(s), "key performance indicator(s)", KPI(s), measurement
- **K - Kontext:** organisation/organization, enterprise, firm, company, "public sector", SME, business

Zwei Strings:
- **S1 (Modelle, präzise):** A nahe O, UND M
- **S2 (Evidenz, breit):** A nahe Einführungsbegriffe, UND K, UND E

Zeitraum 2018-2026, Englisch, Dokumenttypen Artikel, Konferenzbeitrag, Review. Wenn S2 laut OpenAlex-Zählung über ca. 8.000 Records liegt, entscheidet G1 über Eingrenzung (dokumentiert).

### C.2 Ausgangsstrings (werden in WP2 vom Suchstring-Judge verbessert)

**Scopus S1**
```
TITLE-ABS-KEY ( ( "artificial intelligence" OR "machine learning" OR "generative AI" OR "large language model*" OR "AI system*" ) W/5 ( maturity OR readiness OR adoption OR implementation OR governance OR capabilit* ) )
AND TITLE-ABS-KEY ( "maturity model*" OR "readiness model*" OR "maturity assessment*" OR "readiness assessment*" OR "capability model*" OR "quality model*" OR "assessment framework*" OR "assessment model*" OR "maturity framework*" OR "readiness framework*" OR "adoption framework*" OR "governance framework*" )
AND PUBYEAR > 2017 AND ( LIMIT-TO ( LANGUAGE , "English" ) )
```

**Scopus S2**
```
TITLE-ABS-KEY ( ( "artificial intelligence" OR "machine learning" OR "generative AI" OR "large language model*" ) W/3 ( adoption OR implementation OR deployment OR integration OR governance ) )
AND TITLE-ABS-KEY ( organi?ation* OR enterprise* OR firm OR firms OR compan* OR "public sector" OR SME* OR business* )
AND TITLE-ABS-KEY ( "success factor*" OR "critical factor*" OR barrier* OR enabler* OR "best practice*" OR "lessons learned" OR metric* OR "key performance indicator*" OR KPI* OR measur* )
AND PUBYEAR > 2017
```

**Web of Science S1** (NEAR-Gruppen ohne AND, Vorrang NEAR vor AND beachten)
```
TS=( ( "artificial intelligence" OR "machine learning" OR "generative AI" OR "large language model*" OR "AI system*" ) NEAR/5 ( maturity OR readiness OR adoption OR implementation OR governance OR capabilit* ) )
AND TS=( "maturity model*" OR "readiness model*" OR "maturity assessment*" OR "readiness assessment*" OR "capability model*" OR "quality model*" OR "assessment framework*" OR "assessment model*" OR "maturity framework*" OR "readiness framework*" OR "adoption framework*" OR "governance framework*" )
AND PY=(2018-2026)
```

**OpenAlex S1** (keine Wildcards, keine Proximity, Stemming aktiv; keine Kommas im Suchtext)
```
https://api.openalex.org/works?filter=title_and_abstract.search:("artificial intelligence" OR "machine learning" OR "generative AI" OR "large language model") AND ("maturity model" OR "readiness model" OR "maturity assessment" OR "readiness assessment" OR "capability model" OR "quality model" OR "assessment framework" OR "maturity framework" OR "readiness framework" OR "adoption framework" OR "governance framework"),publication_year:>2017&per-page=200&cursor=*
```

**IEEE Xplore, ACM DL, Semantic Scholar:** werden vom Translator aus C.1 erzeugt. Vorgaben: IEEE über `"All Metadata"` (Titel, Abstract, Index Terms, kein Volltext), Singular/Plural ausschreiben statt Wildcards in Phrasen, Limit an Suchbegriffen und Wildcards gegen die IEEE-Hilfe prüfen und S1 bei Bedarf in Teilabfragen splitten; ACM über Titel, Abstract und Keywords (nicht AllField), "Guide to Computing Literature" dokumentieren; Semantic Scholar Bulk-Syntax (`+`, `|`, `-`, Phrasen) vor Nutzung verifizieren und `+` URL-kodieren. SpringerLink nicht direkt (keine Abstract-Feldsuche), Abdeckung über Scopus/WoS/OpenAlex.

### C.3 Prüfauftrag Syntax

Vor G1 prüft Claude Code jede Syntax gegen die offizielle Anbieterhilfe (Scopus Advanced Search, WoS Search Rules, IEEE Command Search, ACM Advanced Search, OpenAlex Docs, Semantic Scholar API Docs) und protokolliert die geprüfte Version mit URL und Datum. Bekannte Fallstricke: Scopus-Operatorvorrang (OR vor W/n vor AND), WoS-Vorrang (NEAR vor AND), IEEE-Limits, OpenAlex verwirft `*`, `?`, `~` stillschweigend.

### C.4 Suchstring-Judge (vor der eigentlichen Suche)

Ziel: die Auswahl der Suchstrings ist ein gemessenes Optimierungsergebnis, kein Bauchgefühl.

1. **Begriffsernte:** objektiv (Häufigkeiten von Titel-, Abstract- und Author-Keyword-Termen im QGS-Dev, TF-IDF gegen eine Zufallsstichprobe aus OpenAlex) plus Vorschläge der Jury. Jury-Vorschläge zählen nur, wenn sie im QGS-Dev mindestens einmal vorkommen.
2. **Kandidaten:** systematische Varianten (Block-Ablation: jeder Block weggelassen bzw. erweitert, Proximity 3/5/10) plus maximal 10 Jury-Vorschläge.
3. **Bewertung pro Kandidat:**
   - Quasi-Sensitivität auf QGS-Dev durch lokale Boolesche Auswertung über Titel, Abstract, Keywords (deterministisch, kostenlos)
   - Trefferzahl über OpenAlex `meta.count` (als Schätzung; Abweichung zu Scopus ist bekannt und wird nicht als exakt berichtet)
   - Präzisionsschätzung: Jury beurteilt 50 zufällige Treffer pro Kandidat auf Relevanz (Mehrheitsentscheid)
4. **Auswahlregel:** maximale geschätzte Präzision unter den Nebenbedingungen Quasi-Sensitivität(Dev) ≥ 0,90 und Trefferzahl ≤ Budget. Bei Gleichstand der kürzere String.
5. **Einmalig nach Freeze:** Quasi-Sensitivität auf dem Holdout berichten. Liegt sie unter 0,80, ist das eine Protokollabweichung, die G1 neu öffnet.

Wang et al. (2023) zeigen, dass LLM-generierte Boolesche Strings Präzision zulasten des Recalls bevorzugen. Deshalb entscheidet die Messung, nicht die Jury.

### C.5 Grey Literature - Query-Set für creel

Nur die zwölf von creel akzeptierten Schlüssel verwenden. Stoppkriterium nach Garousi et al. (2019): Effort-bounded (max. 5 Seiten pro Query) und theoretische Sättigung (letzte Seite ohne neue relevante Treffer laut Jury-Vorschau -> keine weiteren Seiten im nächsten Lauf).

```toml
[defaults]
pages = 5
gl = "us"
hl = "en"
render_js = false
snowball_depth = 0
snowball_max_links = 20

[[query]]
q = "AI maturity model enterprise"

[[query]]
q = "AI readiness assessment framework organization"

[[query]]
q = "AI adoption framework enterprise"

[[query]]
q = "generative AI maturity model"

[[query]]
q = "responsible AI maturity model organization"

[[query]]
q = "AI governance maturity assessment"

[[query]]
q = "AI implementation success factors case study"

[[query]]
q = "enterprise AI adoption lessons learned"

[[query]]
q = "AI program KPIs metrics measure success"

[[query]]
q = "AI center of excellence operating model"

[[query]]
q = "ISO 42001 implementation experience"

[[query]]
q = "EU AI Act readiness assessment checklist"

[[query]]
q = "NIST AI RMF implementation organization"

[[query]]
q = "AI maturity model filetype:pdf"

[[query]]
q = "AI adoption survey report enterprise filetype:pdf"

[[query]]
q = "KI Reifegradmodell Unternehmen"
gl = "at"
hl = "de"

[[query]]
q = "KI Einführung Unternehmen Erfolgsfaktoren"
gl = "at"
hl = "de"

[[query]]
q = "AI maturity model"
engine = "arxiv"
pages = 3

[[query]]
q = "AI readiness organizations framework"
engine = "arxiv"
pages = 3
```

Deutsche Queries sind optional: Sie erhöhen die Abdeckung für DACH-Praxisquellen, verlangen aber, dass Ein-/Ausschlusskriterien Deutsch zulassen. Entscheidung in G0.

### C.6 Ein- und Ausschlusskriterien (mit `short_label` für PRISMA)

| Label | Kriterium | short_label |
|---|---|---|
| IC1 | befasst sich mit Einführung, Nutzung, Governance oder Reife von KI in Organisationen | org AI adoption |
| IC2 | enthält ein Modell/Framework oder Aussagen zu Faktoren, Kriterien, Praktiken oder Messgrößen | model or factors |
| IC3 | 2018-2026 | period |
| EC1 | ausschließlich technische Eigenschaften einzelner KI-Systeme ohne Organisationsbezug | system-only |
| EC2 | KI nur als Werkzeug in einer Fachdomäne ohne Aussage zur Einführung | domain application |
| EC3 | kein Volltext zugänglich bzw. Grey-Quelle ohne Inhalt (creel-Ursachen) | no full text |
| EC4 | Sprache weder Englisch (noch Deutsch, falls in G0 zugelassen) | language |
| EC5 | Duplikat oder ältere Version derselben Arbeit | duplicate |
| EC6 | reine Werbung/Produktbeschreibung ohne inhaltliche Aussage (Grey) | marketing |

### C.7 Qualitätsbewertung

- **Akademisch (0/0.5/1):** Ziel klar? Methode beschrieben? Modell/Faktoren hergeleitet statt behauptet? Validierung vorhanden? Limitationen genannt?
- **Grey (0/0.5/1) nach Garousi et al. 2019:** Autorität des Herausgebers, Methodik erkennbar, Objektivität (kein reines Produktmarketing), Datum vorhanden und aktuell, Neuheit, Belege/Quellen angegeben, Outlet-Typ (1st/2nd/3rd tier)
- QA-Level steuert die Evidenzregel (B.3), nicht den Einschluss.

---

## Teil D - Related Work und Abgrenzung

Claude Code legt die Tabelle unten als `docs/aiqm-study/related-work.yaml` an (eine Zeile pro Arbeit, Felder wie die Spalten), damit WP9 sie als LaTeX-Tabelle erzeugt. Vor Einreichung erneut nach Arbeiten ab 2026 suchen (siehe D.5).

### D.1 Cluster

1. **Reviews von AI-Maturity-/Readiness-Modellen:** Sadiq et al. 2021 (15 Studien, keine Metriken, geringe Validierung festgestellt), Akbarighatar 2022 (35 Artikel -> 30 Faktoren, endet bei Faktoren), Akbarighatar et al. 2023 (1.451 Papers per Topic Modeling -> Capability-Framework; methodisch nächster Vorgänger, aber kein LLM, keine Metriken), Sun 2026 (36 Modelle; Governance und Ökosystem unterrepräsentiert), Reichl & Gruenbichler 2023
2. **Einzelmodelle für Organisationen:** Jöhnk et al. 2021 (25 Interviews, Readiness-Faktoren mit Indikatoren), Holmström 2022 (konzeptionell), Mikalef & Gupta 2021 (AI Capability, Survey), Hansen et al. 2024 (TOE, 3 Dimensionen, 3 Fälle), Fukas et al. 2021 (Audit-Domäne), Heger et al. 2025 (RAI, 90 Expert:innen, 24 Dimensionen), Reuel et al. 2024, Dreyling et al. 2024 (öffentlicher Sektor), Tehrani et al. 2024, Uren & Edwards 2023, Ferreira et al. 2025 (Pilot), Witkowski & Wodecki 2026 (GenAI, LLM-Agenten bewerten, leiten aber nicht her), TAIMM 2026 (Fragen auf AI Act gemappt)
3. **Praxis und Standards:** MITRE AI MM 2023 (Profil pro Säule ohne Gesamtscore), Microsoft/Google/AWS Adoption Frameworks, NIST AI RMF 1.0, ISO/IEC 42001
4. **Qualitätsmodelle für KI-Systeme:** ISO/IEC 25059 (Edition 2 im FDIS-Stadium, Edition angeben), Siebert et al. 2022 (Quamoco bis zu Messgrößen, aber Objekt ist das System), Xia et al. 2024 (MLR -> Metrikkatalog, nur Accountability)
5. **LLM-gestützte Konstruktion von Taxonomien/Modellen:** Motamedi et al. 2026 (BISE, LLM-Taxonomie aus bestehenden Taxonomien, F1 statt Agreement; **wichtigster Methoden-Konkurrent**), Shah et al. 2023 (LLM-Taxonomie mit κ gegen Menschen), TaxoAdapt, TaxoAlign, Preßler et al. 2026 (LLM bewertet Reife, leitet nicht her)
6. **AI Governance:** Papagiannidis et al. 2025, Batool et al. 2025 (Grey explizit ausgeschlossen), Birkstedt et al. 2023, Mäntymäki et al. 2022, Lu et al. 2024 (MLR -> Pattern-Katalog), Schneider et al. 2023
7. **LLMs in Sekundärstudien (Methodenbasis):** Thode et al. 2025, Huotala et al. 2024/2026, Felizardo et al. 2024, Khraisha et al. 2024, Madeyski et al. 2025, Hida et al. 2026, Calderon et al. 2025, Verga et al. 2024, Panickssery et al. 2024

### D.2 Vergleichstabelle (Spalten für das Paper)

| Arbeit | Objekt | Evidenzbasis | Herleitung | Tiefe | Validierung Herleitung | Validierung Anwendung | Traceability zu Quellen | Regulatorik-Mapping |
|---|---|---|---|---|---|---|---|---|
| Sadiq et al. 2021 | Org | akad. + wenig grey, 15 | manuell | Review | - | - | - | - |
| Akbarighatar et al. 2023 | Org (RAI) | akad., 1.451 | Topic Modeling + manuell | Capabilities | - | - | - | - |
| Jöhnk et al. 2021 | Org | Interviews (25) | qualitativ | Faktoren + Indikatoren | - | - | - | - |
| Hansen et al. 2024 | Org | Lit. + 5 Interviews | manuell | Dimensionen/Level | - | 3 Fälle | - | - |
| Heger et al. 2025 | Org (RAI) | 90 Expert:innen | Co-Design | Dimensionen | - | - | - | - |
| Siebert et al. 2022 | ML-System | Workshops, Fälle | manuell (Quamoco) | bis Messgröße | - | 3 Fälle | - | - |
| Xia et al. 2024 | RAI-Accountability | MLR | manuell | Metriken | - | - | teilweise | - |
| TAIMM 2026 | Org (Trustworthy AI) | n. b. | manuell | Fragen | - | n. b. | - | AI Act |
| MITRE 2023 | Org | Praxis | n. b. | 20 Dimensionen, 1 Item | - | - | - | - |
| Motamedi et al. 2026 | Patent-Taxonomie | bestehende Taxonomien | LLM (GPT-4) | Taxonomie | F1 vs. manuell | - | - | - |
| **Diese Arbeit** | **Org** | **MLR akad. + grey, groß** | **LLM-Jury + Mensch** | **bis Metrik** | **κ/α, Recall vs. QGS, ARI, Sättigung** | **- (Future Work)** | **ja, Span + Hash** | **AI Act, ISO 42001, NIST** |

Werte mit "n. b." (nicht bestätigt) vor der Einreichung am Volltext prüfen.

### D.3 Novelty-Claim (Formulierung)

> To the best of our knowledge, no prior work derives an organisational AI adoption model down to the level of measurable metrics from a multivocal evidence base using an LLM jury, quantifies the validity of that derivation at every stage against human coding, and keeps every metric traceable to archived source evidence.

### D.4 Was wir **nicht** behaupten dürfen

- erstes Modell mit Regulatorik-Mapping (TAIMM, RAI Question Bank, Reuel et al.)
- erstes Profil ohne Gesamtscore (MITRE)
- erste LLM-gestützte Taxonomie- oder Modellbildung (Motamedi et al. 2026, Shah et al.)
- erste MLR, die Metriken liefert (Xia et al. 2024)
- erstes groß angelegtes, automatisiertes Review zu dem Thema (Akbarighatar et al. 2023)
- Neuheit liegt ausschließlich in der **Kombination**; die Validierung der Herleitung ist der Kern von C2. Dass Konkurrenten ihre Modelle in der Anwendung validieren und wir nicht, wird offen als Scope-Grenze benannt.

### D.5 Vor Einreichung prüfen

- arXiv:2608.01592 ("How Well Do LLMs Generate Taxonomies in the SE Domain?") lesen und einordnen
- ESEM/ICSE-WSESE 2026: weitere LLM-gestützte Mapping Studies
- TAIMM: Autoren, Band, Artikelnummer
- ISO/IEC 25059: gültige Edition
- neue AI-Maturity-Reviews seit Okt. 2026 (Suchalarm in Scopus/Google Scholar setzen)

---

## Teil E - Venue und Paper-Gerüst

### E.1 Empfehlung

- **Primär: Information and Software Technology (Elsevier, hybrid).** Passt zum stärksten Beitrag (validierte LLM-gestützte Herleitung, FCM als SE-Konstrukt). IST hat zuletzt genau solche Arbeiten veröffentlicht (Thode et al. 2025 zur LLM-Auswahl in Sekundärstudien). Closed Access kostet nichts; ob die Elsevier-KEMÖ-Vereinbarung für die USTP gilt und 2027 verlängert wird, bei der Bibliothek klären. Rahmung: "quality model derivation" und "review methodology", nicht "Management-Thema".
- **Fallback 1: IEEE Access.** Schnell, breiter Scope. Die USTP ist Partner der IEEE-Austria-Vereinbarung (Annahmen 2025-2027); Titelliste und Restkontingent bei der Bibliothek prüfen, dann ist die APC voraussichtlich gedeckt.
- **Fallback 2: Information Systems Frontiers (Springer, hybrid, kein Discover).** Wenn das Paper stärker als IS-Thema gerahmt werden soll; Springer-KEMÖ deckt OA.
- Nicht empfohlen: BISE (Reviewer erwarten Anwendungsevaluation), EMSE, TFSC, I&M.

### E.2 Paper-Gerüst (IST)

1. Introduction (Problem: viele Modelle, wenig Messbarkeit, kaum nachvollziehbare Herleitung; RQs; Beiträge)
2. Background (Maturity- vs. Qualitätsmodelle, FCM/Quamoco/GQM; LLMs in Sekundärstudien)
3. Related Work (Cluster D.1, Tabelle D.2, Abgrenzung D.3)
4. Research Method (Becker et al. 2009 als Rahmen, MLR nach Garousi, Jury-Pipeline, Validierungsdesign B.6)
5. Results RQ2: Validity of the Derivation (Suche, Screening, Extraktion, Abstraktion, Sättigung)
6. Results RQ1: The Model (Dimensionen, Kriterien, Metriken, Evidenzgrade)
7. Results RQ3: Coverage, Traceability and Regulatory Crosswalk
8. Discussion (Implikationen für Forschung und Praxis, Vergleich mit bestehenden Modellen, warum keine Gewichte)
9. Threats to Validity (B.8)
10. Conclusion and Future Work (Anwendungsevaluation, empirische Gewichte, Itemvalidierung)
- Data Availability: Replication Package (Zenodo), Protokoll (OSF)
- Declaration of Competing Interests: "The authors intend to commercially apply the proposed model through a company they are in the process of founding." (Firmenname erst nach Eintragung und Markenprüfung)

Hinweis: RQ2 vor RQ1 zu berichten ist Absicht. Erst die Validität der Herleitung, dann das Ergebnis.

---

## Teil F - Literatur

Status: **[v]** = Metadaten auf einer Verlags-, DOI-, Repositoriums- oder arXiv-Seite bestätigt; **[p]** = vor Einreichung prüfen (Details in Klammern). Claude Code erzeugt daraus `refs.bib` und gleicht jede DOI noch einmal ab, bevor sie ins Paper geht.

### Methodik - Reviews und Statistik
- [v] Kitchenham, B., Charters, S. (2007). Guidelines for performing Systematic Literature Reviews in Software Engineering, v2.3. EBSE Technical Report EBSE-2007-01.
- [v] Garousi, V., Felderer, M., Mäntylä, M. V. (2019). Guidelines for including grey literature and conducting multivocal literature reviews in software engineering. IST 106, 101-121. doi:10.1016/j.infsof.2018.09.006
- [v] Zhang, H., Babar, M. A., Tell, P. (2011). Identifying relevant studies in software engineering. IST 53(6), 625-637. doi:10.1016/j.infsof.2010.12.010
- [v] Wohlin, C. (2014). Guidelines for snowballing in systematic literature studies and a replication in software engineering. EASE '14, Art. 38. doi:10.1145/2601248.2601268
- [p] Petersen, K., Vakkalanka, S., Kuzniarz, L. (2015). Guidelines for conducting systematic mapping studies in software engineering: An update. IST 64, 1-18. doi:10.1016/j.infsof.2015.03.007 (Band 64 vs. 65)
- [p] Page, M. J. et al. (2021). The PRISMA 2020 statement. BMJ 372, n71. doi:10.1136/bmj.n71 (Band)
- [v] Ampatzoglou, A., Bibi, S., Avgeriou, P., Verbeek, M., Chatzigeorgiou, A. (2019). Identifying, categorizing and mitigating threats to validity in software engineering secondary studies. IST 106, 201-230. doi:10.1016/j.infsof.2018.10.006
- [v] Cruzes, D. S., Dybå, T. (2011). Recommended steps for thematic synthesis in software engineering. ESEM 2011, 275-284. doi:10.1109/ESEM.2011.36
- [v] Guest, G., Namey, E., Chen, M. (2020). A simple method to assess and report thematic saturation in qualitative research. PLOS ONE 15(5). doi:10.1371/journal.pone.0232076
- [v] Cohen, J. (1960). A coefficient of agreement for nominal scales. EPM 20(1), 37-46. doi:10.1177/001316446002000104
- [v] Krippendorff, K. (2018). Content Analysis: An Introduction to Its Methodology, 4th ed. SAGE.
- [v] Krippendorff, K. (2011). Computing Krippendorff's Alpha-Reliability. Annenberg School for Communication, University of Pennsylvania.
- [p] Hayes, A. F., Krippendorff, K. (2007). Answering the call for a standard reliability measure for coding data. Communication Methods and Measures 1(1), 77-89. (DOI 10.1080/19312450709336664)
- [p] Hanley, J. A., Lippman-Hand, A. (1983). If nothing goes wrong, is everything all right? Interpreting zero numerators. JAMA 249(13), 1743-1745. (Rule of Three; komplett prüfen)
- [v] Wohlin, C. et al. (2012). Experimentation in Software Engineering. Springer. doi:10.1007/978-3-642-29044-2

### Methodik - Modellkonstruktion
- [v] Becker, J., Knackstedt, R., Pöppelbuß, J. (2009). Developing maturity models for IT management. BISE 1(3), 213-222. doi:10.1007/s12599-009-0044-5
- [v] de Bruin, T., Freeze, R., Kulkarni, U., Rosemann, M. (2005). Understanding the main phases of developing a maturity assessment model. ACIS 2005, paper 109.
- [v] Pöppelbuß, J., Röglinger, M. (2011). What makes a useful maturity model? ECIS 2011, paper 28.
- [v] Mettler, T. (2011). Maturity assessment models: a design science research approach. IJSSS 3(1/2), 81-98. doi:10.1504/IJSSS.2011.038934
- [v] McCall, J. A., Richards, P. K., Walters, G. F. (1977). Factors in Software Quality, Vol. I. RADC-TR-77-369.
- [v] ISO/IEC 25010:2023. SQuaRE - Product quality model.
- [v] ISO/IEC 25059:2023. SQuaRE - Quality model for AI systems. (Revision im FDIS-Stadium)
- [p] Basili, V. R., Caldiera, G., Rombach, H. D. (1994). The Goal Question Metric approach. Encyclopedia of Software Engineering, Wiley. (Seiten)
- [v] Wagner, S. et al. (2015). Operationalised product quality models and assessment: The Quamoco approach. IST 62, 101-123. doi:10.1016/j.infsof.2015.02.009
- [v] Nickerson, R. C., Varshney, U., Muntermann, J. (2013). A method for taxonomy development and its application in information systems. EJIS 22(3), 336-359. doi:10.1057/ejis.2012.26
- [v] Usman, M., Britto, R., Börstler, J., Mendes, E. (2017). Taxonomies in software engineering. IST 85, 43-59. doi:10.1016/j.infsof.2017.01.006
- [v] Kundisch, D. et al. (2022). An update for taxonomy designers. BISE 64(4), 421-439. doi:10.1007/s12599-021-00723-x
- [v] Hevner, A. R., March, S. T., Park, J., Ram, S. (2004). Design science in information systems research. MISQ 28(1), 75-105. doi:10.2307/25148625
- [v] Peffers, K. et al. (2007). A design science research methodology for information systems research. JMIS 24(3), 45-77. doi:10.2753/MIS0742-1222240302
- [v] Venable, J., Pries-Heje, J., Baskerville, R. (2016). FEDS: a framework for evaluation in design science research. EJIS 25(1), 77-89. doi:10.1057/ejis.2014.36

### LLMs in Sekundärstudien und als Judges
- [p] Baltes, S. et al. (2026). Guidelines for empirical studies in software engineering involving large language models. Empirical Software Engineering (accepted); arXiv:2508.15503. (Band/DOI nach Erscheinen)
- [v] Wagner, S., Muñoz Barón, M., Falessi, D., Baltes, S. (2025). Towards evaluation guidelines for empirical studies involving LLMs. WSESE 2025 (ICSE workshop); arXiv:2411.07668.
- [v] Thode, L., Iftikhar, U., Mendez, D. (2025). Exploring the use of LLMs for the selection phase in systematic literature studies. IST 184, 107757. doi:10.1016/j.infsof.2025.107757
- [v] Huotala, A., Kuutila, M., Ralph, P., Mäntylä, M. (2024). The promise and challenges of using LLMs to accelerate the screening process of systematic reviews. EASE 2024, 262-271. doi:10.1145/3661167.3661172
- [v] Huotala, A., Kuutila, M., Mäntylä, M. (2026). Has LLM screening performance stalled in software engineering systematic reviews? arXiv:2610.10633.
- [v] Felizardo, K. R. et al. (2024). ChatGPT application in systematic literature reviews in software engineering. ESEM 2024, 25-36. doi:10.1145/3674805.3686666
- [p] Felizardo, K. R. et al. (2024). Data extraction for systematic mapping study using a large language model: a proof-of-concept study in software engineering. ESEM 2024. (DOI)
- [v] Madeyski, L., Kitchenham, B., Shepperd, M. (2025). LLM4SCREENLIT: Recommendations on assessing the performance of large language models for screening literature in systematic reviews. arXiv:2511.12635.
- [v] Hida, G. S., Ribeiro, D. M., Yahata, E. (2026). Beyond accuracy: LLM variability in evidence screening for software engineering SLRs. arXiv:2604.27006.
- [v] Ahmed, T., Devanbu, P., Treude, C., Pradel, M. (2025). Can LLMs replace manual annotation of software engineering artifacts? MSR 2025. doi:10.1109/MSR66628.2025.00086
- [v] Wang, S., Scells, H., Koopman, B., Zuccon, G. (2023). Can ChatGPT write a good Boolean query for systematic review literature search? SIGIR 2023. doi:10.1145/3539618.3591703
- [p] Khraisha, Q. et al. (2024). Can large language models replace humans in systematic reviews? Research Synthesis Methods. doi:10.1002/jrsm.1715 (Band/Seiten)
- [v] Gartlehner, G. et al. (2024). Data extraction for evidence synthesis using a large language model. Research Synthesis Methods 15(4), 576-589. doi:10.1002/jrsm.1710
- [v] Dennstädt, F. et al. (2024). Title and abstract screening for literature reviews using large language models. Systematic Reviews 13. doi:10.1186/s13643-024-02575-4
- [v] Zheng, L. et al. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. NeurIPS 36 (Datasets and Benchmarks).
- [v] Panickssery, A., Bowman, S. R., Feng, S. (2024). LLM evaluators recognize and favor their own generations. NeurIPS 37.
- [v] Verga, P. et al. (2024). Replacing judges with juries: evaluating LLM generations with a panel of diverse models. arXiv:2404.18796.
- [v] Shi, L. et al. (2025). Judging the judges: a systematic study of position bias in LLM-as-a-judge. IJCNLP-AACL 2025, 292-314.
- [v] Calderon, N., Reichart, R., Dror, R. (2025). The alternative annotator test for LLM-as-a-judge. ACL 2025, 16051-16081. doi:10.18653/v1/2025.acl-long.782
- [v] Reiss, M. V. (2023). Testing the reliability of ChatGPT for text annotation and classification: a cautionary remark. arXiv:2304.11085.

### Related Work
- [v] Sadiq, R. B., Safie, N., Abd Rahman, A. H., Goudarzi, S. (2021). Artificial intelligence maturity model: a systematic literature review. PeerJ CS 7, e661. doi:10.7717/peerj-cs.661
- [v] Akbarighatar, P., Pappas, I., Vassilakopoulou, P. (2023). A sociotechnical perspective for responsible AI maturity models. IJIM Data Insights 3(2), 100193. doi:10.1016/j.jjimei.2023.100193
- [v] Akbarighatar, P. (2022). Maturity and readiness models for responsible AI: a systematic literature review. MCIS 2022, paper 12.
- [v] Sun, J. (2026). Are organizations ready for human-AI collaboration? A systematic review of AI maturity models. HHAI 2026, FAIA 423, 505-510. doi:10.3233/FAIA260546
- [v] Jöhnk, J., Weißert, M., Wyrtki, K. (2021). Ready or not, AI comes. BISE 63(1), 5-20. doi:10.1007/s12599-020-00676-7
- [v] Holmström, J. (2022). From AI to digital transformation: the AI readiness framework. Business Horizons 65(3), 329-339. doi:10.1016/j.bushor.2021.03.006
- [v] Mikalef, P., Gupta, M. (2021). Artificial intelligence capability. Information & Management 58(3), 103434. doi:10.1016/j.im.2021.103434
- [v] Hansen, H. F., Lillesund, E., Mikalef, P., Altwaijry, N. (2024). Understanding artificial intelligence diffusion through an AI capability maturity model. ISF 26(6), 2147-2163. doi:10.1007/s10796-024-10528-4
- [v] Fukas, P., Rebstadt, J., Remark, F., Thomas, O. (2021). Developing an artificial intelligence maturity model for auditing. ECIS 2021, 133.
- [v] Heger, A. K. et al. (2025). Towards a responsible AI organizational maturity model. PACM HCI 9(7) (CSCW). doi:10.1145/3757514
- [v] Reuel, A. et al. (2024). Responsible AI in the global context: maturity model and survey. arXiv:2410.09985.
- [v] Dreyling, R., Lemmik, J., Tammet, T., Pappel, I. (2024). An artificial intelligence maturity model for the public sector. TalTech J. of European Studies 14(2), 217-239. doi:10.2478/bjes-2024-0023
- [v] Tehrani, A. N. et al. (2024). Decoding AI readiness. Technovation 131, 102948. doi:10.1016/j.technovation.2023.102948
- [v] Uren, V., Edwards, J. (2023). Technology readiness and the organizational journey towards AI adoption. IJIM 68, 102588. doi:10.1016/j.ijinfomgt.2022.102588
- [v] Ferreira, R. M. F. D., Grilo, A., Maia, M. (2025). Piloting a maturity model for responsible artificial intelligence. J. Responsible Technology 22, 100117. doi:10.1016/j.jrt.2025.100117
- [v] Witkowski, A., Wodecki, A. (2026). A prescriptive generative AI maturity model for new product development processes. JMTM 37(9), 40-63. doi:10.1108/JMTM-09-2025-0884
- [p] The Trustworthy AI Maturity Model (TAIMM): Integrating ethics and regulation across the AI lifecycle (2026). J. Responsible Technology. (Autoren, Band)
- [v] Siebert, J. et al. (2022). Construction of a quality model for machine learning systems. Software Quality Journal 30, 307-335. doi:10.1007/s11219-021-09557-y
- [v] Xia, B. et al. (2024). Towards a responsible AI metrics catalogue. CAIN 2024; arXiv:2311.13158.
- [v] Lu, Q. et al. (2024). Responsible AI pattern catalogue. ACM Computing Surveys 56(7), 1-35. doi:10.1145/3626234
- [v] Motamedi, E., Novalija, I., Rei, L. (2026). Semi-automatic hierarchical taxonomy creation from existing taxonomies with large language models. BISE 68(1), 35-57. doi:10.1007/s12599-025-00982-y
- [p] Shah, C. et al. (2023). Using large language models to generate, validate, and apply user intent taxonomies. MSR-TR-2023-32. (Journal-Version doi:10.1145/3732294 prüfen)
- [v] Preßler, W., Seidel, P., Späthe, S. (2026). LLM-supported excerpt-level maturity assessment. I4CS 2026, CCIS 3007, 260-277. doi:10.1007/978-3-032-27096-2_14
- [v] Papagiannidis, E., Mikalef, P., Conboy, K. (2025). Responsible artificial intelligence governance: a review and research framework. JSIS 34(2), 101885. doi:10.1016/j.jsis.2024.101885
- [v] Batool, A., Zowghi, D., Bano, M. (2025). AI governance: a systematic literature review. AI and Ethics. doi:10.1007/s43681-024-00653-w
- [v] Birkstedt, T., Minkkinen, M., Tandon, A., Mäntymäki, M. (2023). AI governance: themes, knowledge gaps and future agendas. Internet Research 33(7), 133-167. doi:10.1108/INTR-01-2022-0042
- [v] Mäntymäki, M., Minkkinen, M., Birkstedt, T., Viljanen, M. (2022). Defining organizational AI governance. AI and Ethics 2(4), 603-609. doi:10.1007/s43681-022-00143-x
- [v] Schneider, J., Abraham, R., Meske, C., vom Brocke, J. (2023). Artificial intelligence governance for businesses. ISM 40(3), 229-249. doi:10.1080/10580530.2022.2085825
- [v] MITRE (2023). The MITRE AI Maturity Model and Organizational Assessment Tool Guide.
- [v] NIST (2023). AI Risk Management Framework 1.0, NIST AI 100-1. doi:10.6028/NIST.AI.100-1
- [v] ISO/IEC 42001:2023. Artificial intelligence - Management system.
- [v] AWS (2024). AWS Cloud Adoption Framework for AI, ML and Generative AI.
- [v] Google Cloud (2020). AI Adoption Framework.
- [v] Microsoft. Cloud Adoption Framework for Azure - AI adoption.
- [v] Regulation (EU) 2024/1689 (Artificial Intelligence Act).
