import { PhaseComingSoon } from '../components/ui'

export function EligibilityStub() {
  return (
    <PhaseComingSoon
      phase="Phase 3"
      icon="📄"
      title="Full-Text Eligibility"
      description="Assess full-text eligibility of papers that passed title/abstract screening. Same I/E/U interface with full-text specific criteria and conflict resolution."
      planned={[
        'Per-paper full-text I/E/U decision form',
        'Full-text specific I/E criteria (configured in Setup)',
        'PDF/URL link per paper',
        'Full-text inaccessible flag (E5)',
        'Same conflict resolution mechanism as Screening',
        'Progression funnel: screened → assessed → included',
      ]}
    />
  )
}

export function SnowballingStub() {
  return (
    <PhaseComingSoon
      phase="Phase 4"
      icon="❄️"
      title="Snowballing"
      description="Forward and backward citation snowballing with saturation detection. Manage multiple iterations and track which new papers each iteration adds."
      planned={[
        'Create forward / backward snowballing iterations',
        'Import citing-papers BibTeX per iteration',
        'Per-iteration I/E/U screening (same criteria)',
        'Duplicate detection against existing corpus',
        'Saturation detection: 0 new included = saturated',
        'Per-iteration Kappa calculation',
        'Iteration comparison table (saturation curve)',
      ]}
    />
  )
}

export function QualityStub() {
  return (
    <PhaseComingSoon
      phase="Phase 5"
      icon="⭐"
      title="Quality Assessment"
      description="Score each included paper on QA1–QAn criteria configured in Setup. Papers below the medium threshold are flagged for descriptive-only reporting."
      planned={[
        'Per-paper QA scoring form (0 / 0.5 / 1.0 per criterion)',
        'Auto-calculated total score and quality level (High/Medium/Low)',
        'Color-coded quality indicator per paper',
        'Low-quality warning flag',
        'QA summary view: all papers ranked by score',
        'R2 validation notes',
      ]}
    />
  )
}

export function ExtractionStub() {
  return (
    <PhaseComingSoon
      phase="Phase 7"
      icon="📝"
      title="Data Extraction"
      description="Structured data extraction for each included paper. Field schema is fully configurable per project (research type, contribution type, domain-specific fields)."
      planned={[
        'Per-paper extraction form with project schema',
        'Dropdown, text, boolean, and number field types',
        'Research type and contribution type classification',
        'Domain-specific event/feature matrix',
        'Bulk edit: apply value to multiple papers',
        'Extraction completion indicator',
      ]}
    />
  )
}

export function ResultsStub() {
  return (
    <PhaseComingSoon
      phase="Phase 8"
      icon="📊"
      title="Results & Visualization"
      description="Auto-generated charts, PRISMA flow diagram, and export package. All figures derive from the actual decision data — no manual entry required."
      planned={[
        'PRISMA 2020 flow diagram (auto-generated SVG)',
        'Publications per year (horizontal bar chart)',
        'Research type distribution',
        'Contribution type distribution',
        'Quality assessment summary (stacked bar)',
        'Kappa dashboard (DB stream vs. snowballing)',
        'Excel export (multi-sheet, professional format)',
        'PDF export (publication-quality appendix)',
        'BibTeX export of included studies',
        'Project archive (.slrw replication package)',
      ]}
    />
  )
}
