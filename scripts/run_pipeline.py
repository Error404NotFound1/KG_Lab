"""项目流水线入口：支持预处理、术语抽取、实体关系抽取、标注、图谱导出与评估。"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGES = ["preprocess", "terms", "finalize", "extract", "clean", "relation", "kg", "annotate", "evaluate"]
# 说明：
#   preprocess → PDF 抽取文本（慢，只需跑一次）
#   terms      → 术语候选抽取（慢，只需跑一次）
#   finalize   → 术语表定稿（快，改规则后随时可重跑）
#   extract    → 全量 NER（慢，只在语料变化时重跑）
#   clean      → 仅清洗已有 entities_raw.jsonl（快，改过滤规则后重跑）
#   relation   → 关系抽取（依赖 entities_clean.jsonl，改触发词规则后重跑）
#   kg         → 图谱导出（快）
#   annotate   → 生成标注/评估文件
#   evaluate   → 评估


def run_preprocess(args):
    print("运行预处理")
    from preprocess.extract import extract_text, preview_ocr_backend
    from preprocess.clean import clean_text, split_sentences

    print(f"[识别] 运行前探测: {preview_ocr_backend()}（仅在文本层失败时才调用）")
    if args.input:
        input_files = [Path(args.input)]
    else:
        raw_dir = ROOT.parent / "知识图谱构建数据集"
        if not raw_dir.exists():
            print(f"默认输入目录 {raw_dir} 不存在，请手动指定 --input")
            return
        input_files = list(raw_dir.rglob("*.pdf"))
        if not input_files:
            print(f"在 {raw_dir} 下没有找到任何 PDF 文件")
            return

    for input_pdf in input_files:
        if not input_pdf.exists():
            print(f"输入文件不存在: {input_pdf}")
            continue

        if args.output:
            output_path = Path(args.output)
            if output_path.is_dir():
                output_path = output_path / input_pdf.with_suffix('.txt').name
            elif len(input_files) > 1:
                output_path = output_path.parent / input_pdf.with_suffix('.txt').name
        else:
            output_path = ROOT / "data" / "text" / input_pdf.with_suffix('.txt').name

        if output_path.exists() and not args.force:
            print(f"跳过已提取文档: {output_path}")
            continue

        print(f"正在从 {input_pdf} 抽取文本...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output_path = output_path.with_name(output_path.name + ".tmp")
        try:
            raw_text = extract_text(str(input_pdf))
            cleaned_text = clean_text(raw_text)
            sentences = split_sentences(cleaned_text)
            with open(temp_output_path, "w", encoding="utf-8") as f:
                for s in sentences:
                    f.write(s + "\n")
            temp_output_path.replace(output_path)
        except Exception as exc:
            if temp_output_path.exists():
                temp_output_path.unlink()
            print(f"[{input_pdf.name}] 预处理失败，未保存输出: {exc}")
            raise
        print(f"[{input_pdf.name}] 预处理完成，已保存至 {output_path}")


def run_terms(args):
    from terminology.term_extraction import extract_terms

    outputs = extract_terms(args.input or (ROOT / "data" / "text"), args.output)
    print("术语抽取完成：")
    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))

def run_finalize(args):
    from terminology.llm_clean import clean_terms_with_llm
    from terminology.finalize_terms import finalize_terms

    print("开始调用 LLM 进行全量智能清洗（可能需要几分钟，请耐心等待）...")
    clean_terms_with_llm()
    outputs = finalize_terms()
    print("术语表定稿完成：")
    for key, path in outputs.items():
        print(f"  {key}: {path}")


def run_extract(args):
    """全量 NER：对所有句子重新跑实体识别。耗时长，只在语料变化时使用。"""
    from candidate_extraction.ner import predict_corpus

    raw_ent, clean_ent = predict_corpus()
    print(f"实体抽取完成: raw={raw_ent}, clean={clean_ent}")


def run_clean(args):
    """只对已有 entities_raw.jsonl 做清洗，生成新的 entities_clean.jsonl。
    用于：改了过滤规则 / terms_final.csv 更新后，不需要重跑全量 NER 时。"""
    from candidate_extraction.ner import clean_entities, _load_type_map
    from pathlib import Path

    ROOT_DATA = ROOT / "data"
    raw_path = ROOT_DATA / "entities" / "entities_raw.jsonl"
    clean_path = ROOT_DATA / "entities" / "entities_clean.jsonl"

    if not raw_path.exists():
        print(f"entities_raw.jsonl 不存在: {raw_path}，请先运行 --stage extract")
        return

    type_map = _load_type_map()
    count = clean_entities(raw_path, clean_path, type_map)
    print(f"实体清洗完成: {count} 条写入 {clean_path}")


def run_relation(args):
    """只重跑关系抽取（依赖已有的 entities_clean.jsonl）。
    用于：改了触发词规则 / 类型约束后，快速验证效果。"""
    from candidate_extraction.relation import predict_relations
    from pathlib import Path

    clean_ent = ROOT / "data" / "entities" / "entities_clean.jsonl"
    if not clean_ent.exists():
        print(f"entities_clean.jsonl 不存在: {clean_ent}，请先运行 --stage clean")
        return

    raw_rel, clean_rel = predict_relations(entities_path=clean_ent)
    print(f"关系抽取完成: raw={raw_rel}，clean={clean_rel}")


def run_annotate(args):
    from annotation.interop import convert_entities_for_eval, convert_relations_for_eval, export_to_doccano

    doccano_path = export_to_doccano()
    ent_path = convert_entities_for_eval()
    rel_path = convert_relations_for_eval()
    print(f"doccano 导入文件: {doccano_path}")
    print(f"实体评估文件: {ent_path}")
    print(f"关系评估文件: {rel_path}")


def run_kg(args):
    from kg.export import export_graph_files

    outputs = export_graph_files()
    print("KG 导出完成：")
    print(json.dumps({key: str(value) for key, value in outputs.items()}, ensure_ascii=False, indent=2))


def run_evaluate(args):
    print("评估阶段已就绪：请将人工标注金标准放入 data/annotations/ 后调用 evaluation.metrics 进行对比。")


STAGE_FUNCS = {
    "preprocess": run_preprocess,
    "terms": run_terms,
    "finalize": run_finalize,
    "extract": run_extract,
    "clean": run_clean,
    "relation": run_relation,
    "annotate": run_annotate,
    "kg": run_kg,
    "evaluate": run_evaluate,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=STAGES, required=True, help="要运行的阶段（常规开发只使用 terms/extract/annotate/kg/evaluate，避免重复处理 PDF）")
    parser.add_argument("--input", type=str, help="指定输入路径")
    parser.add_argument("--output", type=str, help="指定输出路径")
    parser.add_argument("--force", action="store_true", help="强制重新生成结果")
    args = parser.parse_args()
    STAGE_FUNCS[args.stage](args)


if __name__ == "__main__":
    main()
