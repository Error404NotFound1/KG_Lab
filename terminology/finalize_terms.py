"""
术语表定稿脚本（任务 1）
- 读取 terms_clean.csv（规则清洗后的 1200 行主表）
- 合并 terms_clean_llm.csv 的 entity_type / alias 修正结果
- 过滤触发词、单字、无意义术语
- 对仍为 Concept 的术语用规则再推断一次类型
- 输出 data/terminology/terms_final.csv 和 alias_final.csv
"""

import csv
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMS_DIR = PROJECT_ROOT / "data" / "terminology"

# ─── 不允许作为有效实体的触发词黑名单（这些词同时也是关系抽取的触发词）
TRIGGER_WORDS = {
    "包括", "包含", "组成", "由", "采用", "使用", "基于",
    "影响", "决定", "改变", "适用于", "用于", "面向",
    "支持", "服务于", "具有", "具备", "参数为", "取值",
    "设定为", "见", "记载于", "发表于", "是一种", "属于",
    "可视为",
}

# 明显无意义词汇（硬编码黑名单，补充）
NOISE_TERMS = {
    "和式", "则有", "于是", "最后", "可知", "全球鹰", "重力",
    "运动学方程", "翼根效应", "亚声速", "迎风面",
    "应用变体技术减少了50",  # 乱码/截断词
    # 逻辑连接词
    "首先", "其次", "然后", "最后", "总之", "综上所述", "因此", "所以",
    "但是", "然而", "因为", "由此", "从而", "那么", "同样", "一般情况下",
    "当然", "第一", "第二", "第三", "也就是说", "实际上", "简称",
    "由图", "由表", "对于单", "以上", "续表", "的关系", "的变化",
    "在式", "对于", "有关", "因而", "这时", "由此可见", "概述",
    # 地名/人名
    "苏联", "西安", "米格", "幻影", "阿波罗",
    # 模糊量词
    "增大", "减小", "变大", "变小", "增加", "减少",
    # 书面语
    "矢量", "位置", "材料", "试验", "概率", "强度",
}

# 语用词正则（匹配后直接过滤）
import re as _re
_PRAGMATIC_PATTERNS = [
    _re.compile(r"^(如果|虽然|尽管|对于|由于|关于|通过|为了|当|若|则|使得|根据|根)"),
    _re.compile(r"^(升力|阻力|力矩|面积|位置|强度|材料|试验|载荷|压力|应力|质量|速度|时间)$"),  # 太泛化的物理量
    _re.compile(r"(续表|第\d+章|图\d|表\d|式\d|附录)"),
    _re.compile(r"^[的地得]"),  # 助词开头
    _re.compile(r"锥如|到织|对于单|的变化|的关系|的形式"),  # 截断词
]

# 允许保留的英文术语白名单
ENGLISH_WHITELIST = {"morphing", "aircraft", "wing", "uav", "mpc"}

# 补充类型推断规则（比 term_extraction.py 中更精细）
TYPE_RULES = [
    ("ControlMethod", ["控制律", "控制方法", "控制策略", "控制算法", "预测控制", "自适应控制",
                       "滑模控制", "反步法", "遗传算法", "强化学习", "深度学习", "神经网络",
                       "MPC", "PID", "LQR", "DDPG", "规划", "决策", "优化算法",
                       "气动实验与测量控制", "采样", "策略", "控制", "偏航"]),
    ("Mechanism",    ["变形", "折叠", "展开", "切换", "变构", "morphing", "驱动机制",
                       "铰接机构", "后缘增升", "三缝", "双折叠", "变后掠", "折展",
                       "分离", "机翼变体", "机构驱动", "展收", "弯曲", "变换"]),
    ("Structure",    ["机翼", "翼型", "翼面", "机身", "尾翼", "舵面", "蒙皮", "隔框",
                       "翼梁", "铰链", "前缘", "后缘", "翼根", "翼尖", "垂尾", "平尾",
                       "翼展", "夹层", "复合材料结构", "结构设计", "活动机翼", "固定机翼",
                       "wing", "fuselage", "flap", "装配", "螺栓", "螺钉", "密封圈",
                       "铝合金", "环氧树脂", "胶接", "转轴", "铰接", "侧缘", "上机翼"]),
    ("Performance",  ["升阻比", "稳定性", "机动性", "气动特性", "气动性能", "鲁棒性",
                       "可靠性", "控制品质", "升力系数", "阻力系数", "俯仰力矩",
                       "诱导阻力", "响应速度", "振动", "弯矩", "推力", "航程",
                       "气动热", "动稳定性", "最优解", "成本低", "压力系数", "局部应力",
                       "安全系数", "载荷", "设计载荷", "诱导阻力系数", "翼载荷",
                       "上下机翼处于不同位置时双翼"]),
    ("Mission",      ["巡航", "起飞", "着陆", "机动", "跨域飞行", "再入", "轨道",
                       "返回舱", "飞行试验", "低速", "超声速", "高速", "阵风",
                       "临近空间", "飞行时间", "主要任务", "飞行阶段", "超临界"]),
    ("Parameter",    ["攻角", "迎角", "速度", "高度", "马赫数", "参数", "角度",
                       "载荷因子", "雷诺数", "展弦比", "弦长", "展长", "厚度",
                       "弯度", "俯仰角", "偏航角", "上反角", "四元数", "初始应变",
                       "约束条件", "设计变量", "声速", "倍弦长", "热导率",
                       "相对厚度", "相对面积", "热膨胀", "热导", "温度梯度",
                       "地面坐标系", "迎风", "坐标", "参考面积", "机翼面积"]),
    ("Aircraft",     ["飞行器", "航天器", "飞机", "无人机", "变体", "空天", "变构",
                       "aircraft", "uav", "drone", "飞船", "返回舱", "空天飞行器",
                       "喷气运输机", "跨域", "双折叠翼变体"]),
    ("Document",     ["文献", "论文", "项目", "综述", "期刊", "学报"]),
]


