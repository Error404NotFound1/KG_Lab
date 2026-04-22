import csv
import json
from pathlib import Path

try:
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import RDF, RDFS
except ImportError:  # pragma: no cover
    Graph = Literal = Namespace = URIRef = None
    RDF = RDFS = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ENTITIES_DIR = DATA_DIR / "entities"
RELATIONS_DIR = DATA_DIR / "relations"
KG_DIR = DATA_DIR / "kg"
EX = Namespace("http://example.org/kg/") if Namespace else None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows



def normalize_entity_name(name: str) -> str:
    return "_".join(name.strip().split())



def build_graph_data(entities_path: str | Path | None = None, relations_path: str | Path | None = None) -> tuple[list[dict], list[dict]]:
    entities_source = Path(entities_path) if entities_path else ENTITIES_DIR / "entities_clean.jsonl"
    relations_source = Path(relations_path) if relations_path else RELATIONS_DIR / "relations_clean.jsonl"
    entity_rows = _read_jsonl(entities_source)
    relation_rows = _read_jsonl(relations_source)

    nodes = {}
    for row in entity_rows:
        key = normalize_entity_name(row["entity"])
        nodes.setdefault(key, {"id": key, "name": row["entity"], "entity_type": row["entity_type"], "source_doc": row["doc_id"]})

    edges = []
    seen = set()
    for row in relation_rows:
        source = normalize_entity_name(row["head"])
        target = normalize_entity_name(row["tail"])
        key = (source, row["relation"], target, row["doc_id"], row["sentence_id"])
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "source": source,
            "relation": row["relation"],
            "target": target,
            "doc_id": row["doc_id"],
            "sentence_id": row["sentence_id"],
            "evidence": row["evidence_sentence"],
        })
    return list(nodes.values()), edges



def export_graph_files(entities_path: str | Path | None = None, relations_path: str | Path | None = None, out_dir: str | Path | None = None) -> dict[str, Path]:
    target_dir = Path(out_dir) if out_dir else KG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    nodes, edges = build_graph_data(entities_path, relations_path)

    nodes_path = target_dir / "nodes.csv"
    edges_path = target_dir / "edges.csv"
    json_path = target_dir / "kg.json"
    ttl_path = target_dir / "kg.ttl"

    with open(nodes_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "entity_type", "source_doc"])
        writer.writeheader()
        writer.writerows(nodes)

    with open(edges_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "relation", "target", "doc_id", "sentence_id", "evidence"])
        writer.writeheader()
        writer.writerows(edges)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, ensure_ascii=False, indent=2)

    export_ttl(nodes, edges, ttl_path)
    return {"nodes": nodes_path, "edges": edges_path, "json": json_path, "ttl": ttl_path}



def export_ttl(entities, relations, out_path: str | Path = KG_DIR / "kg.ttl"):
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if Graph is None:
        lines = ["@prefix ex: <http://example.org/kg/> .", ""]
        for entity in entities:
            safe_name = str(entity["name"]).replace('"', "'")
            lines.append(f"ex:{entity['id']} a ex:{entity['entity_type']} ;")
            lines.append(f"    <http://www.w3.org/2000/01/rdf-schema#label> \"{safe_name}\" .")
        for relation in relations:
            lines.append(f"ex:{relation['source']} ex:{relation['relation']} ex:{relation['target']} .")
        target.write_text("\n".join(lines), encoding="utf-8")
        return target

    graph = Graph()
    graph.bind("ex", EX)
    for entity in entities:
        node = URIRef(EX[entity["id"]])
        graph.add((node, RDF.type, URIRef(EX[entity["entity_type"]])))
        graph.add((node, RDFS.label, Literal(entity["name"])))
    for relation in relations:
        source = URIRef(EX[relation["source"]])
        target_node = URIRef(EX[relation["target"]])
        predicate = URIRef(EX[relation["relation"]])
        graph.add((source, predicate, target_node))
        graph.add((source, URIRef(EX["hasEvidence"]), Literal(relation["evidence"])))
    graph.serialize(destination=str(target), format="turtle")
    return target



def import_neo4j(ttl_path: str, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "neo4j"):
    print("Neo4j 导入建议：先使用导出的 nodes.csv 和 edges.csv，通过 LOAD CSV 或 Python 驱动导入。")
    print(f"当前参数：ttl={ttl_path}, uri={uri}, user={user}")
