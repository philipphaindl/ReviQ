import os
from modules.common import *
from modules.checks import *
from modules.sheet_selected_studies import *
from modules.sheet_statistics import *
from modules.sheet_review_protocol import *
from modules.sheet_search_strings_libraries import *
from modules.selection import *

if os.path.exists(PROTOCOL_FILENAME):
    os.remove(PROTOCOL_FILENAME)

wb = openpyxl.Workbook()

process_search_strings_and_libraries(wb, config)
prepare_review_protocol(wb)

start_row_id = 2
for conf in config["iterations"]:

    iteration_conf = IterationConfig(conf, os.path.join(config["base_dir"], conf["dir"]), parse_search_string(conf))
    duplicates_detection_config = DuplicationDetectionConfig([], [])
    selection_result = SelectionResult({}, {}, {})

    check_manual_evaluations(iteration_conf)

    sheet = wb[REVIEW_PROTOCOL_SHEET_NAME]
    last_row_id, metrics = evaluate_studies(iteration_conf, sheet, start_row_id, duplicates_detection_config, selection_result)

    print(conf["dir"])
    update_review_protocol(wb, start_row_id, iteration_conf, selection_result)
    total_selected = write_selected_studies(iteration_conf, selection_result)
    process_statistics(wb, iteration_conf, conf["dir"], metrics, total_selected, selection_result)
    print()
    start_row_id = last_row_id

process_selected_studies(wb, iteration_conf, selection_result)

wb.save(PROTOCOL_FILENAME)
