# Implementierungsplan: LLM-gestützte Herleitung eines Qualitätsmodells (WP0)

Stand: 23.10.2026 · **Plan freigegeben (Philipp, 23.10.2026)** · Grundlage: `docs/aiqm-study/PROMPT.md` (Teil A bis F) · Repo-Stand `2a687c5`

Dieses Dokument ist das Ergebnis von WP0. Es hält fest, was ReviQ heute kann, wo der Prompt und das
Repo auseinanderliegen, wie die Entscheidungen E1 bis E6 ausgefallen sind (Abschnitt 3) und wie WP1
bis WP9 gebaut werden. Code für WP1 ff. gibt es noch nicht.

Änderung gegenüber dem ersten Entwurf: Philipps Rückmeldung vom 23.10. ist eingearbeitet
(vollautomatischer Betrieb als gleichrangiges Ziel, keine Lizenzdatenbanken, Suche nur Englisch).

---

## 1. Zusammenfassung

- ReviQ ist sauber gebaut und gut getestet: **754 Tests grün** (`pytest`, Python 3.12, 52 s).
- Für die Studie trägt ReviQ fast alles: Projekttyp `mlr`, fünf Reviewer, Decision-JSON-Import,
  Konfliktverwaltung, κ mit Konfidenzintervall und PABAK für alle Reviewer-Paare, QA, Extraktion,
  WARC-Archiv mit SHA-256, Replication Package.
- ReviQ macht jede Abweichung zwischen Reviewern zu einem Konflikt. Die Lösung (E1) ist eine
  **adaptive Jury**: je Record so viele Stimmen wie nötig, Fehlerraten der Judges aus ihrer
  Übereinstimmung geschätzt (Dawid-Skene), ein automatisches Reliabilitäts-Gate je Phase,
  Menschen optional über aktives Lernen. Zwei Betriebsarten: `studie` (Paper) und `review`
  (vollautomatisch). ReviQ bleibt unverändert; Entscheidungen der Jury laufen über den
  bestehenden Konflikt-Endpunkt.
- Retrieval nur aus offenen Quellen (OpenAlex, Semantic Scholar, arXiv, creel), Suche nur Englisch
  (E3, E4); damit gibt es keinen manuellen Suchschritt mehr.
- Die Syntaxprüfung C.3 ist **nur vorläufig**: Die Hilfeseiten der Anbieter waren aus dieser
  Umgebung nicht erreichbar, nur Suchauszüge. Zwei Annahmen im Prompt sind nach diesen Auszügen
  wahrscheinlich veraltet (OpenAlex-Wildcards und -Proximity, IEEE-Limits). Details in Abschnitt 8.
- Kosten: Die LLM-Läufe liegen nach grober Schätzung **bei etwa 150–400 Dollar für alle Judges
  zusammen**, weil die adaptive Jury die meisten Records mit zwei Stimmen entscheidet. Dazu kommen
  einige hundert bis tausend SearchApi- und ScrapingBee-Credits (Abschnitt 6).

---

## 2. Bestandsaufnahme ReviQ

| Bereich | Stand im Repo | Bedeutung für die Studie |
|---|---|---|
| Projekttyp | `Project.review_type` mit den Werten `slr` und `mlr` (`app/models.py`) | Der Prompt sagt „multivocal“; im Code heißt das `mlr`. |
| Reviewer | `Reviewer.role` R1 bis R5, frei benannt | R3 bis R5 als Judges möglich. |
| Phasen | `ReviewerDecision.phase` mit den Werten `screening` und `full-text` | WP5 „Eligibility“ = `full-text`. |
| Entscheidungen | `I`, `E`, `U`; `criterion_label`, `rationale`, `source_file` | Konfidenz und Lauf-Nummer haben kein Feld → eigene Tabellen. |
| Zustandslogik | `services/decision_service.sync_decision_state`: 1 Stimme → vorläufige Entscheidung; alle gleich → final („agreement“); **jede Abweichung → offener Konflikt, keine finale Entscheidung** | Siehe E1. `ConflictLog` hält nur zwei Stimmen (erste und erste abweichende). |
| Konfliktauflösung | `POST /api/projects/{id}/conflicts/{cid}/resolve` mit `resolution`, `resolution_method`, `resolution_note`, `resolved_by_reviewer_id` | Kann eine dokumentierte Regelauflösung tragen (E1, Option C). |
| Decision-Import | `POST /api/projects/{id}/import/reviewer-decisions`, Upsert je (Paper, Reviewer, Phase), Rückgabe mit disjunkten Zählern | Genau das Format aus A.2. Ein Judge, der zweimal läuft, überschreibt seine Entscheidung (Upsert). Lauf-zu-Lauf-Werte daher nur in den eigenen Tabellen. |
| κ | `routers/kappa.py`: Cohen's κ mit 95 %-KI (z = 1,96, eigene SE-Formel), PABAK, `all-pairs`; U = Enthaltung | Für R1/R2 und Judge-Paare nutzbar. α, AC1 und MCC fehlen (WP4). |
| PRISMA | `routers/report.py` zählt finale `I`/`E` je Phase | Finale `U` zählen weder als ein- noch als ausgeschlossen → U muss vor dem Bericht aufgelöst sein. |
| Migrationen | `database.MIGRATIONS`: additive `ALTER TABLE`, idempotent, Fehler geschluckt; Tabellen über `SQLModel.metadata.create_all`; Retrieval-Tabellen über `retrieval/schema.sql` | Neue Judging-Tabellen werden als eigene SQLModel-Tabellen angelegt (keine Änderung bestehender Tabellen). |
| creel | `python -m app.retrieval` mit `run`, `batch` (TOML), `refetch --dry-run`, `reextract`, `report`, `export-json`, `adopt`; Engines `google` u. a. über SearchApi.io, `arxiv` ohne Schlüssel | C.5 wird unverändert genutzt. |
| Query-Set C.5 | Mit `retrieval.batch.load_config` geprüft: **gültig**, 19 Queries (17 Google à 5 Seiten, 2 arXiv à 3 Seiten), nur erlaubte Schlüssel | 85 SearchApi-Anfragen plus Abrufe. |
| Schlüssel | Nur aus der Umgebung; `retrieval/redact.py` mit `SEARCHAPI_API_KEY`, `SCRAPINGBEE_API_KEY`, `ANTHROPIC_API_KEY` | `SECRET_ENV_VARS` muss um die neuen Judge-Schlüssel wachsen (mechanisch, M3). |
| LLM heute | `retrieval/vision.py` (Bildbeschreibungen, `anthropic>=0.40` optional) | Einziger bisheriger Modellaufruf; Judging bekommt eine eigene Schicht. |
| Replication | `routers/replication.py`: Export und Import inklusive Retrieval-Tabellen | Der LLM-Cache und die Judging-Tabellen gehören in den Export (WP9). |
| Dokumentation | **Kein `CLAUDE.md`, kein `docs/`-Verzeichnis**; `requirements-optional.txt` verweist auf `docs/retrieval/decisions.md`, das im Repo fehlt | Der Prompt verlangt „CLAUDE.md lesen“; es gibt keins, und das Repo hat solche Verweise bewusst entfernt (M1). |
| Abhängigkeiten | `requirements.txt` exakt gepinnt; Docker-Image ohne optionale Pakete | Judging-Pakete in eigene, gepinnte `requirements-judging.txt`, damit das Image unverändert bleibt. |

