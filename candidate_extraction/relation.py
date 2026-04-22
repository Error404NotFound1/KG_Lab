"""
改进的关系抽取模块（任务 3）

核心改进：
1. 触发词位置约束：触发词必须在 head 和 tail 之间的文本中
2. 实体黑名单：触发词本身不能出现为实体
3. 实体类型约束：特定关系类型要求特定实体类型组合
4. 距离约束：head 和 tail 的字符距离不超过阈值
5. 同义 relation 规范化
6. 真正区分 raw 和 clean（clean 是过滤后的高质量版本）
"""

import json
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ENTITIES_DIR = DATA_DIR / "entities"
RELATIONS_DIR = DATA_DIR / "relations"

# ─── 关系触发词表：(relation_type, trigger_words)
RELATION_PATTERNS = [
    ("is_a",            ["是一种", "属于", "可视为", "是一类", "即"]),
    ("has_component",   ["包括", "包含", "由", "组成", "具有以下", "主要有"]),
    ("uses_method",     ["采用", "使用", "基于", "利用"]),
    ("affects",         ["影响", "决定", "改变", "作用于", "制约"]),
    ("applies_to",      ["适用于", "用于", "面向", "针对"]),
    ("supports_mission",["支持", "服务于", "满足"]),
    ("has_mechanism",   ["具有", "具备", "通过"]),
    ("has_parameter",   ["参数为", "取值", "设定为", "表示为"]),
    ("documented_in",   ["见", "记载于", "发表于", "出自"]),
    ("part_of",         ["是", "组成部分", "属于"]),
]

# 触发词 → relation 快速查找
TRIGGER_TO_RELATION: dict[str, str] = {}
for rel, triggers in RELATION_PATTERNS:
    for t in triggers:
        TRIGGER_TO_RELATION[t] = rel

# 触发词集合（用于黑名单过滤：触发词不能作为实体）
ALL_TRIGGERS: set[str] = set(TRIGGER_TO_RELATION.keys())

# ─── 实体类型约束：relation → (allowed_head_types, allowed_tail_types)
# None 表示不限制
RELATION_TYPE_CONSTRAINTS: dict[str, tuple[set | None, set | None]] = {
    "is_a":             (None, None),
    "has_component":    (
        {"Aircraft", "Structure", "Mechanism", "ControlMethod"},
        {"Aircraft", "Structure", "Mechanism", "ControlMethod", "Performance", "Parameter"},
    ),
    "uses_method":      (
        {"Aircraft", "Mission", "Structure"},
        {"ControlMethod", "Mechanism"},
    ),
    "affects":          (
        {"Parameter", "Structure", "Mechanism", "ControlMethod"},
        {"Performance", "Parameter", "Mission"},
    ),
    "applies_to":       (
        {"ControlMethod", "Mechanism"},
        {"Aircraft", "Mission"},
    ),
    "supports_mission": (
        {"Aircraft", "Structure", "ControlMethod", "Mechanism", "Performance"},
        {"Mission"},
    ),
    "has_mechanism":    (
        {"Aircraft", "Structure"},
        {"Mechanism"},
    ),
    "has_parameter":    (
        {"Aircraft", "Structure", "Mechanism", "ControlMethod"},
        {"Parameter"},
    ),
    "documented_in":    (None, {"Document"}),
    "part_of":          (None, {"Aircraft", "Structure", "Mechanism"}),
}

# 最大 head-tail 字符距离（过远的配对噪声大）
MAX_ENTITY_DISTANCE = 80

# 最少句子保留词数（太短的句子不可信）
MIN_SENTENCE_LEN = 8


