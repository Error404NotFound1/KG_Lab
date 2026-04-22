import csv
import json
import re
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
TERMS_DIR = DATA_DIR / "terminology"
ENTITIES_DIR = DATA_DIR / "entities"
PROCESSED_DIR = DATA_DIR / "processed"

# 触发词不应作为实体
TRIGGER_WORDS = {
    "包括", "包含", "组成", "由", "采用", "使用", "基于",
    "影响", "决定", "改变", "适用于", "用于", "面向",
    "支持", "服务于", "具有", "具备", "参数为", "取值",
    "设定为", "见", "记载于", "发表于", "是一种", "属于", "可视为",
}


def load_terms(term_file: str | Path | None = None) -> list[dict]:
    path = Path(term_file) if term_file else TERMS_DIR / "terms_clean.csv"
    if not path.exists():
        raise FileNotFoundError(f"术语文件不存在: {path}")
    import csv

    terms = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("keep", "Y") != "Y":
                continue
            term = (row.get("term") or "").strip()
            if not term:
                continue
            terms.append(
                {
                    "term": term,
                    "entity_type": (row.get("entity_type") or "Concept").strip() or "Concept",
                    "alias": (row.get("alias") or "").strip(),
                }
            )
    terms.sort(key=lambda item: (-len(item["term"]), item["term"]))
    return terms



def load_sentences(sentences_path: str | Path | None = None) -> list[dict]:
    path = Path(sentences_path) if sentences_path else PROCESSED_DIR / "sentences.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"句子文件不存在: {path}")
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records



def find_all_occurrences(text: str, term: str) -> Iterable[tuple[int, int]]:
    start = 0
    while True:
        index = text.find(term, start)
        if index == -1:
            break
        yield index, index + len(term)
        start = index + len(term)



def overlaps(existing: list[dict], start: int, end: int) -> bool:
    for item in existing:
        if not (end <= item["start"] or start >= item["end"]):
            return True
    return False



def infer_rule_entities(text: str) -> list[dict]:
    import re

    rules = [
        (r"[0-9]+(?:\.[0-9]+)?(?:°|度|m/s|km/h|马赫|N|Pa)", "Parameter"),
        (r"[A-Za-z]+控制", "ControlMethod"),
        (r"(?:机翼|翼型|尾翼|机身|舵面|铰接机构)", "Structure"),
    ]
    entities = []
    for pattern, entity_type in rules:
        for match in re.finditer(pattern, text):
            entities.append(
                {
                    "entity": match.group(0),
                    "entity_type": entity_type,
                    "start": match.start(),
                    "end": match.end(),
                    "source": "rule",
                }
            )
    return entities



def predict_ner(text: str, model_path: str = "models/ner", term_file: str | Path | None = None):
    terms = load_terms(term_file)
    results: list[dict] = []
    for item in terms:
        term = item["term"]
        for start, end in find_all_occurrences(text, term):
            if overlaps(results, start, end):
                continue
            results.append(
                {
                    "entity": term,
                    "entity_type": item["entity_type"],
                    "start": start,
                    "end": end,
                    "source": "dictionary",
                }
            )
    for rule_entity in infer_rule_entities(text):
        if overlaps(results, rule_entity["start"], rule_entity["end"]):
            continue
        results.append(rule_entity)
    results.sort(key=lambda item: (item["start"], -(item["end"] - item["start"])))
    return results



def train_ner(train_data: str, model_out: str = "models/ner"):
    print(f"当前项目默认采用规则与词典方式进行实体识别，训练接口保留：{train_data} -> {model_out}")



def _load_type_map(terms_final_path: Path | None = None) -> dict[str, str]:
    """从 terms_final.csv 构建 term → entity_type 映射，用于回写实体类型。"""
    path = terms_final_path or TERMS_DIR / "terms_final.csv"
    if not path.exists():
        # 降级到 terms_clean.csv
        path = TERMS_DIR / "terms_clean.csv"
    if not path.exists():
        return {}
    type_map: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            term = (row.get("term") or "").strip()
            etype = (row.get("entity_type") or "").strip()
            if term and etype and etype != "Concept":
                type_map[term] = etype
    return type_map


def clean_entities(raw_path: Path, clean_path: Path, type_map: dict[str, str]) -> int:
    """
    从 raw 实体中过滤噪声，输出真正的 clean 实体文件。
    过滤规则：
      - 实体为触发词
      - 实体长度 <= 1
      - 实体纯数字
      - 实体纯标点符号
    同时用 type_map 回写实体类型（优先使用 terms_final 中的类型）。
    返回 clean 实体数量。
    """
    PURE_NUM = re.compile(r"^\d+\.?\d*$")
    PURE_PUNCT = re.compile(r"^[\s\W]+$")
    seen: set = set()
    count = 0
    with open(raw_path, "r", encoding="utf-8") as f_in, \
         open(clean_path, "w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            entity = record.get("entity", "")
            # 过滤
            if entity in TRIGGER_WORDS:
                continue
            if len(entity) <= 1:
                continue
            if PURE_NUM.match(entity):
                continue
            if PURE_PUNCT.match(entity):
                continue
            # 用 terms_final 回写类型
            if entity in type_map:
                record["entity_type"] = type_map[entity]
            # 去重（同文档同句同实体）
            key = (record["doc_id"], record["sentence_id"], entity)
            if key in seen:
                continue
            seen.add(key)
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def predict_corpus(
    sentences_path: str | Path | None = None,
    term_file: str | Path | None = None,
    out_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """返回 (raw_path, clean_path)。"""
    ENTITIES_DIR.mkdir(parents=True, exist_ok=True)
    raw_target = Path(out_path) if out_path else ENTITIES_DIR / "entities_raw.jsonl"
    clean_target = ENTITIES_DIR / "entities_clean.jsonl"

    sentences = load_sentences(sentences_path)
    with open(raw_target, "w", encoding="utf-8") as f:
        for record in sentences:
            sentence = record["text"]
            entities = predict_ner(sentence, term_file=term_file)
            for entity in entities:
                payload = {
                    "doc_id": record["doc_id"],
                    "title": record["title"],
                    "file_name": record["file_name"],
                    "sentence_id": record["sentence_id"],
                    "text": sentence,
                    "entity": entity["entity"],
                    "entity_type": entity["entity_type"],
                    "start": entity["start"],
                    "end": entity["end"],
                    "source": entity["source"],
                }
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    type_map = _load_type_map()
    clean_count = clean_entities(raw_target, clean_target, type_map)
    print(f"[ner] raw 实体: 见 {raw_target}")
    print(f"[ner] clean 实体: {clean_count} 条（去重 + 过滤后）")
    return raw_target, clean_target
