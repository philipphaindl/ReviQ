# Review protocol: an LLM-jury-assisted, validated derivation of a quality model for AI adoption in organisations

Status: **approved at G0** (2026-10-23, Philipp Haindl) · Authors: Philipp Haindl, Oliver Eigner ·
Model name: `<MODELNAME>` (set after trademark check) · Registration: internal; the timestamp is the
commit that fixed this version in the ReviQ repository (no public registration for now)

This protocol is fixed before any search is run. Every value marked **a priori** is binding; a later
change is reported as a deviation (section 12). Values that can only be set after calibration are
marked `[set at Gx]` and are filled in at that gate, with the date, before the step that uses them.
The configuration that the tooling reads is `backend/app/judging/study.toml` and
`backend/app/judging/criteria.toml`; this document and those files must agree.

---

## 1. Background and objective

Many maturity and readiness models for AI in organisations exist, few reach measurable metrics,
and few make their derivation traceable. This study derives a quality model for AI adoption in
organisations from existing models and multivocal evidence, using an LLM jury whose output is
validated against human coding at every stage. The application of the model in organisations is
not evaluated (future work).

Structure: Factor-Criteria-Metric (McCall et al. 1977), operationalised after Quamoco (Wagner et
al. 2015) and GQM (Basili et al. 1994). No weights: the result is a profile per dimension; within a
dimension the unweighted mean of its criteria, no overall score across dimensions.

Independence: the authors' planned commercial product (Ascios Assess) is **not** a seed model; the
comparison happens after publication. The competing-interests statement names the planned use.

## 2. Research questions

- **RQ1** Which dimensions, criteria and metrics characterise the quality of AI adoption in
  organisations, as derived from existing models and multivocal evidence?
- **RQ2** How reliable and valid is an LLM-jury-based derivation of such a model compared with
  human coding, at the stages of search, screening, extraction and abstraction?
- **RQ3** How completely does the derived model cover existing AI maturity and readiness models
  and regulatory frameworks (EU AI Act, ISO/IEC 42001, NIST AI RMF), and how traceable is each
  metric to its evidence?

## 3. Review type and tooling

Multivocal literature review after Garousi, Felderer & Mäntylä (2019), with Kitchenham & Charters
(2007) for the formal stream. System of record: ReviQ (project type `mlr`), with three projects:
the main project, a calibration project and a validation project. The latter two contain only
their samples and only the human reviewers R1 and R2, so that the gold standard is coded without
sight of any judge rationale.

LLM judges are ReviQ reviewers. Their votes enter through ReviQ's decision import; decisions the
jury settles are recorded through ReviQ's conflict resolution with the rule, the posterior and the
model versions in the resolution note.

## 4. Seed models

Selection: publicly accessible; subject is AI adoption or AI capability of organisations (not single
AI systems); explicit structure (at least dimensions); 2018 or later.

Candidates (final selection at G0): Jöhnk et al. 2021; Hansen et al. 2024; Fukas et al. 2021;
Akbarighatar 2022; Holmström 2022; Heger et al. 2025; Dreyling et al. 2024; MITRE AI Maturity Model
(2023); Microsoft Cloud Adoption Framework (AI); Google Cloud AI Adoption Framework (2020); AWS
CAF-AI (2024); NIST AI RMF 1.0; ISO/IEC 42001:2023. Gartner's AI Maturity Model only if publicly
described in sufficient detail, otherwise excluded with that reason. ISO/IEC 25059 and Siebert et
al. 2022 serve as system-quality references for delimitation, not as seeds.

Final seed list (G0): the candidates above. Gartner's AI Maturity Model is excluded, because no
public description with an explicit structure was identified; this is reconsidered only if one is
found during the search, and then reported as a deviation.

## 5. Search strategy

### 5.1 Sources

Only openly accessible sources (no licensed database access):

| Stream | Source | Access |
|---|---|---|
| Formal | OpenAlex (`title_and_abstract.search` or its current equivalent, cursor paging) | API |
| Formal | Semantic Scholar bulk search | API |
| Formal | arXiv | API (through creel) |
| Formal | Google Scholar | SearchApi.io through creel (`engine = google_scholar`); hits resolved against OpenAlex by DOI or title and imported as formal records; unresolvable hits go to the grey stream |
| Grey | Google web search | SearchApi.io through creel (`engine = google`), query set 5.4 |
| Snowballing | backward and forward on included formal sources | OpenAlex references and citations |

