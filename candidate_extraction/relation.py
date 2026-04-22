import json
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ENTITIES_DIR = DATA_DIR / "entities"
RELATIONS_DIR = DATA_DIR / "relations"

RELATION_PATTERNS = [
    ("is_a", ["是一种", "属于", "可视为"]),
    ("has_component", ["包括", "包含", "由", "组成"]),
    ("uses_method", ["采用", "使用", "基于"]),
    ("affects", ["影响", "决定", "改变"]),
    ("applies_to", ["适用于", "用于", "面向"]),
    ("supports_mission", ["支持", "服务于"]),
    ("has_mechanism", ["具有", "具备"]),
    ("has_parameter", ["参数为", "取值", "设定为"]),
    ("documented_in", ["见", "记载于", "发表于"]),
]


def load_entities(path: str | Path | None = None) -> list[dict]:
    source = Path(path) if path else ENTITIES_DIR / "entities_clean.jsonl"
    if not source.exists():
        raise FileNotFoundError(f"实体文件不存在: {source}")
    records = []
    with open(source, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records



def group_by_sentence(entities: Iterable[dict]) -> dict[tuple[str, int], list[dict]]:
    grouped: dict[tuple[str, int], list[dict]] = {}
    for item in entities:
        key = (item["doc_id"], item["sentence_id"])
        grouped.setdefault(key, []).append(item)
    for items in grouped.values():
        items.sort(key=lambda row: row["start"])
    return grouped



def infer_relation(sentence: str) -> str | None:
    for relation, triggers in RELATION_PATTERNS:
        if any(trigger in sentence for trigger in triggers):
            return relation
    return None



def relation_candidates(entities: list[dict]) -> Iterable[tuple[dict, dict]]:
    for idx in range(len(entities)):
        for jdx in range(idx + 1, len(entities)):
            yield entities[idx], entities[jdx]



def predict_relations(entities_path: str | Path | None = None, out_path: str | Path | None = None) -> Path:
    RELATIONS_DIR.mkdir(parents=True, exist_ok=True)
    target = Path(out_path) if out_path else RELATIONS_DIR / "relations_raw.jsonl"
    entities = load_entities(entities_path)
    grouped = group_by_sentence(entities)
    seen = set()
    with open(target, "w", encoding="utf-8") as f:
        for (_, _), sentence_entities in grouped.items():
            if len(sentence_entities) < 2:
                continue
            sentence = sentence_entities[0]["text"]
            relation = infer_relation(sentence)
            if not relation:
                continue
            for head, tail in relation_candidates(sentence_entities):
                key = (head["doc_id"], head["sentence_id"], head["entity"], relation, tail["entity"])
                if key in seen or head["entity"] == tail["entity"]:
                    continue
                seen.add(key)
                payload = {
                    "doc_id": head["doc_id"],
                    "title": head["title"],
                    "file_name": head["file_name"],
                    "sentence_id": head["sentence_id"],
                    "head": head["entity"],
                    "head_type": head["entity_type"],
                    "relation": relation,
                    "tail": tail["entity"],
                    "tail_type": tail["entity_type"],
                    "evidence_sentence": sentence,
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    clean_path = RELATIONS_DIR / "relations_clean.jsonl"
    if target != clean_path:
        clean_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return target