---

## 3. Entscheidungen (Stand 23.10.2026, nach Philipps Rückmeldung)

Philipps Vorgaben vom 23.10.: Das Verfahren soll so automatisiert wie möglich laufen, auch ganz ohne
oder mit nur minimalem menschlichem Einsatz, weil nicht jede Anwendung ein Paper wird. Das System
soll selbst wissen, wie viele Runden es braucht, bis die Entscheidungen verlässlich sind;
menschlicher Input ist willkommen, aber nicht nötig. Direkte Zugänge zu Scopus, WoS, IEEE und ACM
gibt es nicht.

### E1 – Adaptive Jury mit selbst gemessener Reliabilität (entschieden: Lösung unten)

**Zwei Betriebsarten, ein Code.** `mode = "studie"` für das Paper (Prompts nach G2 eingefroren,
menschlicher Gold-Standard, alle Kennzahlen aus B.6) und `mode = "review"` für den laufenden
Einsatz (vollautomatisch, Menschen optional). Beide nutzen dieselbe Jury; sie unterscheiden sich
nur darin, wer die Restfälle und das Audit übernimmt und ob Prompts sich nach dem Start noch ändern
dürfen.

**Je Record so viele Stimmen wie nötig, nicht mehr.**

1. *Ankerstichprobe.* Auf einer Zufallsstichprobe (Standard 100 Records, geschichtet nach Strom)
   stimmen alle Judges ab. Daraus schätzt ein latentes Klassenmodell (Dawid & Skene 1979,
   Implementierung `crowd-kit` 1.4.2) für jeden Judge Sensitivität und Spezifität, ohne dass ein
   Mensch etwas codiert hat. Dieselbe Stichprobe liefert Krippendorffs α und Gwet's AC1 zwischen den
   Judges.
2. *Runde 1 für alle übrigen Records.* Zwei Judges aus verschiedenen Familien. Aus ihren Stimmen
   und den geschätzten Fehlerraten ergibt sich je Record die Wahrscheinlichkeit, dass er relevant
   ist (P_rel).
3. *Stopp-Regel, recall-first.* Exclude nur, wenn P_rel ≤ τ_E (Vorschlag 0,02); Include
   (Weitergabe an die nächste Phase), wenn P_rel ≥ τ_I (Vorschlag 0,5). Dazwischen folgt die
   nächste Runde: dritter Judge, dann ein zweiter Lauf des unsichersten Judges, dann ein Arbiter
   (stärkstes Modell, hoher `effort`). Nach höchstens vier Runden bleibt ein Rest: in `studie` geht
   er an Menschen, in `review` wird er eingeschlossen und als „unsicher“ markiert.
4. *U und Unparsebares* zählen als Stimme für Include (wie A.4/WP4) und lösen die nächste Runde aus.

Leichte Records kosten so zwei Aufrufe, schwierige drei bis fünf. Die Zahl der Runden ergibt sich
aus den Daten, nicht aus einer festen Vorgabe.

**Reliabilitäts-Gate je Phase (automatisch geprüft, Bericht ins Protokoll):**

- α zwischen den Judges auf der Ankerstichprobe ≥ 0,667, gemessen an der unteren Grenze des
  Bootstrap-KI (Seed fest).
- Geschätzter Recall aus dem Klassenmodell ≥ 0,95.
- *Ausschluss-Audit:* Der Stichprobenumfang folgt aus der Zielfehlerrate ε (Rule of Three:
  n = 3/ε; ε = 1 % → n = 300, ε = 2 % → n = 150). Prüfer sind in `studie` Menschen und in `review`
  ein Arbiter-Modell aus einer Familie, die beim jeweiligen Record nicht abgestimmt hat. Findet das
  Audit einen Include, senkt das System τ_E, prüft alle betroffenen Excludes erneut und
  wiederholt das Audit.
- Ist das Gate nicht erfüllt, zeigt eine Diagnose je Kriterium (`criterion_label`), wo die Judges
  auseinanderliegen, und ein Modell schlägt eine Präzisierung der Kriterientexte vor. In `review`
  wird sie als neue Prompt-Version übernommen und die Ankerstichprobe neu bewertet (höchstens drei
  Iterationen, danach Abbruch mit Bericht). In `studie` geht das nur bis zum Freeze (G2) und nur
  mit Philipps Freigabe.

**Menschlicher Input, wenn vorhanden (aktives Lernen):** Statt einer festen Stichprobe wählt das
System die k Records, deren Label das Klassenmodell am meisten verbessert (P_rel nahe einer
Schwelle, Judges uneins), und stellt sie in ReviQ als offene Konflikte ein. Jede menschliche
Antwort geht als festes Label in das Klassenmodell und schärft die Fehlerraten aller Judges.
k gibt man vor (z. B. 20 in `review`, die Validierungsstichprobe aus B.6 in `studie`).

**Anbindung an ReviQ (ReviQ bleibt unverändert):**

- Jeder Judge ist ein Reviewer (R3 bis R5; weitere Judges oder der Arbiter als eigene Reviewer).
  Seine maßgebliche Stimme geht über den bestehenden Decision-Import hinein. Wiederholungsläufe,
  Konfidenzen und P_rel stehen nur in den eigenen Tabellen.