Full texts: open access only, located through OpenAlex and Unpaywall; grey full texts from the
creel archive (WARC, SHA-256).

The coverage of these sources is not assumed but measured (quasi-sensitivity on the QGS holdout,
5.3) and reported as a threat to validity.

### 5.2 Concept blocks (canonical form, `search/concepts.toml`)

- **A – AI:** "artificial intelligence", "machine learning", "generative AI", "GenAI",
  "large language model(s)", "AI system(s)"
- **O – Organisation/adoption:** adoption, implementation, deployment, integration, governance,
  readiness, maturity, capability/capabilities, transformation
- **M – Model artefact:** "maturity model", "readiness model", "maturity assessment",
  "readiness assessment", "capability model", "quality model", "assessment framework",
  "assessment model", "maturity framework", "readiness framework", "adoption framework",
  "governance framework"
- **E – Evidence on factors/metrics:** "success factor(s)", "critical factor(s)", barrier(s),
  enabler(s), "best practice(s)", "lessons learned", metric(s), "key performance indicator(s)",
  KPI(s), measurement
- **K – Context:** organisation/organization, enterprise, firm, company, "public sector", SME,
  business

Strings: **S1** (models, precise) = A near O, AND M; **S2** (evidence, broad) = A near adoption
terms, AND K, AND E. Period 2018–2026, English, document types article, conference paper, review.
Proximity is used only where the source supports it (verified per source, 5.5). If S2 exceeds about
8,000 records by the OpenAlex count, G1 decides on a narrowing, documented.

`[Final strings per source, set at G1]`

### 5.3 Quasi-gold standard and search-string selection

QGS candidates: the sources of the seed models, of known reviews (Sadiq et al. 2021; Akbarighatar
2022; Akbarighatar et al. 2023; Sun 2026; Reichl & Gruenbichler 2023) and of the reference list,
enriched through OpenAlex. Split deterministically (seed in `study.toml`) into **dev (60 %)** and
**holdout (40 %)**; the holdout is not used before G1.

Candidate strings: block ablation (each block dropped or widened, proximity 3/5/10) plus at most
ten jury suggestions; jury terms count only if they occur at least once in QGS-dev. Per candidate:
quasi-sensitivity on QGS-dev by local Boolean evaluation over title, abstract and keywords; hit
count by OpenAlex `meta.count` (an estimate); precision estimated by the jury on 50 random hits.

Selection rule (**a priori**): maximum estimated precision subject to quasi-sensitivity (dev) ≥ 0.90
and hit count ≤ budget `[budget, set at G1]`; on a tie the shorter string. After G1, quasi-sensitivity
on the holdout is reported once; below 0.80 is a deviation that reopens G1.

### 5.4 Grey query set (creel)

Fifteen Google queries with 5 pages each (`gl = us`, `hl = en`, `render_js = false`, no snowballing),
plus two arXiv queries with 3 pages: the query set of the study brief (C.5) without its two German
queries. No premium or stealth proxy; a source that blocks plain retrieval counts under EC3 with
its recorded cause. Stopping: effort-bounded (pages) and theoretical saturation (last page without
a new relevant hit by jury preview → no further pages in a later run).

Google Scholar queries: `[derived from S1 and S2 as plain English queries, set at G1]`, 10 pages each.

### 5.5 Syntax verification

Before G1 the syntax of every executed source (OpenAlex, Semantic Scholar, arXiv, Google, Google
Scholar) is checked against the provider's official documentation; version, URL and date are
recorded. A provisional check from search excerpts (PLAN.md, section 8) suggests that the OpenAlex
documentation now supports proximity and wildcards for unstemmed search, contrary to the study
brief; the choice between stemmed search without wildcards and `search.exact` with wildcards is
made at G1.

## 6. Selection criteria

| Label | Criterion | Phase | short_label |
|---|---|---|---|
| IC1 | Addresses the adoption, use, governance or maturity of AI in organisations | screening | org AI adoption |
| IC2 | Contains a model or framework, or statements on factors, criteria, practices or measures | screening | model or factors |
| IC3 | Published 2018–2026 | screening | period |
| EC1 | Only technical properties of individual AI systems, without reference to the organisation | screening | system-only |
| EC2 | AI only as a tool within an application domain, without statements on its adoption | screening | domain application |
| EC3 | No open-access full text, or a grey source without content (creel causes) | full-text | no full text |
| EC4 | Not in English | screening | language |
| EC5 | Duplicate or earlier version of the same work | screening | duplicate |
| EC6 | Pure advertising or product description without substantive statements (grey) | screening | marketing |

