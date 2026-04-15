"""RDF/TTL 导出与 Neo4j 导入脚本占位"""

def export_ttl(entities, relations, out_path: str = "data/kg.ttl"):
    print(f"导出 TTL 到 {out_path} （未实现）")
    return out_path


def import_neo4j(ttl_path: str, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "neo4j"):
    print(f"将 {ttl_path} 导入 Neo4j（{uri}） （未实现）")
