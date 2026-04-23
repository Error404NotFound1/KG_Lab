"""
变构飞行器知识图谱 Web 应用
后端：FastAPI + 内存加载 kg.json（无需 Neo4j 即可运行）
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
KG_JSON = DATA_DIR / "kg" / "kg.json"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"

app = FastAPI(title="变构飞行器知识图谱应用", version="1.0.0")

# 挂载静态文件（若目录存在）
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ─── 实体类型颜色映射
TYPE_COLORS = {
    "Aircraft":      "#00d4ff",
    "Structure":     "#7c3aed",
    "Mechanism":     "#f59e0b",
    "ControlMethod": "#10b981",
    "Performance":   "#ef4444",
    "Mission":       "#8b5cf6",
    "Parameter":     "#06b6d4",
    "Document":      "#6b7280",
    "Concept":       "#374151",
}


@lru_cache(maxsize=1)
def load_kg() -> dict:
    if not KG_JSON.exists():
        return {"nodes": [], "edges": []}
    return json.loads(KG_JSON.read_text(encoding="utf-8"))


# ─── API 路由 ─────────────────────────────────────────────────

@app.get("/api/stats")
def api_stats():
    """图谱统计面板数据"""
    kg = load_kg()
    type_dist: dict[str, int] = {}
    for node in kg["nodes"]:
        t = node.get("entity_type", "Concept")
        type_dist[t] = type_dist.get(t, 0) + 1

    rel_dist: dict[str, int] = {}
    for edge in kg["edges"]:
        r = edge.get("relation", "unknown")
        rel_dist[r] = rel_dist.get(r, 0) + 1

    # 统计文献数
    doc_ids = {n["source_doc"] for n in kg["nodes"] if n.get("source_doc")}

    return {
        "entities": len(kg["nodes"]),
        "relations": len(kg["edges"]),
        "documents": len(doc_ids),
        "entity_type_distribution": type_dist,
        "relation_type_distribution": rel_dist,
        "type_colors": TYPE_COLORS,
    }


@app.get("/api/search")
def api_search(q: str = Query("", min_length=0)):
    """实体搜索：模糊匹配名称"""
    kg = load_kg()
    q = q.strip()
    if not q:
        return []
    results = [
        node for node in kg["nodes"]
        if q.lower() in node.get("name", "").lower()
    ]
    # 按名称长度升序（精确匹配优先）
    results.sort(key=lambda n: len(n.get("name", "")))
    return results[:60]


@app.get("/api/entity/{entity_id:path}")
def api_entity_detail(entity_id: str):
    """实体详情 + 相关关系 + 证据句"""
    kg = load_kg()
    node = next(
        (n for n in kg["nodes"] if n["id"] == entity_id), None
    )
    if not node:
        raise HTTPException(status_code=404, detail=f"实体不存在: {entity_id}")

    out_edges = [e for e in kg["edges"] if e["source"] == entity_id]
    in_edges  = [e for e in kg["edges"] if e["target"] == entity_id]

    # 补充邻居节点名称
    id_to_name = {n["id"]: n.get("name", n["id"]) for n in kg["nodes"]}
    for e in out_edges + in_edges:
        e["source_name"] = id_to_name.get(e["source"], e["source"])
        e["target_name"] = id_to_name.get(e["target"], e["target"])

    return {
        "entity": node,
        "color": TYPE_COLORS.get(node.get("entity_type", "Concept"), "#374151"),
        "out_relations": out_edges[:80],
        "in_relations":  in_edges[:80],
    }


@app.get("/api/subgraph/{entity_id:path}")
def api_subgraph(entity_id: str, hops: int = Query(1, ge=1, le=2)):
    """返回以 entity_id 为中心的子图（ECharts Graph 格式）"""
    kg = load_kg()
    id_to_node = {n["id"]: n for n in kg["nodes"]}

    if entity_id not in id_to_node:
        raise HTTPException(status_code=404, detail="实体不存在")

    # BFS 收集节点
    visited: set[str] = {entity_id}
    frontier: set[str] = {entity_id}
    for _ in range(hops):
        next_frontier: set[str] = set()
        for eid in frontier:
            for e in kg["edges"]:
                if e["source"] == eid and e["target"] not in visited:
                    next_frontier.add(e["target"])
                elif e["target"] == eid and e["source"] not in visited:
                    next_frontier.add(e["source"])
        visited |= next_frontier
        frontier = next_frontier
        if len(visited) > 200:
            break

    sub_nodes = [id_to_node[nid] for nid in visited if nid in id_to_node]
    sub_edges = [
        e for e in kg["edges"]
        if e["source"] in visited and e["target"] in visited
    ]

    # 转为 ECharts 格式
    echarts_nodes = [
        {
            "id": n["id"],
            "name": n.get("name", n["id"]),
            "value": n.get("entity_type", "Concept"),
            "category": n.get("entity_type", "Concept"),
            "symbolSize": 24 if n["id"] == entity_id else 14,
            "itemStyle": {
                "color": TYPE_COLORS.get(n.get("entity_type", "Concept"), "#374151"),
                "borderColor": "#ffffff" if n["id"] == entity_id else "transparent",
                "borderWidth": 3 if n["id"] == entity_id else 0,
            },
            "label": {"show": n["id"] == entity_id or hops == 1},
        }
        for n in sub_nodes
    ]
    echarts_edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "label": {"show": False, "formatter": e["relation"]},
            "lineStyle": {"opacity": 0.5, "width": 1},
            "_relation": e["relation"],
            "_evidence": e.get("evidence", ""),
        }
        for e in sub_edges
    ]

    return {"nodes": echarts_nodes, "edges": echarts_edges, "center": entity_id}


@app.get("/api/graph/overview")
def api_graph_overview(limit: int = Query(2000, ge=50, le=5000)):
    """全局图谱采样（按核心度采样），返回带有层次感的 ECharts Graph 格式"""
    kg = load_kg()

    # 计算所有节点的连接度数
    degrees = {}
    for e in kg["edges"]:
        degrees[e["source"]] = degrees.get(e["source"], 0) + 1
        degrees[e["target"]] = degrees.get(e["target"], 0) + 1

    # 根据度数降序排列节点，优先保留核心节点
    sorted_nodes = sorted(
        kg["nodes"], 
        key=lambda n: (degrees.get(n["id"], 0), n.get("entity_type", "Concept") != "Concept"), 
        reverse=True
    )
    
    selected_nodes = sorted_nodes[:limit]
    selected_ids = {n["id"] for n in selected_nodes}
    
    # 过滤出存在于被选节点间的边
    selected_edges = [
        e for e in kg["edges"]
        if e["source"] in selected_ids and e["target"] in selected_ids
    ]

    import math
    echarts_nodes = []
    for n in selected_nodes:
        deg = degrees.get(n["id"], 0)
        # 根据度数计算节点大小，大幅缩小核心节点体积，防止遮挡
        size = max(6, min(26, 6 + math.sqrt(deg) * 1.8))
        
        echarts_nodes.append({
            "id": n["id"],
            "name": n.get("name", n["id"]),
            "value": n.get("entity_type", "Concept"),
            "category": n.get("entity_type", "Concept"),
            "symbolSize": size,
            "itemStyle": {"color": TYPE_COLORS.get(n.get("entity_type", "Concept"), "#374151")},
            # 核心节点（较大）默认显示标签
            "label": {"show": size > 12, "fontSize": 10},
            "_degree": deg
        })

    echarts_edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "_relation": e["relation"],
            # 根据边的关联度，稍微降低普通边的透明度
            "lineStyle": {"opacity": 0.15, "width": 1}
        }
        for e in selected_edges
    ]

    return {
        "nodes": echarts_nodes,
        "edges": echarts_edges,
        "type_colors": TYPE_COLORS,
    }


@app.get("/api/relations")
def api_relations(
    type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=10, le=100),
):
    """按关系类型分页查询关系列表"""
    kg = load_kg()
    id_to_name = {n["id"]: n.get("name", n["id"]) for n in kg["nodes"]}

    edges = kg["edges"]
    if type:
        edges = [e for e in edges if e.get("relation") == type]

    total = len(edges)
    start = (page - 1) * page_size
    page_edges = edges[start: start + page_size]

    results = [
        {
            **e,
            "source_name": id_to_name.get(e["source"], e["source"]),
            "target_name": id_to_name.get(e["target"], e["target"]),
        }
        for e in page_edges
    ]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": results,
        "relation_types": list({e["relation"] for e in kg["edges"]}),
    }


# ─── 前端页面 ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