Records without an abstract in the open indices are screened on title alone and included in case of
doubt; their share is reported.

## 7. Selection procedure: adaptive LLM jury

### 7.1 Judges

One judge per model family, at least three families, one of them open-weight and run locally:
J1 Anthropic, J2 OpenAI, J3 Google, J4 open-weight (Ollama). Each family has a ladder from mid-tier
to top-tier; calibration keeps the mid-tier rung if its estimated sensitivity on the anchor sample
is at most 2 percentage points below the top rung (**a priori**), otherwise the top rung. Model ids
are pinned exactly at G2 (no aliases; the local model by digest).

`[Pinned model ids and parameters per judge, set at G2]`

No judge evaluates text that a model of its own family produced or summarised: extraction by J1 and
J2, naming and evaluation of model-generated text by J3 and J4.

### 7.2 Votes

Each judge returns per record: decision I/E/U, the decisive criterion label, a short rationale and a
confidence between 0 and 1, as JSON validated against a schema. Unparseable answers count as U.
Every call is cached by a hash over provider, model id, parameters, prompt version and text, and
input; the cache is part of the replication package, and every result can be reproduced from it
without an API key.

### 7.3 Aggregation and stopping rule (a priori)

1. **Anchor sample:** 100 records, stratified by stream, voted on by all judges. A latent class
   model (Dawid & Skene 1979) estimates each judge's sensitivity and specificity from their
   agreement; the same sample yields Krippendorff's α and Gwet's AC1 between judges.
2. **First round:** two judges of different families on every other record; the posterior
   probability of relevance P_rel follows from their votes and the estimated error rates.
3. **Stopping rule (recall-first):** exclude only if P_rel ≤ 0.02; pass on to the next phase if
   P_rel ≥ 0.5; otherwise a further round (third judge, then a second run of the least certain
   judge, then an arbiter: the top rung of a family that has not voted on the record). At most four
   rounds. U and unparseable answers count as votes for inclusion and trigger the next round.
4. **Remaining records** after four rounds go to the human reviewers through ReviQ's conflict view.

### 7.4 Reliability gate per phase (a priori)

- Krippendorff's α between judges on the anchor sample ≥ 0.667 (lower bound of a bootstrap CI,
  2,000 resamples, fixed seed);
- model-based recall estimate ≥ 0.95;
- **audit of exclusions:** n = 3/ε random excluded records with ε = 0.01 (n = 300), reviewed by
  humans; zero includes found bounds the error rate at about 1 % (rule of three). Any include found
  lowers the exclusion threshold, re-examines the affected exclusions and repeats the audit.

If the gate fails before G2, the per-criterion disagreement is analysed and the criteria wording
may be sharpened, with approval; after G2 the prompts do not change (12).

### 7.5 Calibration and validation

- **Calibration** (prompt development): 50 records, stratified academic/grey, coded independently
  by R1 and R2 in the calibration project; three runs per judge for run-to-run stability. Burnt
  after use.
- **G2: prompt freeze.** Prompt hashes are recorded; a frozen prompt that changes refuses to load.
- **Validation:** about 300 records, stratified by stream and by jury outcome (unanimous I,
  unanimous E, mixed), disjoint from calibration, coded independently by R1 and R2 in the
  validation project; disagreements resolved in discussion and documented (gold standard).
- **Baseline:** TF-IDF with logistic regression trained on the calibration set (Madeyski et al.
  2025).

The same procedure applies to the full-text phase (EC3 is decided there).

## 8. Quality assessment

Scale 0 / 0.5 / 1. Formal sources: aim stated; method described; model or factors derived rather
than asserted; validation present; limitations stated (QA-A1–A5). Grey sources (Garousi et al.
2019): authority of the producer, methodology recognisable, objectivity, date present and recent,
novelty, evidence or sources given, outlet type (QA-G1–G7). Each source is scored on the list of its
stream; the jury proposes scores, humans check a sample, agreement is reported. The QA level steers
the evidence rule (10), not the inclusion.