- Stimmen alle überein, setzt ReviQ selbst die finale Entscheidung („agreement“). Andernfalls
  öffnet ReviQ einen Konflikt. Hat die Stopp-Regel entschieden, löst `python -m app.judging resolve`
  ihn über den bestehenden Endpunkt auf: `resolution_method = "arbitration"`, `resolution_note` mit
  Regel, P_rel, Stimmenzahl und Modellversionen, `resolved_by` = Reviewer „Jury“. Restfälle bleiben
  als Konflikt für Menschen offen.
- Gold-Standard und Kalibrierung (`studie`) werden in eigenen ReviQ-Projekten codiert, die nur die
  Stichprobe enthalten. So sehen R1 und R2 keine Begründungen der Judges.

**Zum Bericht im Paper (RQ2):** Das Verfahren liefert Recall, MCC und Work Saved gegen den
menschlichen Gold-Standard und zusätzlich die modellbasierte Recall-Schätzung. Der Vergleich beider
ist selbst ein Ergebnis: Er zeigt, wie gut sich das System ohne Menschen einschätzt. Das ist der
Teil, der `review` rechtfertigt.

### E2 – Judges (bestätigt als Vorschlag; Pinning der IDs beim Freeze)

Philipp: „Wenn Sonnet reicht, ist das gut, aber die Qualität muss passen.“ Deshalb entscheidet die
Kalibrierung, nicht die Annahme: eine **Modell-Leiter je Familie** mit einer festen Regel.

| Rolle | Familie | Kandidat (Mittelklasse zuerst) | Preis je Mio. Tokens (ein/aus), Stand der Quelle |
|---|---|---|---|
| J1 | Anthropic | Claude Sonnet 5.5 (`claude-sonnet-5-5`); Stufe 2: Claude Opus 5.5 (`claude-opus-5-5`) | $2/$10; Opus $4/$20 (Anthropic-Modellliste) |
| J2 | OpenAI | aktuelles Mittelklasse-Modell (laut Preisaggregatoren derzeit GPT-6.1 „Sol“) | etwa $2/$10 (Sekundärquellen, vor Pinning offiziell prüfen) |
| J3 | Google | Gemini Flash der aktuellen Generation; Stufe 2: Gemini 3.1 Pro | Flash etwa $0,75–1,50 / $3,75–9; Pro etwa $2/$12 (Sekundärquellen) |
| J4 | open-weight, lokal (Ollama) | gpt-oss 20B oder Qwen3 (8B–32B, je nach Grafikspeicher) | keine API-Kosten |
| Arbiter | eine Familie, die beim jeweiligen Record noch nicht abgestimmt hat | deren Stufe-2-Modell (z. B. Opus 5.5) | sieht nur Restfälle und Audit-Stichprobe |

**Regel:** Auf der Ankerstichprobe der Kalibrierung laufen Mittelklasse und Stufe 2 jeder Familie.
Die Mittelklasse bleibt, wenn ihre geschätzte Sensitivität nicht mehr als 2 Prozentpunkte unter
der Stufe 2 liegt und das Gate besteht; sonst gilt Stufe 2. So ist die Antwort auf „reicht Sonnet?“
ein Messwert im Bericht.

Hinweise:
- Modell-IDs werden erst beim Freeze gepinnt, aus der offiziellen Modellliste des Anbieters
  (A.3.3). Die Preise oben sind Richtwerte aus Aggregatoren; die Kostenschätzung liest sie aus der
  Studienkonfiguration.
- Claude Opus 5.5 nimmt keine Sampling-Parameter wie `temperature` an, Thinking lässt sich nicht
  abschalten. Für Sonnet 5.5, OpenAI und Google vor dem Pinning prüfen. Wiederholbarkeit kommt
  über den Cache, Stabilität wird gemessen.
- Familien-Trennung (A.3.3): Extraktion durch J1 und J2, Cluster-Benennung und Bewertung
  modellerzeugter Texte durch J3 und J4.
- Der lokale Judge läuft auf Philipps Rechner; die Cloud-Session kann ihn nicht ausführen. Ohne
  ihn sind es drei kommerzielle Familien, was A.3.3 (open-weight verlangt) nicht erfüllt. Für
  `review` ist er optional.

### E7 – Judges über Claude Code statt über die API (Philipp, 23.10.2026)

Philipp: „Es soll mit Claude laufen, aber ohne API Call.“ Das ändert A.3.10 des Auftrags (dort ist
`claude -p` als Judge-Backend ausgeschlossen) und berührt Abschnitt 7.1 des Protokolls.

- **Backend:** `app/judging/claude_cli.py` startet die Claude-Code-CLI je Anfrage im Print-Modus:
  exaktes Modell (`--model`), der eingefrorene Prompt als einziger System-Prompt
  (`--system-prompt`), keine Tools (`--tools ""`), Ausgabe nach JSON-Schema (`--json-schema`),
  JSON mit Token-Zählung (`--output-format json`), kein Transkript (`--no-session-persistence`).
  Läuft auf dem Rechner, dessen Claude-Code-Login es nutzt; jede Antwort landet im selben Cache
  und ist ohne CLI wiederholbar.
- **Grenzen gegenüber der API:** keine Sampling-Parameter, kein Batch-Rabatt, Durchsatz durch die
  Nutzungsgrenzen des Abos begrenzt.
- **Offen (Philipp):** (1) Nur Claude-Modelle (Haiku, Sonnet, Opus) als Judges, oder zusätzlich ein
  lokales offenes Modell für die Familienvielfalt? Mit nur einer Familie sind die Fehler der Judges
  korreliert; das Klassenmodell (Dawid-Skene) setzt bedingte Unabhängigkeit voraus und würde die
  Reliabilität dann überschätzen. In `studie` wäre das eine Abweichung von 7.1 mit dem
  menschlichen Gold-Standard als eigentlicher Prüfung; in `review` ist es vertretbar.
  (2) Die aktuellen Nutzungsbedingungen des Abos für automatisierte Massenläufe prüfen.
  (3) Das tatsächliche JSON-Format der CLI an einem echten Aufruf festhalten; aus der
  Arbeitsumgebung durfte die CLI nicht gestartet werden.

