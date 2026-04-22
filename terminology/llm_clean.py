import csv
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"
TERMS_DIR = PROJECT_ROOT / "data" / "terminology"

ALLOWED_TYPES = {
    "Aircraft",
    "Structure",
    "Mechanism",
    "ControlMethod",
    "Performance",
    "Mission",
    "Parameter",
    "Document",
    "Concept",
}


def _strip_model_wrapping(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|text|markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"未找到配置文件: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = data.get("term_cleaning")
    if not isinstance(config, dict):
        raise ValueError("config.json 中缺少 term_cleaning 配置")
    for key in ["api_key", "base_url", "model", "system_prompt", "user_prompt"]:
        if not str(config.get(key, "")).strip():
            raise ValueError(f"term_cleaning 缺少必要字段: {key}")
    return config


def _load_rows(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_rows(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["term", "freq", "tfidf", "pmi", "score", "entity_type", "keep", "alias"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_alias(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["alias", "canonical", "entity_type"])
        writer.writeheader()
        writer.writerows(rows)


def clean_terms_with_llm(
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    alias_path: str | Path | None = None,
) -> dict[str, Path]:
    config = _load_config()

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("请执行：pip install openai") from exc

    input_csv = Path(input_path) if input_path else TERMS_DIR / "terms_clean.csv"
    output_csv = Path(output_path) if output_path else TERMS_DIR / "terms_clean_llm.csv"
    alias_csv = Path(alias_path) if alias_path else TERMS_DIR / "alias_llm.csv"

    rows = _load_rows(input_csv)
    top_n = min(len(rows), int(config.get("top_n", 600)))
    batch_size = int(config.get("batch_size", 80))
    temperature = float(config.get("temperature", 0))
    max_tokens = int(config.get("max_tokens", 4096))

    client_kwargs = {
        "api_key": config["api_key"],
        "base_url": config["base_url"],
    }
    if config.get("timeout"):
        client_kwargs["timeout"] = config["timeout"]
    client = OpenAI(**client_kwargs)

    kept_rows: list[dict] = []
    alias_rows: list[dict] = []

    for start in range(0, top_n, batch_size):
        batch = rows[start:start + batch_size]
        candidates = [
            {
                "term": row["term"],
                "freq": row["freq"],
                "entity_type": row["entity_type"],
                "score": row["score"],
            }
            for row in batch
        ]
        user_prompt = str(config["user_prompt"]).format(
            candidates_json=json.dumps(candidates, ensure_ascii=False)
        )
        response = client.chat.completions.create(
            model=config["model"],
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": config["system_prompt"]},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = _strip_model_wrapping(response.choices[0].message.content if response.choices else "[]")
        items = json.loads(content)
        lookup = {row["term"]: row for row in batch}

        for item in items:
            term = str(item.get("term", "")).strip()
            if term not in lookup:
                continue
            keep = str(item.get("keep", "N")).strip().upper() == "Y"
            if not keep:
                continue
            canonical = str(item.get("canonical", term)).strip() or term
            entity_type = str(item.get("entity_type", lookup[term]["entity_type"])).strip() or lookup[term]["entity_type"]
            if entity_type not in ALLOWED_TYPES:
                entity_type = lookup[term]["entity_type"]
            row = dict(lookup[term])
            row["entity_type"] = entity_type
            row["alias"] = "" if canonical == term else canonical
            row["keep"] = "Y"
            kept_rows.append(row)
            if canonical != term:
                alias_rows.append(
                    {
                        "alias": term,
                        "canonical": canonical,
                        "entity_type": entity_type,
                    }
                )

        print(f"[term_cleaning] 已完成批次 {start // batch_size + 1}")

    kept_rows.sort(key=lambda row: (-float(row["score"]), -int(row["freq"]), row["term"]))
    _write_rows(output_csv, kept_rows)
    _write_alias(alias_csv, alias_rows)

    return {
        "terms_clean_llm": output_csv,
        "alias_llm": alias_csv,
    }
