import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# ===== 路径配置 =====
PROJECT_ROOT = Path(r"d:\kecheng\KG\KG_Lab")
ENTITIES_PATH = PROJECT_ROOT / "data" / "entities" / "entities_clean.jsonl"
RELATIONS_PATH = PROJECT_ROOT / "data" / "relations" / "relations_clean.jsonl"

OUTPUT_DIR = Path(r"d:\kecheng\KG\report\figures")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ENTITY_CSV = OUTPUT_DIR / "实体类型分布统计表.csv"
RELATION_CSV = OUTPUT_DIR / "关系类型分布统计表.csv"
ENTITY_FIG = OUTPUT_DIR / "实体类型分布统计图.png"
RELATION_FIG = OUTPUT_DIR / "关系类型分布统计图.png"

# ===== 中文显示配置 =====
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["axes.facecolor"] = "white"

# ===== 更鲜艳但仍保持学术感的配色 =====
ACADEMIC_COLORS = [
    "#3B82F6",  # 亮蓝
    "#10B981",  # 翠绿
    "#F59E0B",  # 琥珀橙
    "#EF4444",  # 鲜红
    "#8B5CF6",  # 亮紫
    "#06B6D4",  # 青蓝
    "#84CC16",  # 黄绿
    "#F97316",  # 橙红
    "#EC4899",  # 玫红
    "#14B8A6",  # 青绿
    "#6366F1",  # 靛蓝
    "#EAB308",  # 明黄
]


ENTITY_TYPE_LABELS = {
    "Aircraft": "飞行器类型",
    "Structure": "结构部件",
    "Mechanism": "变形机制",
    "ControlMethod": "控制方法",
    "Performance": "性能指标",
    "Mission": "任务场景",
    "Parameter": "参数变量",
    "Document": "参考文献",
    "Concept": "通用概念",
    "Unknown": "未知类型",
}


def load_jsonl(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def count_entity_types(rows):
    counter = Counter()
    for row in rows:
        entity_type = row.get("entity_type", "Unknown")
        counter[entity_type] += 1
    return counter


def count_relation_types(rows):
    counter = Counter()
    for row in rows:
        relation = row.get("relation", "Unknown")
        counter[relation] += 1
    return counter


def save_counter_to_csv(counter: Counter, csv_path: Path, col1: str, col2: str):
    df = pd.DataFrame(counter.items(), columns=[col1, col2]).sort_values(by=col2, ascending=False)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return df


def preprocess_entity_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["实体类型代码"] = df["实体类型"]
    df["实体类型"] = df["实体类型"].map(lambda x: ENTITY_TYPE_LABELS.get(x, x))
    return df


def plot_entity_distribution(df: pd.DataFrame, fig_path: Path):
    df = preprocess_entity_df(df)
    colors = ACADEMIC_COLORS[:len(df)]

    fig, ax = plt.subplots(figsize=(10, 8))

    wedges, texts, autotexts = ax.pie(
        df["数量"],
        labels=df["实体类型"],
        autopct="%1.1f%%",
        startangle=90,
        counterclock=False,
        colors=colors,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.6},
        pctdistance=0.78,
        labeldistance=1.08,
        textprops={"fontsize": 11, "color": "#333333"},
    )

    centre_circle = plt.Circle((0, 0), 0.45, fc="white")
    ax.add_artist(centre_circle)

    total = int(df["数量"].sum())
    ax.text(0, 0.06, "实体总数", ha="center", va="center", fontsize=12, color="#666666")
    ax.text(0, -0.08, f"{total:,}", ha="center", va="center", fontsize=18, fontweight="bold", color="#2563EB")

    for autotext in autotexts:
        autotext.set_color("#222222")
        autotext.set_fontsize(10)

    ax.set_title("变构飞行器知识图谱实体类型分布统计图", fontsize=16, pad=18)
    plt.tight_layout()
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()



def plot_relation_distribution(df: pd.DataFrame, fig_path: Path):
    df = df.sort_values(by="数量", ascending=True).reset_index(drop=True)
    colors = ACADEMIC_COLORS[:len(df)]

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(
        df["关系类型"],
        df["数量"],
        color=colors,
        edgecolor="#333333",
        linewidth=0.8,
        alpha=0.97,
    )

    ax.set_title("变构飞行器知识图谱关系类型分布统计图", fontsize=16, pad=14)
    ax.set_xlabel("数量", fontsize=12)
    ax.set_ylabel("关系类型", fontsize=12)

    ax.grid(axis="x", linestyle="--", alpha=0.28, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#888888")
    ax.spines["bottom"].set_color("#888888")

    max_val = int(df["数量"].max()) if len(df) else 0
    offset = max(max_val * 0.01, 8)

    for bar in bars:
        width = bar.get_width()
        ax.text(
            width + offset,
            bar.get_y() + bar.get_height() / 2,
            f"{int(width)}",
            ha="left",
            va="center",
            fontsize=10,
            color="#222222",
        )

    plt.tight_layout()
    plt.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close()



def main():
    if not ENTITIES_PATH.exists():
        raise FileNotFoundError(f"未找到实体文件: {ENTITIES_PATH}")
    if not RELATIONS_PATH.exists():
        raise FileNotFoundError(f"未找到关系文件: {RELATIONS_PATH}")

    print("正在加载实体数据...")
    entity_rows = load_jsonl(ENTITIES_PATH)
    print(f"实体记录数: {len(entity_rows)}")

    print("正在加载关系数据...")
    relation_rows = load_jsonl(RELATIONS_PATH)
    print(f"关系记录数: {len(relation_rows)}")

    print("正在统计实体类型...")
    entity_counter = count_entity_types(entity_rows)
    entity_df = save_counter_to_csv(entity_counter, ENTITY_CSV, "实体类型", "数量")
    print(entity_df)

    print("正在统计关系类型...")
    relation_counter = count_relation_types(relation_rows)
    relation_df = save_counter_to_csv(relation_counter, RELATION_CSV, "关系类型", "数量")
    print(relation_df)

    print("正在绘制实体类型分布统计图（环形图）...")
    plot_entity_distribution(entity_df, ENTITY_FIG)

    print("正在绘制关系类型分布统计图（水平条形图）...")
    plot_relation_distribution(relation_df, RELATION_FIG)

    print("\n统计完成，输出文件如下：")
    print(f"- {ENTITY_CSV}")
    print(f"- {RELATION_CSV}")
    print(f"- {ENTITY_FIG}")
    print(f"- {RELATION_FIG}")


if __name__ == "__main__":
    main()