def _is_english_noise(term: str) -> bool:
    """纯英文术语：不在白名单内的一律过滤。"""
    lower = term.lower()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9\-]*$", term):
        return lower not in ENGLISH_WHITELIST and term.upper() not in {"MPC", "UAV", "LQR", "PID"}
    return False


def _infer_type(term: str, current_type: str) -> str:
    """
    对仍为 Concept 或 空 的术语尝试推断类型。
    已经有明确类型（非 Concept）的保持不变。
    """
    if current_type and current_type not in ("Concept", ""):
        return current_type
    for entity_type, keywords in TYPE_RULES:
        if any(kw in term for kw in keywords):
            return entity_type
    return "Concept"


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def finalize_terms(
    clean_path: Path | None = None,
    llm_path: Path | None = None,
    out_terms_path: Path | None = None,
    out_alias_path: Path | None = None,
) -> dict[str, Path]:
    """
    主函数：合并 + 过滤 + 补标，输出 terms_final.csv 和 alias_final.csv。
    """
    clean_csv = clean_path or TERMS_DIR / "terms_clean.csv"
    llm_csv = llm_path or TERMS_DIR / "terms_clean_llm.csv"
    out_terms = out_terms_path or TERMS_DIR / "terms_final.csv"
    out_alias = out_alias_path or TERMS_DIR / "alias_final.csv"

    # ── 1. 读取主表
    main_rows = _load_csv(clean_csv)
    print(f"[finalize] 主表术语数: {len(main_rows)}")

    # ── 2. 读取 LLM 清洗结果，建立 term → {entity_type, alias} 映射
    llm_rows = _load_csv(llm_csv)
    llm_override: dict[str, dict] = {}
    alias_rows: list[dict] = []
    for row in llm_rows:
        term = (row.get("term") or "").strip()
        if not term:
            continue
        entity_type = (row.get("entity_type") or "").strip()
        alias = (row.get("alias") or "").strip()
        llm_override[term] = {"entity_type": entity_type, "alias": alias}
        if alias:
            alias_rows.append({
                "alias": term,
                "canonical": alias,
                "entity_type": entity_type,
            })
    print(f"[finalize] LLM 修正术语数: {len(llm_rows)}，别名条数: {len(alias_rows)}")

    # ── 3. 过滤 + 合并 + 补标
    kept: list[dict] = []
    discarded_count = 0

    for row in main_rows:
        term = (row.get("term") or "").strip()
        if not term:
            continue

        # 3a. 过滤触发词
        if term in TRIGGER_WORDS:
            discarded_count += 1
            continue

        # 3b. 过滤噪声词
        if term in NOISE_TERMS:
            discarded_count += 1
            continue

        # 3c. 过滤纯英文非白名单词
        if _is_english_noise(term):
            discarded_count += 1
            continue

        # 3d. 过滤长度 <= 1
        if len(term) <= 1:
            discarded_count += 1
            continue

        # 3e. 过滤纯数字
        if re.match(r"^\d+$", term):
            discarded_count += 1
            continue

        # 3f. 过滤"第X章""图X""表X"等格式词
        if re.match(r"^[图表式第]\d", term):
            discarded_count += 1
            continue

        # 3g. 语用词正则过滤（逻辑连词、截断词等）
        if any(pat.search(term) for pat in _PRAGMATIC_PATTERNS):
            discarded_count += 1
            continue

        # 3h. 致命 Bug 修复：如果大模型清洗过了，但该词没在大模型的输出白名单里，说明被大模型判定为垃圾(keep=N)，直接丢弃！
        if llm_override and term not in llm_override:
            discarded_count += 1
            continue

        # ── 合并 LLM 的 entity_type / alias
        current_type = (row.get("entity_type") or "Concept").strip() or "Concept"
        current_alias = (row.get("alias") or "").strip()
        if term in llm_override:
            override = llm_override[term]
            if override["entity_type"] and override["entity_type"] not in ("Concept", ""):
                current_type = override["entity_type"]
            if override["alias"] and not current_alias:
                current_alias = override["alias"]

        # ── 对仍为 Concept 的术语再推断一次
        final_type = _infer_type(term, current_type)

        kept.append({
            "term": term,
            "freq": row.get("freq", ""),
            "tfidf": row.get("tfidf", ""),
            "pmi": row.get("pmi", ""),
            "score": row.get("score", ""),
            "entity_type": final_type,
            "keep": "Y",
            "alias": current_alias,
        })

    print(f"[finalize] 过滤掉: {discarded_count} 条，保留: {len(kept)} 条")

    # ── 4. 统计类型分布
    from collections import Counter
    type_dist = Counter(r["entity_type"] for r in kept)
    print("[finalize] 实体类型分布:", dict(type_dist))

    # ── 5. 写出
    _write_csv(out_terms, kept, ["term", "freq", "tfidf", "pmi", "score", "entity_type", "keep", "alias"])
    _write_csv(out_alias, alias_rows, ["alias", "canonical", "entity_type"])

    print(f"[finalize] 已写出: {out_terms}")
    print(f"[finalize] 已写出: {out_alias}")
    return {"terms_final": out_terms, "alias_final": out_alias}


if __name__ == "__main__":
    finalize_terms()
