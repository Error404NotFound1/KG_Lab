"""
知识图谱平台后端 — 多图谱版
每个图谱独立存放在 data/graphs/{graph_id}/
"""
from __future__ import annotations

import json
import shutil
import uuid
import asyncio
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
GRAPHS_DIR = DATA_DIR / "graphs"        # 每个子目录 = 一个知识图谱
GRAPHS_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"

app = FastAPI(title="知识图谱平台", version="2.0.0")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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


# ─── 图谱目录结构助手 ─────────────────────────────────────────

def graph_dir(graph_id: str) -> Path:
    return GRAPHS_DIR / graph_id

def graph_meta_path(graph_id: str) -> Path:
    return graph_dir(graph_id) / "meta.json"

def graph_kg_path(graph_id: str) -> Path:
    return graph_dir(graph_id) / "kg" / "kg.json"

def read_meta(graph_id: str) -> dict:
    p = graph_meta_path(graph_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"图谱不存在: {graph_id}")
    return json.loads(p.read_text(encoding="utf-8"))

def save_meta(graph_id: str, meta: dict):
    graph_meta_path(graph_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def load_kg(graph_id: str) -> dict:
    p = graph_kg_path(graph_id)
    if not p.exists():
        return {"nodes": [], "edges": []}
    return json.loads(p.read_text(encoding="utf-8"))


# ─── 后台处理任务 ──────────────────────────────────────────────

def run_pipeline_for_graph(graph_id: str, pdf_paths: list[Path]):
    """在后台线程中为指定图谱执行完整的抽取管线。"""
    import sys
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    gdir = graph_dir(graph_id)
    text_dir   = gdir / "text"
    term_dir   = gdir / "terminology"
    ent_dir    = gdir / "entities"
    rel_dir    = gdir / "relations"
    kg_out_dir = gdir / "kg"
    for d in [text_dir, term_dir, ent_dir, rel_dir, kg_out_dir]:
        d.mkdir(parents=True, exist_ok=True)

    try:
        meta = read_meta(graph_id)
        meta["status"] = "processing"
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_meta(graph_id, meta)

        # 1. 预处理：PDF → 分句 txt
        from preprocess.extract import extract_text
        from preprocess.clean import clean_text, split_sentences

        all_sentences_path = text_dir / "all_sentences.jsonl"
        import json as _json

        with open(all_sentences_path, "a", encoding="utf-8") as sent_f:
            for pdf_path in pdf_paths:
                out_txt = text_dir / (pdf_path.stem + ".txt")
                if not out_txt.exists():
                    raw = extract_text(str(pdf_path))
                    cleaned = clean_text(raw)
                    sentences = split_sentences(cleaned)
                    out_txt.write_text("\n".join(sentences), encoding="utf-8")
                else:
                    sentences = out_txt.read_text(encoding="utf-8").splitlines()

                doc_id = pdf_path.stem
                for i, s in enumerate(sentences):
                    if s.strip():
                        sent_f.write(_json.dumps({"doc_id": doc_id, "sentence_id": i, "text": s}, ensure_ascii=False) + "\n")

        # 2. 术语抽取 — extract_terms(corpus_dir, out_path)
        from terminology.term_extraction import extract_terms
        term_out = term_dir / "terms_raw.csv"
        extract_terms(text_dir, str(term_out))

        # 3. NER — predict_corpus(sentences_path, term_file, out_path)
        from candidate_extraction.ner import predict_corpus
        # 2.5 确定是否有人工金标词典
        term_final = term_dir / "terms_final.csv"
        term_clean = term_dir / "terms_clean.csv"
        term_llm   = term_dir / "terms_llm.csv"
        
        has_manual_gold = term_final.exists()
        
        if has_manual_gold:
            active_term_file = term_final
            print("[pipeline] 发现人工金标词典 terms_final.csv，将使用规则引擎进行抽取。")
        else:
            from terminology.llm_review import review_terms_with_llm
            review_terms_with_llm(term_clean, term_llm)
            active_term_file = term_llm
            print("[pipeline] 未发现人工金标词典，使用 LLM 自动审核并融合抽取新词汇。")
        
        # 3. NER — predict_corpus(sentences_path, term_file, out_path)
        from candidate_extraction.ner import predict_corpus
        ent_raw  = ent_dir / "entities_raw.jsonl"
        ent_clean = ent_dir / "entities_clean.jsonl"
        
        predict_corpus(
            sentences_path=all_sentences_path,
            term_file=active_term_file,
            out_path=ent_raw,
        )

        # 4. 关系抽取
        rel_raw   = rel_dir / "relations_raw.jsonl"
        rel_clean = rel_dir / "relations_clean.jsonl"
        
        if has_manual_gold:
            from candidate_extraction.relation import predict_relations
            predict_relations(
                entities_path=ent_clean,
                out_path=rel_raw,
                clean_path=rel_clean,
            )
        else:
            from candidate_extraction.llm_relation import predict_relations_llm
            predict_relations_llm(
                entities_path=ent_clean,
                out_path=rel_raw,
                clean_path=rel_clean,
            )

        # 5. 导出 KG — export_graph_files(entities_path, relations_path, out_dir)
        from kg.export import export_graph_files
        export_graph_files(
            entities_path=ent_clean,
            relations_path=rel_clean,
            out_dir=kg_out_dir,
        )

        # 更新状态为就绪
        meta = read_meta(graph_id)
        kg = load_kg(graph_id)
        meta["status"] = "ready"
        meta["entity_count"] = len(kg["nodes"])
        meta["relation_count"] = len(kg["edges"])
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_meta(graph_id, meta)

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        try:
            meta = read_meta(graph_id)
            meta["status"] = "error"
            meta["error"] = str(exc)
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_meta(graph_id, meta)
        except Exception:
            pass
        print(f"[pipeline] 图谱 {graph_id} 处理失败:\n{tb}")



# ─── 图谱列表与管理 API ────────────────────────────────────────

@app.get("/api/graphs")
def list_graphs():
    """返回所有图谱的元信息列表，按更新时间倒序。"""
    graphs = []
    for d in GRAPHS_DIR.iterdir():
        meta_file = d / "meta.json"
        if d.is_dir() and meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            graphs.append(meta)
    graphs.sort(key=lambda g: g.get("updated_at", ""), reverse=True)
    return graphs


@app.post("/api/graphs")
async def create_graph(
    name: str = Form(...),
    description: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """新建一个知识图谱，并可选上传初始文档。"""
    graph_id = uuid.uuid4().hex[:12]
    gdir = graph_dir(graph_id)
    raw_dir = gdir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "id": graph_id,
        "name": name,
        "description": description,
        "status": "empty",      # empty | processing | ready | error
        "entity_count": 0,
        "relation_count": 0,
        "doc_count": 0,
        "created_at": now,
        "updated_at": now,
        "error": None,
    }

    saved_pdfs: list[Path] = []
    for f in files:
        if not f.filename:
            continue
        dest = raw_dir / f.filename
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved_pdfs.append(dest)

    meta["doc_count"] = len(saved_pdfs)
    save_meta(graph_id, meta)

    if saved_pdfs:
        meta["status"] = "processing"
        save_meta(graph_id, meta)
        background_tasks.add_task(run_pipeline_for_graph, graph_id, saved_pdfs)

    return meta


@app.get("/api/graphs/{graph_id}")
def get_graph(graph_id: str):
    return read_meta(graph_id)


@app.delete("/api/graphs/{graph_id}")
def delete_graph(graph_id: str):
    gdir = graph_dir(graph_id)
    if not gdir.exists():
        raise HTTPException(status_code=404, detail="图谱不存在")
    shutil.rmtree(gdir)
    return {"deleted": graph_id}


@app.post("/api/graphs/{graph_id}/upload")
async def upload_docs(
    graph_id: str,
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """向现有图谱追加文档并触发增量处理。"""
    meta = read_meta(graph_id)
    raw_dir = graph_dir(graph_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for f in files:
        if not f.filename:
            continue
        dest = raw_dir / f.filename
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(dest)

    meta["doc_count"] = meta.get("doc_count", 0) + len(saved)
    meta["status"] = "processing"
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_meta(graph_id, meta)

    background_tasks.add_task(run_pipeline_for_graph, graph_id, saved)
    return {"queued": len(saved), "files": [p.name for p in saved]}


# ─── 图谱查询 API（复用原有逻辑，改为从图谱目录读取） ──────────

@app.get("/api/graphs/{graph_id}/stats")
def api_stats(graph_id: str):
    kg = load_kg(graph_id)
    type_dist: dict[str, int] = {}
    for node in kg["nodes"]:
        t = node.get("entity_type", "Concept")
        type_dist[t] = type_dist.get(t, 0) + 1

    rel_dist: dict[str, int] = {}
    for edge in kg["edges"]:
        r = edge.get("relation", "unknown")
        rel_dist[r] = rel_dist.get(r, 0) + 1

    doc_ids = {n["source_doc"] for n in kg["nodes"] if n.get("source_doc")}
    return {
        "entities": len(kg["nodes"]),
        "relations": len(kg["edges"]),
        "documents": len(doc_ids),
        "entity_type_distribution": type_dist,
        "relation_type_distribution": rel_dist,
        "type_colors": TYPE_COLORS,
    }


@app.get("/api/graphs/{graph_id}/search")
def api_search(graph_id: str, q: str = Query("", min_length=0)):
    kg = load_kg(graph_id)
    q = q.strip()
    if not q:
        return []
    results = [n for n in kg["nodes"] if q.lower() in n.get("name", "").lower()]
    results.sort(key=lambda n: len(n.get("name", "")))
    return results[:60]


@app.get("/api/graphs/{graph_id}/entity/{entity_id:path}")
def api_entity_detail(graph_id: str, entity_id: str):
    kg = load_kg(graph_id)
    node = next((n for n in kg["nodes"] if n["id"] == entity_id), None)
    if not node:
        raise HTTPException(status_code=404, detail=f"实体不存在: {entity_id}")

    out_edges = [e for e in kg["edges"] if e["source"] == entity_id]
    in_edges  = [e for e in kg["edges"] if e["target"] == entity_id]
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


@app.get("/api/graphs/{graph_id}/subgraph/{entity_id:path}")
def api_subgraph(graph_id: str, entity_id: str, hops: int = Query(1, ge=1, le=2)):
    kg = load_kg(graph_id)
    id_to_node = {n["id"]: n for n in kg["nodes"]}

    if entity_id not in id_to_node:
        raise HTTPException(status_code=404, detail="实体不存在")

    visited: set[str] = {entity_id}
    frontier: set[str] = {entity_id}
    for _ in range(hops):
        nxt: set[str] = set()
        for eid in frontier:
            for e in kg["edges"]:
                if e["source"] == eid and e["target"] not in visited:
                    nxt.add(e["target"])
                elif e["target"] == eid and e["source"] not in visited:
                    nxt.add(e["source"])
        visited |= nxt
        frontier = nxt
        if len(visited) > 200:
            break

    sub_nodes = [id_to_node[nid] for nid in visited if nid in id_to_node]
    sub_edges = [e for e in kg["edges"] if e["source"] in visited and e["target"] in visited]

    import math
    degrees: dict[str, int] = {}
    for e in sub_edges:
        degrees[e["source"]] = degrees.get(e["source"], 0) + 1
        degrees[e["target"]] = degrees.get(e["target"], 0) + 1

    echarts_nodes = [
        {
            "id": n["id"],
            "name": n.get("name", n["id"]),
            "value": n.get("entity_type", "Concept"),
            "category": n.get("entity_type", "Concept"),
            "symbolSize": 28 if n["id"] == entity_id else max(10, min(22, 8 + math.sqrt(degrees.get(n["id"], 0)) * 2)),
            "itemStyle": {
                "color": TYPE_COLORS.get(n.get("entity_type", "Concept"), "#374151"),
                "borderColor": "#ffffff" if n["id"] == entity_id else "transparent",
                "borderWidth": 3 if n["id"] == entity_id else 0,
            },
            "label": {"show": True},
        }
        for n in sub_nodes
    ]
    echarts_edges = [
        {
            "source": e["source"],
            "target": e["target"],
            "label": {"show": False, "formatter": e["relation"]},
            "lineStyle": {"opacity": 0.6, "width": 1},
            "_relation": e["relation"],
            "_evidence": e.get("evidence", ""),
        }
        for e in sub_edges
    ]
    return {"nodes": echarts_nodes, "edges": echarts_edges, "center": entity_id}


@app.get("/api/graphs/{graph_id}/overview")
def api_graph_overview(graph_id: str, limit: int = Query(2000, ge=50, le=5000)):
    import math
    kg = load_kg(graph_id)

    degrees: dict[str, int] = {}
    for e in kg["edges"]:
        degrees[e["source"]] = degrees.get(e["source"], 0) + 1
        degrees[e["target"]] = degrees.get(e["target"], 0) + 1

    sorted_nodes = sorted(
        kg["nodes"],
        key=lambda n: (degrees.get(n["id"], 0), n.get("entity_type", "Concept") != "Concept"),
        reverse=True,
    )
    selected = sorted_nodes[:limit]
    sel_ids = {n["id"] for n in selected}
    sel_edges = [e for e in kg["edges"] if e["source"] in sel_ids and e["target"] in sel_ids]

    echarts_nodes = []
    for n in selected:
        deg = degrees.get(n["id"], 0)
        size = max(6, min(26, 6 + math.sqrt(deg) * 1.8))
        echarts_nodes.append({
            "id": n["id"],
            "name": n.get("name", n["id"]),
            "value": n.get("entity_type", "Concept"),
            "category": n.get("entity_type", "Concept"),
            "symbolSize": size,
            "itemStyle": {"color": TYPE_COLORS.get(n.get("entity_type", "Concept"), "#374151")},
            "label": {"show": size > 12, "fontSize": 10},
            "_degree": deg,
        })

    echarts_edges = [
        {"source": e["source"], "target": e["target"], "_relation": e["relation"], "lineStyle": {"opacity": 0.15, "width": 1}}
        for e in sel_edges
    ]
    return {"nodes": echarts_nodes, "edges": echarts_edges, "type_colors": TYPE_COLORS}


# ─── 页面路由 ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页：图谱列表"""
    return templates.TemplateResponse(request=request, name="home.html")


@app.get("/graph/{graph_id}", response_class=HTMLResponse)
async def graph_view(request: Request, graph_id: str):
    """图谱详情页"""
    return templates.TemplateResponse(request=request, name="graph.html", context={"graph_id": graph_id})
