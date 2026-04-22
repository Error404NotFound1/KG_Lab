import json
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ANNOTATION_DIR = DATA_DIR / "annotations"
PROCESSED_DIR = DATA_DIR / "processed"
ENTITIES_DIR = DATA_DIR / "entities"
RELATIONS_DIR = DATA_DIR / "relations"



def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows



def export_to_doccano(dataset_path: str | Path | None = None, out_path: str | Path | None = None):
    source = Path(dataset_path) if dataset_path else PROCESSED_DIR / "sentences.jsonl"
    target = Path(out_path) if out_path else ANNOTATION_DIR / "doccano_import.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(source)
    with open(target, "w", encoding="utf-8") as f:
        for row in rows:
            payload = {
                "text": row["text"],
                "meta": {
                    "doc_id": row["doc_id"],
                    "title": row["title"],
                    "sentence_id": row["sentence_id"],
                },
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return target



def import_from_doccano(project_id: int, out_path: str | Path):
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("", encoding="utf-8")
    print(f"请将 doccano 项目 {project_id} 的导出结果放入 {target}，随后即可接入评估流程。")
    return target



def convert_entities_for_eval(source_path: str | Path | None = None, out_path: str | Path | None = None) -> Path:
    source = Path(source_path) if source_path else ENTITIES_DIR / "entities_clean.jsonl"
    target = Path(out_path) if out_path else ANNOTATION_DIR / "pred_entities.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(source)
    with open(target, "w", encoding="utf-8") as f:
        for row in rows:
            payload = {
                "doc_id": row["doc_id"],
                "sentence_id": row["sentence_id"],
                "entity": row["entity"],
                "entity_type": row["entity_type"],
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return target



def convert_relations_for_eval(source_path: str | Path | None = None, out_path: str | Path | None = None) -> Path:
    source = Path(source_path) if source_path else RELATIONS_DIR / "relations_clean.jsonl"
    target = Path(out_path) if out_path else ANNOTATION_DIR / "pred_relations.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(source)
    with open(target, "w", encoding="utf-8") as f:
        for row in rows:
            payload = {
                "doc_id": row["doc_id"],
                "sentence_id": row["sentence_id"],
                "head": row["head"],
                "relation": row["relation"],
                "tail": row["tail"],
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return target