### E3 – Nur offene Quellen (entschieden)

Keine Lizenzzugänge, daher **nur offene Quellen**: OpenAlex (Hauptquelle), Semantic Scholar Bulk,
arXiv, Crossref als Metadaten-Ergänzung; Volltexte nur Open Access über die OA-Links von OpenAlex
und Unpaywall. Der manuelle Exportschritt aus WP3 entfällt, das Retrieval ist voll automatisiert.

Folgen:
- Die Abdeckung wird nicht behauptet, sondern gemessen: Quasi-Sensitivität der Strings gegen den
  QGS-Holdout (C.4) zeigt, was OpenAlex und Semantic Scholar finden. Was dort fehlt, steht als
  Threat to Validity im Bericht.
- Manche Verlage liefern keine Abstracts an offene Indizes. Der Anteil der Records ohne Abstract
  wird gezählt; sie werden nur nach Titel gescreent und im Zweifel eingeschlossen.
- Für nicht offene Volltexte entscheidet die Eligibility auf dem Abstract mit Markierung, oder EC3
  („no full text“) greift. Welche der beiden Varianten gilt, legt das Protokoll fest (Vorschlag:
  EC3, weil Extraktion und Span-Verifikation einen Volltext brauchen).
- Die Translator-Arbeit aus C.2 und C.3 schrumpft auf OpenAlex, Semantic Scholar und arXiv. Die
  Strings für Scopus und WoS bleiben im Protokoll als Referenz, werden aber nicht ausgeführt.

**Google (Philipp, 23.10.: „sehr, sehr wichtig“).** Google bleibt zentral und kommt zweimal vor:

- *Google-Websuche für Grey-Literatur* über creel (SearchApi.io, Engine `google`), Query-Set C.5
  ohne die deutschen Queries: 15 Queries à 5 Seiten, dazu 2 arXiv-Queries.
- *Google Scholar als zusätzlicher akademischer Kanal* über creel mit der Engine `google_scholar`,
  die creel unverändert an SearchApi.io durchreicht (`retrieval/serp.fetch_page`). Er gleicht
  einen Teil der fehlenden Lizenzdatenbanken aus. Vorgehen: die Konzeptblöcke aus C.1 als
  vereinfachte englische Queries (Scholar kennt weder Proximity noch Feldsuche), feste Seitentiefe
  als Stoppkriterium (Vorschlag 10 Seiten, also die ersten 100 Treffer je Query), jeder Treffer
  über DOI bzw. Titel gegen OpenAlex aufgelöst und als formaler Record mit Quelle „Google Scholar“
  importiert; nicht auflösbare Treffer gehen in den Grey-Strom. Ob `retrieval/serp.parse_organic`
  die Scholar-Antwort von SearchApi ohne Anpassung liest, wird in WP3 an einer aufgezeichneten
  Antwort geprüft, bevor Credits fließen.

### E4 – Suchsprache (bestätigt: nur Englisch)

E4 fragte, ob die Studie zusätzlich deutschsprachige Grey-Literatur sucht (die zwei deutschen
Queries in C.5) und ob deutsche Quellen dann zugelassen sind (EC4). Empfehlung: **Suche und
Einschluss nur Englisch.** Gründe: Fast die gesamte akademische und der größte Teil der Praxis-
Evidenz ist englisch; eine zweite Sprache verlangt eigene Kalibrierung der Judges; ein
englischsprachiges Paper ist so leichter zu prüfen. Übersetzt wird erst das Ergebnis, also das
Modell und die Empfehlungen; das deckt sich mit Sherlock (ADR-0014 dort: Begriffssprache Englisch,
Ausgabe in sechs Sprachen). Grenze: DACH-spezifische Praxisquellen fehlen; das steht als Threat
im Bericht. Die beiden deutschen Queries fallen aus C.5 heraus.

### E5 – Proxy-Optionen von creel (bestätigt)

creel kann Seiten über die Premium- oder Stealth-Proxys von ScrapingBee holen, wenn eine Seite den
normalen Abruf blockiert. Empfehlung: **ohne Premium- und Stealth-Proxy**, nur normaler Abruf und
bei Bedarf `render_js`. Blockierte Quellen fallen unter EC3 und werden mit Grund gezählt
(`retrieval_reason`). Gründe: Zugriffssperren der Anbieter werden respektiert, die Methode ist
reproduzierbar und im Methodenteil einfach zu beschreiben, die Kosten bleiben niedrig.

### E6 – Schwellwerte (bestätigt)

Die Werte aus B.6 werden übernommen. Für die zwei offenen Punkte:

- *Bootstrap-Stabilität der Abstraktion:* Für ARI gibt es keinen etablierten Schwellwert. Vorschlag:
  Median-ARI ≥ 0,7 und 2,5-%-Quantil ≥ 0,5, a priori festgelegt und als eigene Setzung berichtet.
- *Evidenzgrad je Metrik* (B.3 verlangt mindestens zwei unabhängige Quellen, davon eine akademisch
  oder Grey mit QA „high“): A = mindestens drei unabhängige Quellen, davon mindestens zwei
  empirische akademische Arbeiten; B = mindestens drei unabhängige Quellen, davon mindestens eine
  akademisch oder Grey „high“; C = genau die Mindestregel (zwei Quellen, eine davon akademisch oder
  Grey „high“); D = unter der Mindestregel (geht nicht als Metrik ins Modell, bleibt als Kandidat
  mit Begründung sichtbar).
- *Stopp-Regel der Jury:* τ_E = 0,02, τ_I = 0,5, höchstens vier Runden, Ankerstichprobe 100,
  Audit-Ziel ε = 1 % (n = 300) in `studie` und ε = 2 % (n = 150) in `review`.

Alle Werte stehen in der Studienkonfiguration und im Protokoll; G0 friert sie ein.


---

## 4. Architektur `backend/app/judging/`

Analog zu creel: ein Paket, ein CLI, kein Knopf in der Oberfläche.