def load_entities(path: str | Path | None = None) -> list[dict]:
    source = Path(path) if path else ENTITIES_DIR / "entities_clean.jsonl"
    if not source.exists():
        raise FileNotFoundError(f"实体文件不存在: {source}")
    records = []
    with open(source, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def group_by_sentence(entities: Iterable[dict]) -> dict[tuple[str, int], list[dict]]:
    grouped: dict[tuple[str, int], list[dict]] = {}
    for item in entities:
        key = (item["doc_id"], item["sentence_id"])
        grouped.setdefault(key, []).append(item)
    for items in grouped.values():
        items.sort(key=lambda r: r["start"])
    return grouped


def find_relation_in_span(sentence: str, head_end: int, tail_start: int) -> str | None:
    """
    在 head 和 tail 之间的文本片段中查找触发词。
    head_end: head 实体结束位置
    tail_start: tail 实体开始位置
    返回最先匹配的关系类型，若无则返回 None。
    """
    if head_end > tail_start:
        # head 在 tail 后面，交换搜索区间
        span = sentence[tail_start:head_end]
    else:
        span = sentence[head_end:tail_start]

    for trigger, relation in TRIGGER_TO_RELATION.items():
        if trigger in span:
            return relation
    return None


def _type_ok(relation: str, head_type: str, tail_type: str) -> bool:
    """检查实体类型是否满足关系约束。"""
    constraint = RELATION_TYPE_CONSTRAINTS.get(relation)
    if constraint is None:
        return True
    allowed_head, allowed_tail = constraint
    if allowed_head is not None and head_type not in allowed_head:
        return False
    if allowed_tail is not None and tail_type not in allowed_tail:
        return False
    return True


def predict_relations(
    entities_path: str | Path | None = None,
    out_path: str | Path | None = None,
    clean_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """
    返回 (raw_path, clean_path)。
    raw_path: 所有触发词命中的三元组（未经类型约束过滤）
    clean_path: 经过全部约束过滤后的高质量三元组
    """
    RELATIONS_DIR.mkdir(parents=True, exist_ok=True)
    raw_target = Path(out_path) if out_path else RELATIONS_DIR / "relations_raw.jsonl"
    clean_target = Path(clean_path) if clean_path else RELATIONS_DIR / "relations_clean.jsonl"

    entities = load_entities(entities_path)

    # 过滤掉以触发词为 entity 的记录
    entities = [e for e in entities if e["entity"] not in ALL_TRIGGERS]

    grouped = group_by_sentence(entities)

    seen_raw: set = set()
    seen_clean: set = set()

    raw_count = 0
    clean_count = 0

    with open(raw_target, "w", encoding="utf-8") as f_raw, \
         open(clean_target, "w", encoding="utf-8") as f_clean:

        for (doc_id, sent_id), sent_entities in grouped.items():
            if len(sent_entities) < 2:
                continue

            sentence = sent_entities[0]["text"]

            # 句子太短，跳过
            if len(sentence) < MIN_SENTENCE_LEN:
                continue

            for i in range(len(sent_entities)):
                for j in range(i + 1, len(sent_entities)):
                    head = sent_entities[i]
                    tail = sent_entities[j]

                    # 距离约束
                    distance = abs(tail["start"] - head["end"])
                    if distance > MAX_ENTITY_DISTANCE:
                        continue

                    # 在 head~tail 之间找触发词
                    relation = find_relation_in_span(sentence, head["end"], tail["start"])
                    if not relation:
                        continue

                    # 去重（raw 层面）
                    raw_key = (doc_id, sent_id, head["entity"], relation, tail["entity"])
                    if raw_key in seen_raw or head["entity"] == tail["entity"]:
                        continue
                    seen_raw.add(raw_key)

                    payload = {
                        "doc_id": doc_id,
                        "title": head.get("title", ""),
                        "file_name": head.get("file_name", ""),
                        "sentence_id": sent_id,
                        "head": head["entity"],
                        "head_type": head["entity_type"],
                        "relation": relation,
                        "tail": tail["entity"],
                        "tail_type": tail["entity_type"],
                        "evidence_sentence": sentence,
                    }
                    f_raw.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    raw_count += 1

                    # 类型约束过滤 → clean
                    if not _type_ok(relation, head["entity_type"], tail["entity_type"]):
                        continue

                    clean_key = (doc_id, sent_id, head["entity"], relation, tail["entity"])
                    if clean_key in seen_clean:
                        continue
                    seen_clean.add(clean_key)

                    f_clean.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    clean_count += 1

    print(f"[relation] raw 三元组: {raw_count} 条")
    print(f"[relation] clean 三元组 (类型约束后): {clean_count} 条")
    return raw_target, clean_target
