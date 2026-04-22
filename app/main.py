from pathlib import Path
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
KG_JSON = DATA_DIR / "kg" / "kg.json"
TEMPLATES_DIR = PROJECT_ROOT / "app" / "templates"
STATIC_DIR = PROJECT_ROOT / "app" / "static"

app = FastAPI(title="变构飞行器知识图谱应用")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_kg() -> dict:
    if not KG_JSON.exists():
        return {"nodes": [], "edges": []}
    return json.loads(KG_JSON.read_text(encoding="utf-8"))


@app.get("/api/stats")
def stats():
    kg = load_kg()
    node_types = {}
    for node in kg["nodes"]:
        node_types[node["entity_type"]] = node_types.get(node["entity_type"], 0) + 1
    return {
        "entities": len(kg["nodes"]),
        "relations": len(kg["edges"]),
        "entity_type_distribution": node_types,
    }


@app.get("/api/search")
def search(q: str):
    kg = load_kg()
    q = q.strip()
    return [node for node in kg["nodes"] if q and q in node["name"]][:50]


@app.get("/api/entity/{entity_id}")
def entity_detail(entity_id: str):
    kg = load_kg()
    node = next((item for item in kg["nodes"] if item["id"] == entity_id), None)
    if not node:
        raise HTTPException(status_code=404, detail="实体不存在")
    related = [edge for edge in kg["edges"] if edge["source"] == entity_id or edge["target"] == entity_id]
    return {"entity": node, "relations": related}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "stats": stats()})