```
backend/app/judging/
  __main__.py          python -m app.judging <command>
  cli.py               Kommandos, jedes kostenpflichtige mit --dry-run
  config.py            Studienkonfiguration (TOML): mode (studie | review), Judges, Modell-Leiter,
                       gepinnte IDs, Schwellwerte, Seeds, Preise für die Kostenschätzung
  models.py            eigene SQLModel-Tabellen (siehe unten), bestehende nur lesen
  providers/           anthropic.py, openai.py, google.py, ollama.py, gemeinsame Schnittstelle
  cache.py             Hash über (Anbieter, Modell-ID, Parameter, Prompt-Version, Input) → Rohantwort
  prompts/             *.md mit Frontmatter (name, version, frozen_at), Lader prüft Version und Freeze
  schemas/             JSON-Schemas der Ausgaben (Screening, QA, Extraktion, Benennung, Crosswalk)
  search/              concepts.toml, Translator (OpenAlex, Semantic Scholar, arXiv), lokale Boolesche
                       Auswertung, QGS
  jury.py              adaptive Jury: Ankerstichprobe, Runden, Stopp-Regel, Arbiter, Restfälle (E1)
  aggregation.py       Dawid-Skene (crowd-kit) mit optionalen menschlichen Labels, P_rel je Record
  gate.py              Reliabilitäts-Gate je Phase, Audit-Umfang aus Zielfehlerrate, Diagnose je Kriterium
  active.py            Auswahl der Records für menschlichen Input (aktives Lernen)
  screening.py         Screening und Volltext mit der Jury, Export als ReviQ-Decision-JSON, resolve
  extraction.py        Kandidatenaussagen, Span-Verifikation, IoU-Abgleich
  abstraction.py       Embeddings (lokal gepinnt), agglomeratives Clustering, Hierarchie
  stats.py             α, AC1, MCC, ARI, F1, Bootstrap mit Seed, Rule of Three, Sättigung
  report.py            alle Kennzahlen als CSV, LaTeX, SVG
  costs.py             Schätzung je Kommando (Aufrufe, Tokens, Batch-Ersparnis)
```

Eigene Tabellen (Präfix `aiqm_`, Migration über `create_all`, keine Änderung bestehender Tabellen):
`aiqm_llm_call` (Cache: Hash, Anbieter, Modell-ID, Parameter, Prompt-Name/-Version, Input, Rohantwort,
Zeit, Tokens, Kosten, Status), `aiqm_judge_decision` (Judge, Lauf, Paper, Phase, I/E/U, Kriterium,
Begründung, Konfidenz, parse_ok, Cache-Hash), `aiqm_qgs` (Paper/DOI, Herkunft, Split dev/holdout,
Seed), `aiqm_search_candidate` (String je Datenbank, Bewertungen), `aiqm_statement` (Schema B.5,
Span, Offsets, verifiziert), `aiqm_cluster`, `aiqm_model_element` (Dimension/Kriterium/Metrik,
Eltern, Definition, Evidenz), `aiqm_crosswalk`, `aiqm_coverage`.

Kommandos (Auswahl): `init-study`, `qgs import|split`, `search harvest|candidates|evaluate|select`,
`screen` (adaptiv, mit `--max-rounds`, `--human-budget`), `gate`, `export-decisions`, `resolve`,
`calibrate`, `freeze`, `audit-excludes`, `qa`, `extract`,
`abstract`, `saturation`, `coverage`, `crosswalk`, `report`, `replicate --from-cache`.

Grundsätze aus A.3 im Code: Cache-Hit vor jedem Aufruf, `--offline` scheitert bei Cache-Miss statt
zu rufen; Prompt-Lader verweigert geänderte Prompts nach `freeze` (Hash im Freeze-Protokoll);
Modell-IDs ohne Alias (Prüfung gegen eine Sperrliste wie `latest`); Batch-APIs für Hauptläufe;
keine Claude-Code-CLI und kein Agent SDK als Judge-Backend (A.3.10).

---

## 5. Arbeitspakete

| WP | Ergebnis | Tests | Gate |
|---|---|---|---|
| WP1 | `protocol.md` aus B und C mit Platzhaltern und den Werten aus E6; ReviQ-Projekt (`mlr`), IC/EC mit `short_label`, QA-Kriterien (akademisch und Garousi), Reviewer R1/R2, Judges und „Jury“; Kalibrierungs- und Validierungsprojekt (E1); Skelett `judging/` mit Konfiguration, Cache, Prompt-Lader, Anbieter-Schnittstelle und `--dry-run` | Projekte idempotent; Cache-Roundtrip; Prompt-Freeze; Schlüssel nie in Cache oder Logs | **G0** |
| WP2 | QGS-Import (B.4, D, F), Anreicherung über OpenAlex, Split 60/40 mit Seed; `concepts.toml`; Translator für OpenAlex, Semantic Scholar und arXiv mit Golden Files (Scopus und WoS nur als Referenztext im Protokoll); Suchstring-Judge nach C.4 | Golden Files, Boolesche Auswertung, Split-Determinismus | **G1** |
| WP3 | OpenAlex (Cursor-Paging), Semantic Scholar Bulk, arXiv und Google Scholar (creel, Auflösung gegen OpenAlex) als BibTeX; OA-Volltexte über OpenAlex und Unpaywall; creel-Lauf mit C.5 ohne die deutschen Queries und ohne Premium-/Stealth-Proxy; Dedup über ReviQ; Retrieval-Report mit Anteil fehlender Abstracts und fehlender OA-Volltexte | Paging und BibTeX gegen aufgezeichnete Antworten | – |
| WP4 | Adaptive Jury (E1): Ankerstichprobe, Modell-Leiter (E2), Kalibrierung (3 Läufe je Judge), Freeze, Hauptlauf mit Stopp-Regel, Gate, Audit, Validierung gegen Gold; Nicht-LLM-Baseline (TF-IDF + logistische Regression, B.7) | Dawid-Skene gegen den Referenzdatensatz von Dawid & Skene (1979); Stopp-Regel und Rundenzahl auf simulierten Judges mit bekannten Fehlerraten (Recall-Schätzung trifft den Sollwert); Export-JSON gegen den Import-Endpunkt (wie `test_integration_decision_exchange`); `resolve` über den Konflikt-Endpunkt; Cache-Roundtrip | **G2** |
| WP5 | Volltext-Jury (dieselbe adaptive Jury, Phase `full-text`), QA-Vorschläge, Agreement auf Stichprobe | QA-Aggregation gegen ReviQs `qa`-Logik | – |
| WP6 | Extraktion durch zwei Judges, Span-Verifikation (Normalisierung wie in einem Test festgelegt), IoU ≥ 0,5, Halluzinationsrate | Span-Suche mit positiven und negativen Fällen, IoU | – |
| WP7 | Embeddings (lokal gepinnt), Clustering, Schwellwert per ARI auf Kalibrierung, Jury-Benennung mit randomisierter Reihenfolge, Hierarchie, Bootstrap | ARI gegen Referenz, Determinismus mit Seed | **G3** |
| WP8 | Sättigung nach Guest et al. (100 Permutationen), Abdeckungsmatrix, Traceability, Crosswalk AI Act / ISO 42001 / NIST AI RMF | Sättigungsmaße gegen ein Beispiel aus Guest et al. | – |
| WP9 | `report` mit allen Zahlen; Baltes-Checkliste; Replication Package inklusive Cache und Prompts | Replikation aus dem Cache ohne Schlüssel ergibt identische Tabellen | – |