QA level per stream (G0): the share of the attainable score on the stream's list; **high** ≥ 75 %,
**medium** ≥ 50 %, **low** below (ReviQ's default thresholds).

## 9. Data extraction

Per included source, two judges extract candidate statements independently:
`statement_id, source_id, evidence_span (verbatim), span_offsets, candidate_type {dimension |
criterion | metric/indicator | practice}, construct_label, polarity {enabler | barrier |
indicator}, measurability {quantitative | ordinal | binary | qualitative}, measurement_method,
org_context {SME | large | public | any}, lifecycle_phase, regulatory_reference, evidence_type
{empirical | case | experience report | opinion | standard}`.

Span verification: every statement needs a verbatim span that is found in the archived full text
after normalisation; statements without one are discarded and counted (hallucination rate). The two
judges are matched by span overlap (IoU ≥ 0.5); precision, recall and F1 between judges are
reported; the union is kept, single finds are flagged. Factual fields are checked on samples;
interpretative fields (`candidate_type`, `construct_label`, `measurability`) are always validated by
humans on a sample of about 100 statements.

## 10. Synthesis: from statements to the model

- Deductive-inductive: the elements of the seed models form the initial codebook; new clusters
  extend it.
- Embeddings with a locally pinned open model; deterministic agglomerative clustering; the distance
  threshold is chosen on the calibration set against a human grouping by ARI and then frozen.
- The jury names each cluster (label and definition) with randomised and swapped example order.
- Hierarchy: candidates → metrics → criteria → dimensions.
- **Evidence rule (a priori):** a metric enters the model only with at least two independent
  sources, at least one of them formal or grey with QA level "high". Grades: **A** at least three
  independent sources, at least two of them empirical formal studies; **B** at least three
  independent sources, at least one formal or grey "high"; **C** exactly the minimum rule; **D**
  below the minimum (not a metric; kept visible as a candidate with its reason).
- Validation: closed card sorting of about 150 statements by R1 and R2 (α ≥ 0.667, ARI);
  bootstrap over sources (n = 200) and run-to-run stability with median ARI ≥ 0.7 and 2.5 %
  quantile ≥ 0.5 (**a priori**).
- **G3:** model draft with labels and definitions approved by both authors.

## 11. Saturation, coverage, traceability, regulatory crosswalk

- Saturation after Guest et al. (2020) over 100 random permutations of the source order (median
  and band); threshold ≤ 5 % new criteria over two blocks.
- Coverage: every element of every seed model is mapped to a criterion or marked "discarded" with a
  reason; 100 % assigned.
- Traceability: each metric → criterion → dimension with all evidence (source, span, access time,
  SHA-256 for grey sources).
- Crosswalk: obligations of Regulation (EU) 2024/1689, ISO/IEC 42001 clauses and Annex A controls,
  NIST AI RMF subcategories → criteria; two judges, human check on a sample, uncovered obligations
  listed explicitly.

## 12. Deviations

Any change to an a-priori value, a frozen prompt, the criteria or the seed list after the gate that
fixed it is a deviation: recorded with date, reason and effect in `docs/aiqm-study/deviations.md`
and reported in the paper.

## 13. Reporting

PRISMA 2020 with three columns (databases, snowballing, grey) as produced by ReviQ; Garousi et al.
(2019) items for grey literature (search engine, country setting, pages, stopping criterion, access
log); the LLM guidelines of Baltes et al. (EMSE 2026) as a completed checklist; Madeyski, Kitchenham
& Shepperd (2025) for screening performance (recall first, MCC, full confusion matrix, non-LLM
baseline). Every figure in the paper is produced by `python -m app.judging report`.

Threats to validity are structured after Ampatzoglou et al. (2019), extended by LLM-specific
threats: hallucination, non-determinism, self-preference, position bias, data contamination; plus
the restriction to open sources and to English.

## 14. Data availability and competing interests

Replication package (to be published with the paper): ReviQ export, LLM cache, prompts,
configuration, WARC manifest (without full texts of copyrighted sources), scripts; tagged. The
protocol is kept in the repository; its approved version is fixed by commit.

Competing interests: "The authors intend to commercially apply the proposed model through a company
they are in the process of founding." (company name after registration and trademark check)
