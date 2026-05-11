import json
import concurrent.futures
from pathlib import Path
from candidate_extraction.relation import load_entities, group_by_sentence, _type_ok, MIN_SENTENCE_LEN, MAX_ENTITY_DISTANCE

def _get_llm_client():
    from preprocess.extract import _load_ocr_config
    config = _load_ocr_config()
    from openai import OpenAI
    client_kwargs = {
        "api_key": config["api_key"],
        "base_url": config["base_url"],
    }
    timeout = config.get("timeout")
    if timeout:
        client_kwargs["timeout"] = timeout
    return OpenAI(**client_kwargs), config["model"]

def predict_relations_llm(
    entities_path: str | Path,
    out_path: str | Path,
    clean_path: str | Path,
) -> tuple[Path, Path]:
    raw_target = Path(out_path)
    clean_target = Path(clean_path)
    
    entities = load_entities(entities_path)
    grouped = group_by_sentence(entities)
    
    # Prepare batches of sentences that have >= 2 entities
    batches = []
    current_batch = []
    BATCH_SIZE = 200
    
    sentence_metadata = {}
    
    for (doc_id, sent_id), sent_entities in grouped.items():
        if len(sent_entities) < 2:
            continue
            
        sentence = sent_entities[0]["text"]
        if len(sentence) < MIN_SENTENCE_LEN:
            continue
            
        # Check if there are any entities close enough
        has_close_pair = False
        for i in range(len(sent_entities)):
            for j in range(i + 1, len(sent_entities)):
                if abs(sent_entities[j]["start"] - sent_entities[i]["end"]) <= MAX_ENTITY_DISTANCE:
                    has_close_pair = True
                    break
            if has_close_pair:
                break
                
        if not has_close_pair:
            continue
            
        unique_entities = []
        seen = set()
        for e in sent_entities:
            if e["entity"] not in seen:
                seen.add(e["entity"])
                unique_entities.append({"name": e["entity"], "type": e["entity_type"]})
                
        if len(unique_entities) < 2:
            continue
            
        item_id = f"{doc_id}_{sent_id}"
        sentence_metadata[item_id] = {
            "doc_id": doc_id,
            "title": sent_entities[0].get("title", ""),
            "file_name": sent_entities[0].get("file_name", ""),
            "sentence_id": sent_id,
            "sentence": sentence,
            "entities": {e["name"]: e["type"] for e in unique_entities}
        }
        
        current_batch.append({
            "id": item_id,
            "sentence": sentence,
            "entities": unique_entities
        })
        
        if len(current_batch) >= BATCH_SIZE:
            batches.append(current_batch)
            current_batch = []
            
    if current_batch:
        batches.append(current_batch)
        
    print(f"[llm_relation] 筛选出 {len(sentence_metadata)} 个包含多个实体的句子，分 {len(batches)} 批进行大模型关系抽取...")
    
    client, model = _get_llm_client()
    raw_count = 0
    clean_count = 0
    
    seen_raw = set()
    seen_clean = set()
    
    def process_batch(batch_idx, batch):
        print(f"[llm_relation] 提交批次: {batch_idx + 1}/{len(batches)}")
        prompt = """你是一个专业的机械、工程与制造领域（如汽车、航空、液压等）知识图谱构建专家。请从以下句子中提取实体之间的关系。
允许的关系类型（relation）有：
- is_a (是一种/属于)
- has_component (包含/由...组成)
- uses_method (采用/使用)
- affects (影响/决定/改变)
- applies_to (适用于)
- supports_mission (支持任务)
- has_mechanism (具有机制)
- has_parameter (拥有参数)

输入是一个 JSON 数组，每个对象包含 id, sentence 和 entities（候选实体列表）。
对于每个对象，请判断 sentence 中实体之间是否存在上述关系。
如果有，请返回一个 JSON 数组。返回格式如下：
[
  {
    "id": "1",
    "relations": [
      {"head": "实体1", "tail": "实体2", "relation": "has_component"}
    ]
  }
]
注意：如果某个句子没有明显关系，其 relations 数组留空或省略该 id。不要输出任何解释或 Markdown 格式。
输入：
"""
        prompt += json.dumps(batch, ensure_ascii=False)
        extracted_rels = []
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个严格的信息抽取工具，只输出合法的 JSON 数组。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:-1])
            
            results = json.loads(content)
            for res in results:
                item_id = res.get("id")
                if not item_id or item_id not in sentence_metadata:
                    continue
                    
                meta = sentence_metadata[item_id]
                doc_id = meta["doc_id"]
                sent_id = meta["sentence_id"]
                sentence = meta["sentence"]
                entity_dict = meta["entities"]
                
                for rel in res.get("relations", []):
                    head = rel.get("head")
                    tail = rel.get("tail")
                    relation = rel.get("relation")
                    
                    if not head or not tail or not relation or head == tail:
                        continue
                    if head not in entity_dict or tail not in entity_dict:
                        continue
                        
                    head_type = entity_dict[head]
                    tail_type = entity_dict[tail]
                    
                    payload = {
                        "doc_id": doc_id,
                        "title": meta["title"],
                        "file_name": meta["file_name"],
                        "sentence_id": sent_id,
                        "head": head,
                        "head_type": head_type,
                        "relation": relation,
                        "tail": tail,
                        "tail_type": tail_type,
                        "evidence_sentence": sentence,
                    }
                    extracted_rels.append(payload)
        except Exception as e:
            print(f"[llm_relation] 批次 {batch_idx + 1} 抽取失败: {e}")
            
        print(f"[llm_relation] 批次 {batch_idx + 1}/{len(batches)} 完成，抽取到 {len(extracted_rels)} 个关系")
        return extracted_rels

    with open(raw_target, "w", encoding="utf-8") as f_raw, open(clean_target, "w", encoding="utf-8") as f_clean:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_batch, i, batch) for i, batch in enumerate(batches)]
            for future in concurrent.futures.as_completed(futures):
                results = future.result()
                for payload in results:
                    doc_id = payload["doc_id"]
                    sent_id = payload["sentence_id"]
                    head = payload["head"]
                    head_type = payload["head_type"]
                    relation = payload["relation"]
                    tail = payload["tail"]
                    tail_type = payload["tail_type"]
                    
                    raw_key = (doc_id, sent_id, head, relation, tail)
                    if raw_key in seen_raw:
                        continue
                    seen_raw.add(raw_key)
                    
                    f_raw.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    raw_count += 1
                    
                    if not _type_ok(relation, head_type, tail_type):
                        continue
                        
                    clean_key = (doc_id, sent_id, head, relation, tail)
                    if clean_key in seen_clean:
                        continue
                    seen_clean.add(clean_key)
                    
                    f_clean.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    clean_count += 1
                
    print(f"[llm_relation] LLM 抽取完成。raw 三元组: {raw_count} 条，clean 三元组: {clean_count} 条")
    return raw_target, clean_target