Statistik (A.3.7): `krippendorff` 0.9.0, `scikit-learn` 1.9.1 (MCC, ARI, F1), `irrCAC` 0.4.4 (AC1),
`statsmodels` 0.15.0 (Konfidenzintervalle), `crowd-kit` 1.4.2 (Dawid-Skene), alle auf PyPI verfügbar; Tests gegen publizierte
Referenzwerte (Krippendorff 2011, Gwet). Die vorhandene κ-Implementierung bleibt die Quelle für κ;
ein Test vergleicht sie mit `sklearn.metrics.cohen_kappa_score`.

---

## 6. Kostenschätzung (Größenordnung)

Annahmen, alle vor G1 bzw. G2 zu ersetzen: 6.000–8.000 Records nach Dedup (C.1 deckelt S2 bei etwa
8.000), etwa 400 brauchbare Grey-Quellen, 400–600 Volltexte in WP5, 150–250 eingeschlossene Quellen
in WP6.

| Schritt | Aufrufe | Tokens je Aufruf (ein/aus) | Volumen je Judge |
|---|---|---|---|
| Suchstring-Judge (Präzision, 50 Treffer × ~30 Kandidaten) | ~1.500 | 0,6k / 0,1k | ~1M ein |
| Screening, adaptiv: Ankerstichprobe (100 × alle Judges), Runde 1 (2 Judges je Record), weitere Runden (Annahme 25 % der Records) | ~2,3 Stimmen je Record, also ~17.000 Aufrufe auf alle Judges verteilt | 1,2k / 0,2k (+ Thinking) | ~7M ein, 1–4M aus je Judge |
| Kalibrierung (50 × 3 Läufe) und Validierung (300) | ~450 | 1,2k / 0,2k | <1M |
| Volltext und QA | ~500–600 | 10–15k / 0,5k | ~8M ein |
| Extraktion (2 Judges) | ~200 | 15k / 2k | ~3M ein, 0,4M aus |
| Benennung, Crosswalk, Audit | ~1.000 | 2k / 0,3k | ~2M ein |

Grob also **20–25M Eingabe- und 2–6M Ausgabe-Tokens je kommerziellem Judge**; der Arbiter
(Stufe-2-Modell) sieht nur Restfälle und Audit, etwa 1.000–2.000 Aufrufe.

| Posten | Schätzung |
|---|---|
| J1 Sonnet 5.5 ($2 / $10 je Mio. Tokens laut Anthropic-Modellliste; Batch halbiert) | Standard ~$60–110, Batch ~$30–55; mit hohem Thinking-Anteil bis ~$150 |
| Weitere kommerzielle Judges (OpenAI-Mittelklasse, Gemini Flash) | gleiche Token-Mengen; nach den Richtpreisen aus E2 ~$30–120 je Judge mit Batch |
| Arbiter (z. B. Opus 5.5) | ~$20–60 |
| **LLM gesamt** | **etwa $150–400** (Batch, Mittelklasse besteht die Kalibrierung); deutlich mehr, wenn Stufe 2 für alle Judges nötig wird |
| Lokaler Judge (Ollama) | keine API-Kosten; Laufzeit auf Philipps Rechner (Stunden bis Tage für 9.000 Screenings, je nach Hardware) |
| SearchApi.io (C.5 ohne deutsche Queries: 75 Anfragen; Google Scholar etwa 6–10 Queries à 10 Seiten; plus Wiederholungen) | ~200–300 Suchen |
| ScrapingBee (bis ~750 Abrufe, ohne Premium-/Stealth-Proxy nach E5) | ~1.000–4.000 Credits je nach Anteil `render_js` |
| OpenAlex, Semantic Scholar, Unpaywall | ohne Kosten; Bedingungen (Kontaktadresse bzw. Schlüssel) vor WP2 prüfen |

Jedes kostenpflichtige Kommando zeigt diese Schätzung mit `--dry-run` aus den tatsächlichen
Record-Zahlen, getrennt nach Standard und Batch (A.3.6).

---

## 7. Benötigte Schlüssel und Zugänge

Alle nur als Umgebungsvariablen, in `redact.SECRET_ENV_VARS` aufgenommen:

- `ANTHROPIC_API_KEY` (API-Konto, nicht das Abo; A.3.10)
- `OPENAI_API_KEY` und `GOOGLE_API_KEY` bzw. `GEMINI_API_KEY`, je nach E2
- Ollama lokal: kein Schlüssel; Modell-Digest in der Studienkonfiguration
- `SEARCHAPI_API_KEY`, `SCRAPINGBEE_API_KEY` (vorhanden in creel)
- `SEMANTIC_SCHOLAR_API_KEY` (optional, für stabile Rate-Limits)
- `OPENALEX_EMAIL` bzw. ein OpenAlex-Schlüssel, falls nötig; `UNPAYWALL_EMAIL`
- OSF bzw. Zenodo: Philipps Konto für G0 und WP9 (kein Schlüssel im Code nötig)

---

## 8. Syntaxprüfung C.3 (vorläufig)

