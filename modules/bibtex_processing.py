import os
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.customization import convert_to_unicode
from bibtexparser.bwriter import BibTexWriter
from modules.common import *

def read_bib_file(file_path):
    """Read all bibtex entries from the given path"""
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as bibtex_file:
        parser = BibTexParser()
        parser.customization = convert_to_unicode  
        bib_database = bibtexparser.load(bibtex_file, parser=parser)
                
        return bib_database.entries

def get_bibtex_entries(iteration_dir, directory, filename):
    """Retrieves the bibtex entries for a given iteration, status, and library"""
    if not iteration_dir or not filename:
        raise ValueError("Invalid input: iteration_dir and filename cannot be empty")
    
    file_path = os.path.join(iteration_dir, directory, filename)
    return read_bib_file(file_path)

def write_bibtex_entries(output_path, entries):
    """Write the given bibtex entries to the given output path"""
    if not output_path:
        raise ValueError("Invalid input: output_path cannot be empty")

    db = BibDatabase()
    db.entries = entries
    writer = BibTexWriter()
    
    with open(output_path, 'w', encoding='utf-8') as bibfile:
        bibfile.write(writer.write(db))
