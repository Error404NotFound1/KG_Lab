import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_CSV = ROOT / "data" / "metadata" / "documents.csv"
SRC_DIR = ROOT / "data" / "text"
DST_DIR = ROOT / "data" / "text_ascii"
MAP_CSV = ROOT / "data" / "metadata" / "file_name_mapping_ascii.csv"

SLUG_MAP = {
    "DOC001": "reusable_space_vehicle_structure_design",
    "DOC002": "space_shuttle_aerodynamics_analysis",
    "DOC003": "aircraft_aerodynamic_design",
    "DOC004": "guo_tingyu_cja_paper",
    "DOC005": "aircraft_structure_design",
    "DOC006": "morphing_aircraft_morphing_modes_and_aerodynamic_layout_review",
    "DOC007": "morphing_aircraft_control_technology_review",
    "DOC008": "morphing_aircraft_and_structures_book",
    "DOC009": "aerospace_morphing_flight_editorial_bao_weimin",
    "DOC010": "aerospace_morphing_flight_status_and_future_liu_sijia",
    "DOC011": "spacecraft_flight_dynamics_principles_xiao_yelun",
    "DOC012": "astronautical_flight_dynamics",
    "DOC013": "cja_morphing_aircraft_paper",
    "DOC014": "cross_domain_morphing_aircraft_scheme_and_aerodynamics_an_yingtao",
    "DOC015": "cross_domain_morphing_aircraft_self_learning_mpc_attitude_control_jia_zhengyu",
}


def main() -> None:
    DST_DIR.mkdir(parents=True, exist_ok=True)
    rows = []

    with open(DOCS_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        records = list(reader)

    for rec in records:
        doc_id = rec["doc_id"]
        old_name = rec["file_name"]
        new_name = f"{doc_id.lower()}_{SLUG_MAP.get(doc_id, 'file')}.txt"
        shutil.copy2(SRC_DIR / old_name, DST_DIR / new_name)
        rows.append(
            {
                "doc_id": doc_id,
                "original_file_name": old_name,
                "ascii_file_name": new_name,
            }
        )

    with open(MAP_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["doc_id", "original_file_name", "ascii_file_name"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"copied={len(rows)}")
    print(DST_DIR)
    print(MAP_CSV)


if __name__ == "__main__":
    main()