**Einschränkung:** Aus dieser Umgebung waren die Hilfeseiten der Anbieter nicht abrufbar (Proxy bzw.
DNS gesperrt für openalex.org, elsevier.com, clarivate.com, ieee.org, acm.org, semanticscholar.org).
Die Angaben unten stammen aus Suchmaschinen-Auszügen der genannten Seiten, abgerufen am 23.10.2026.
**Sie gelten nicht als geprüft im Sinne von C.3.** Nach E3 werden nur noch OpenAlex, Semantic Scholar
und arXiv ausgeführt; die übrigen Zeilen bleiben als Referenz für die Strings im Protokoll. Vor G1 muss jemand mit Netzzugang die
Originalseiten lesen und Version, URL und Datum eintragen; das CLI bekommt dafür eine Tabelle
`aiqm_syntax_check`.

| Datenbank | Aussage im Prompt | Stand laut Suchauszug | Bewertung |
|---|---|---|---|
| Scopus | Vorrang OR vor W/n vor AND | Elsevier-Support: OR, dann W/n und PRE/n, dann AND, dann AND NOT ([Elsevier Support](https://www.elsevier.support/scopus/answer/how-can-i-best-use-the-advanced-search), [Scopus Search Tips](https://dev.elsevier.com/sc_search_tips.html)) | **bestätigt** (vorläufig) |
| Scopus | `"…"` als Phrase, `*` in Phrasen | Anführungszeichen = lose Phrase, `{…}` = exakte Phrase (Bibliotheksleitfäden, widersprüchlich); Wildcards `*`/`?` mit mindestens 3 Zeichen davor | **prüfen**: Wildcards in losen Phrasen (`"large language model*"`) |
| Web of Science | Vorrang NEAR vor AND | NEAR/x, SAME, NOT, AND, OR; NEAR ohne Zahl = 15 Wörter ([WoS Search Operators](https://webofscience.help.clarivate.com/Content/search-operators.html)) | **bestätigt**; zusätzlich: NOT vor AND, AND vor OR → Klammern wie im Prompt nötig |
| IEEE Xplore | Limits prüfen, S1 ggf. splitten | 25 Suchbegriffe je Klausel, bis zu 10 Wildcards je Suche; NEAR/ONEAR nur in Command Search ([Command Search](https://ieeexplore.ieee.org/Xplorehelp/searching-ieee-xplore/command-search), [Search Tips](https://ieeexplore.ieee.org/Xplorehelp/searching-ieee-xplore/search-tips)) | **Abweichung wahrscheinlich**: S1 hat bereits 23 Begriffe, ausgeschriebene Singular/Plural-Formen überschreiten 25 → Split in Teilabfragen ist sicher nötig. Feldname „All Metadata“ unbestätigt. |
| ACM DL | Titel, Abstract, Keywords | Felder Title, Abstract per „Search Within“; Syntax `Title:(…) AND Abstract:(…)`; Operatoren groß; Stemming und Plural standardmäßig an; Proximity widersprüchlich ([UCL Guide](https://library-guides.ucl.ac.uk/ACM-Digital-Library/searching), [ACM Training](https://libraries.acm.org/training-resources/new-dl-features/advanced-search-2021)) | **prüfen**: Feldname für Author Keywords; ob ACM Proximity kennt |
| OpenAlex | keine Wildcards, keine Proximity, Stemming an; `*`, `?`, `~` werden still entfernt | Aktuelle Entwickler-Doku laut Auszug: AND/OR/NOT groß, Phrasen, **Proximity `"…"~N`**, **Wildcards `*`/`?` nur mit `search.exact` (ungestemmt), mind. 3 Zeichen davor**; die ältere Doku sagt „werden entfernt“; URL-Grenze ~4 KB ([developers.openalex.org](https://developers.openalex.org/guides/searching), [help.openalex.org](https://help.openalex.org/api/searching/), [docs.openalex.org](https://docs.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities)) | **Abweichung wahrscheinlich**: Der Prompt beschreibt den älteren Stand. Ob `title_and_abstract.search` weiter als Filter existiert, war im Auszug nicht bestätigt. URL-Länge der OR-Gruppen bei S2 beachten. |
| Semantic Scholar | Bulk-Syntax `+`, `\|`, `-`, Phrasen | Nur `\|` als OR über eine Drittquelle bestätigt; die offizielle Doku war nicht im Auszug | **ungeprüft** |

Zusammengefasst: Scopus- und WoS-Vorrang wie im Prompt; IEEE braucht sicher Teilabfragen; bei
OpenAlex ist der Prompt vermutlich überholt (Proximity und Wildcards jetzt möglich, aber nur
ungestemmt). Daraus folgt eine G1-Frage: Bleibt OpenAlex beim gestemmten Suchen ohne Wildcards
(einfacher, wie im Prompt), oder nutzt es `search.exact` mit Wildcards?

---

## 9. Mechanische Entscheidungen (Änderungsprotokoll)

| Nr. | Entscheidung | Grund |
|---|---|---|
| M1 | Kein Anweisungsdokument für Entwicklungswerkzeuge im Repo; die Arbeitsgrundlage bleibt `docs/aiqm-study/PROMPT.md` und dieser Plan | Der Prompt setzt eine `CLAUDE.md` voraus; das Repo hat solche Verweise bewusst entfernt (Commit `86c83f9`). Commits erscheinen nur unter Philipps Namen. |
| M2 | Projekttyp `mlr` statt „multivocal“ | So heißt der Wert im Code (`Project.review_type`). |
| M3 | `redact.SECRET_ENV_VARS` um die neuen Schlüssel erweitern | A.3.4 verlangt Wiederverwendung von `redact.py`; sonst würden die neuen Schlüssel nicht geschwärzt. Einzige Änderung an bestehendem Code außerhalb von `judging/`. |
| M4 | Judging-Abhängigkeiten in `backend/requirements-judging.txt`, exakt gepinnt (Anbieter-SDKs, Statistik, `crowd-kit`, lokales Embedding-Modell) | Das Docker-Image und `requirements.txt` bleiben unverändert. |
| M5 | Phase „Eligibility“ = ReviQ-Phase `full-text` | Vorhandenes Vokabular. |
| M6 | Lauf-zu-Lauf-Daten und Konfidenzen nur in `aiqm_judge_decision`; nach ReviQ geht je Judge und Phase genau der maßgebliche Lauf | Der Import macht Upserts; mehrere Läufe würden sich überschreiben. |
| M7 | Studien-Artefakte unter `docs/aiqm-study/` (Prompt, Plan, Protokoll, Related Work), Konfiguration unter `backend/app/judging/` | Wie im Prompt vorgesehen. |
| M8 | Reviewer-Rollen: J1–J3 als R3–R5 (wie im Auftrag), J4 als R6, „Jury“ als R7, „Arbiter“ als R8 | ReviQ und die Oberfläche behandeln Rollen als freien Text; so nennt jede Entscheidung ihre Quelle. |
| M9 | Akademische und Grey-QA-Kriterien liegen beide im Projekt (QA-A1–A5, QA-G1–G7); das Judging-Modul bewertet jede Quelle nur nach der Liste ihres Stroms und berechnet das QA-Level selbst | ReviQ kennt eine QA-Liste je Projekt und unterscheidet die Ströme dabei nicht. ReviQs eigene QA-Zusammenfassung ist für diese Projekte deshalb nicht aussagekräftig. |
| M10 | Prompt-Freeze je Prompt (`prompts/freeze.json`) statt eines globalen Freeze | Die Phasen erreichen ihren Freeze zu verschiedenen Zeitpunkten (Screening bei G2, Extraktion später). |

---

## 10. Nächster Schritt

1. Erledigt: Plan freigegeben am 23.10.2026.
2. Die Syntax-Tabelle (Abschnitt 8) wird für OpenAlex, Semantic Scholar und arXiv an den
   Originalseiten geprüft; Scopus und WoS sind nur noch Referenz.
3. WP1 erledigt (siehe unten). **G0 erteilt am 23.10.2026:** Protokoll freigegeben, ohne
   öffentliche Registrierung (Zeitstempel ist der Commit); Seed-Liste wie vorgeschlagen ohne
   Gartner; QA-Level high ≥ 75 %, medium ≥ 50 % je Strom.
4. WP2 läuft (Stand unten). Für die Online-Schritte braucht die Arbeitsumgebung Zugriff auf
   OpenAlex und die Dokumentationsseiten (Abschnitt 8); bis dahin führt Philipp sie lokal aus.

### Stand WP2 (23.10.2026)

Gebaut und getestet (offline):
- `search/concepts.toml` und `concepts.py`: kanonische Blöcke A, O, O2, M, E, K und die Strings S1
  und S2 als Klauseln (Block oder Block W/n Block).
- `search/boolean.py`: lokale Boolesche Auswertung über Titel, Abstract und Keywords, mit W/n wie
  bei Scopus, ohne Stemming (untere Schranke gegenüber stemmenden Quellen), Feldgrenzen werden
  nicht überbrückt.
- `search/translate.py`: Übersetzung für OpenAlex, Semantic Scholar, arXiv und Google Scholar;
  Proximity wird zu AND (keine dieser Quellen kann Gruppen-Proximity), Golden Files unter
  `tests/judging/golden/`. Google Scholar: feste Regel mit 22 kurzen Queries, als creel-Query-Set
  ausgebbar (`search render --source google_scholar --creel-toml`).
- `search/openalex.py`: Client für Werke (DOI, ID, Titel) und Trefferzahlen (`meta.count`), Parser
  gegen ein aus dem dokumentierten Schema gebautes Fixture; beim ersten Lauf mit Netz durch eine
  aufgezeichnete Antwort zu ersetzen.
- `search/qgs_seeds.toml` und `qgs.py`: 22 Startwerke aus Teil B.4, D und F (Seeds, Reviews,
  verwandte Arbeiten), Import mit Referenzen der Seeds und Reviews, Prüfliste als CSV für beide
  Autoren, deterministischer Split 60/40, der genau einmal läuft.
- `search/candidates.py` und `harvest.py`: Varianten (Ablation, W/3/5/10, AND, verbreiterte Blöcke),
  Sensitivität auf QGS-dev, Auswahlregel nach C.4; TF-IDF-Begriffsernte.
- CLI: `qgs import|export|accept|split|status`, `search render|evaluate [--count]`.
- 40 neue Tests, Suite 833 grün.

Offen bis G1:
- **Netz:** `qgs import` und `search evaluate --count` brauchen api.openalex.org. Die
  Syntaxprüfung braucht die Dokumentationsseiten (developers.openalex.org, help.openalex.org,
  api.semanticscholar.org, info.arxiv.org, searchapi.io).
- **Menschen:** Die QGS-Kandidatenliste prüfen (`qgs export --file qgs.csv`, Spalte `accept`
  mit y/n, dann `qgs accept --file qgs.csv`), etwa 1 Stunde.
- **Jury-Präzision:** Die Schätzung der Präzision je Kandidat (50 Treffer, Mehrheitsentscheid)
  braucht die Judge-Backends. Sie werden für G1 vorgezogen (eigentlich WP4); bis dahin wählt die
  Regel nicht aus.
- **WP3-Hinweis:** creel ruft jeden Treffer über ScrapingBee ab. Für Google Scholar reicht die
  Trefferliste, weil die Treffer gegen OpenAlex aufgelöst werden. Ein Abruf nur der Trefferliste
  spart Credits und wird in WP3 geprüft.

### Stand WP1 (23.10.2026)

- `docs/aiqm-study/protocol.md`: Protokoll für G0, englisch (Registrierung und Paper), mit allen
  a-priori-Werten aus E1 bis E6 und markierten Platzhaltern `[set at Gx]`.
- `backend/app/judging/`: `study.toml` (Konfiguration), `criteria.toml` (IC/EC/QA, Reviewer),
  `config.py` (strenge Prüfung, Alias-Sperre, Pinning-Pflicht beim Freeze), `cache.py`
  (Schlüssel über alles, was die Antwort bestimmt; Offline-Replay; Schwärzung), `prompts.py`
  (Front Matter, Hash, Freeze), `costs.py` (Schätzung inkl. adaptiver Stimmenzahl), `setup.py`
  (`init-study`: drei Projekte, idempotent, ändert nie bestehende Kriterien), `providers.py`
  (Schnittstelle; Backends folgen in WP4), `cli.py`.
- `app/retrieval/redact.py`: neue Schlüssel ergänzt (M3).
- Tests: 39 neue unter `backend/tests/judging/`, gesamte Suite 793 grün.
- Beispiel: `python -m app.judging estimate --records 7000` schätzt das Screening auf etwa
  15.900 Stimmen und rund $48 im Batch für die drei kommerziellen Judges (Mittelklasse,
  Richtpreise).
