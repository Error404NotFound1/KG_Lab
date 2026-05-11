import csv
import json
import os
from pathlib import Path

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

def review_terms_with_llm(raw_csv_path: Path, final_csv_path: Path):
    if not raw_csv_path.exists():
        return
        
    MAX_TERMS_TO_REVIEW = 300
    
    # Read existing terms if any
    existing_terms = {}
    if final_csv_path.exists():
        with open(final_csv_path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                existing_terms[row["term"]] = row
                
    # Read new candidates
    new_candidates = []
    all_raw_rows = []
    with open(raw_csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            all_raw_rows.append(row)
            term = row.get("term", "")
            if term not in existing_terms and len(new_candidates) < MAX_TERMS_TO_REVIEW:
                new_candidates.append(row)
                
    if not new_candidates:
        print("[llm_review] 没有发现需要审核的新候选词汇，跳过大模型审核。")
        return

    # Prepare prompt for new candidates
    prompt = """你是一个通用工程、机械与制造领域的知识图谱专家（包含航空航天、汽车维修、液压系统等）。
请审核以下自动抽取的术语候选列表。
你需要返回一个 JSON 数组，每个元素包含：
- term: 原始术语
- keep: "Y" 表示保留（只要是机械、工程、物理参数、系统组件等专业术语均可），"N" 表示因为是日常废话、无意义词或停用词而删除
- entity_type: 根据术语的含义，修正其对应的实体类型（可选值：Aircraft, Vehicle, Structure, Mechanism, Performance, Mission, Parameter, ControlMethod, Concept, Tool）
- alias: 术语的别名或同义词（如果有的话，没有则留空）

输入术语列表（JSON格式）：
"""
    input_data = [{"term": r["term"], "entity_type": r["entity_type"]} for r in new_candidates]
    prompt += json.dumps(input_data, ensure_ascii=False)
    
    print(f"[llm_review] 发现 {len(new_candidates)} 个新术语，开始使用大模型审核...")
    
    client, model = _get_llm_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个严格的航空航天术语审核专家。只返回合法的 JSON 数组，不要任何Markdown包裹，不要其他文字。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        reviewed_data = json.loads(content)
        
        review_dict = {item["term"]: item for item in reviewed_data if "term" in item}
        
        # Merge results into existing_terms
        for term, rev in review_dict.items():
            # Find original row
            orig_row = next((r for r in new_candidates if r["term"] == term), None)
            if orig_row:
                orig_row["keep"] = rev.get("keep", "N")
                orig_row["entity_type"] = rev.get("entity_type", orig_row["entity_type"])
                orig_row["alias"] = rev.get("alias", orig_row["alias"])
                existing_terms[term] = orig_row
                
        # For new candidates that LLM didn't return or we didn't send
        for row in all_raw_rows:
            term = row.get("term", "")
            if term not in existing_terms:
                row["keep"] = "N"
                existing_terms[term] = row
                
        # Write merged results
        kept_count = 0
        with open(final_csv_path, "w", encoding="utf-8-sig", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            for term, row in existing_terms.items():
                if row.get("keep") == "Y":
                    kept_count += 1
                writer.writerow(row)
                
        print(f"[llm_review] 大模型审核融合完成，当前词典共保留了 {kept_count} 个核心实体（已生成/更新 {final_csv_path.name}）")
        
    except Exception as e:
        print(f"[llm_review] 大模型审核失败: {e}，将保持原有词典不变")
        import traceback
        traceback.print_exc()
