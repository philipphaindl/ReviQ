import yaml
from dataclasses import dataclass
import re

PROTOCOL_FILENAME = "protocol.xlsx"
RETRIEVED_DIRNAME = "0_retrieved"
DEDUPLICATED_DIRNAME = "1_deduplicated"
NEEDING_MANUAL_EVALUATION_DIRNAME = "2_needing_manual_evaluations"
AFTER_MANUAL_EVALUATION_DIRNAME = "3_after_manual_evaluations"
MANUAL_EVALUATION_FILENAME = "manual_evaluations.xlsx"
CONFIG_FILENAME = 'config.yml'
FINAL_STUDIES_BIBFILE = "selected_studies.bib"
SELECTED_STUDIES_SHEET_NAME = "Selected Studies"
STATISTICS_SHEET_NAME = "Statistics"
LIBRARIES_SHEET_NAME = "Libraries and Search Strings"
REVIEW_PROTOCOL_SHEET_NAME = "Review Protocol"

@dataclass
class IterationConfig:
    iteration_config: dict
    iteration_dir: str
    keywords: list

    @property
    def threshold(self):
        return self.iteration_config["quality-score-treshold"]

@dataclass
class DuplicationDetectionConfig:
    dois: list
    titles_and_venues: list

@dataclass
class SelectionResult:
    results: dict
    papers: dict
    categories: dict

class Paper:

    def __init__(self, author, title, year, citekey = None):
        self.author = author
        self.title = title
        self.year = year
        self.codes = {}
        self.citekey = citekey

    def append_code(self, key, value):
        if key in self.codes:
            self.codes[key].add(value)
        else:
            self.codes[key] = set()
            self.codes[key].add(value)

def parse_search_string(iteration_config):
    if not iteration_config or "keywords" not in iteration_config:
        raise ValueError("Missing 'keywords' in iteration configuration")
    
    return [keyword.lower() for keyword in iteration_config["keywords"]]

def get_citekey(title, author, year, papers):
    """Retrieves the citekey based on title, author, and year."""
    sanitized_search_title = re.sub(r"[^a-zA-Z0-9\s]", "", title).lower()
    
    for library in papers:
        for paper in papers[library]:
            if paper.title:
                sanitized_paper_title = re.sub(r"[^a-zA-Z0-9\s]", "", paper.title).lower()
                if sanitized_search_title in sanitized_paper_title:
                    if author.split()[0].lower() in paper.author.split()[0].lower() and paper.year == year:
                        return paper.citekey
    return None

def get_entries_by_citekey(entries, included):
    if not entries or not included:
        return []
    
    return [entry for entry in entries if entry.get("ID") in included]

try:
    with open(CONFIG_FILENAME, 'rt') as f:
        config = yaml.safe_load(f)
except (FileNotFoundError, yaml.YAMLError) as e:
    print(f"Error loading {CONFIG_FILENAME}: {e}")
    config = {}