"""示例流水线入口：支持分阶段运行（简化）"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGES = ["preprocess", "terms", "extract", "annotate", "kg", "evaluate"]


def run_preprocess(args):
    print("运行预处理")
    from preprocess.extract import extract_text, preview_ocr_backend
    from preprocess.clean import clean_text, split_sentences

    print(f"[识别] 运行前探测: {preview_ocr_backend()}（仅在文本层失败时才调用）")
    
    # 若无指定输入，则默认递归遍历上一级目录的 "知识图谱构建数据集" 下的所有 PDF
    if args.input:
        input_files = [Path(args.input)]
    else:
        raw_dir = ROOT.parent / "知识图谱构建数据集"
        if not raw_dir.exists():
            print(f"默认输入目录 {raw_dir} 不存在，请手动指定 --input")
            return
        # 使用 rglob 递归查找含有子文件夹的 PDF（如"变构飞行器"、"维修类"等）
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
    print("运行术语提取（示例）")


def run_extract(args):
    print("运行候选抽取（示例）")


def run_annotate(args):
    print("运行标注导入/导出（示例）")


def run_kg(args):
    print("运行 KG 构建/导出（示例）")


def run_evaluate(args):
    print("运行评估（示例）")


STAGE_FUNCS = {
    "preprocess": run_preprocess,
    "terms": run_terms,
    "extract": run_extract,
    "annotate": run_annotate,
    "kg": run_kg,
    "evaluate": run_evaluate,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=STAGES, required=True, help="要运行的阶段")
    p.add_argument("--input", type=str, help="指定单个输入文件路径（可选，默认处理 data/raw 下的全部PDF）")
    p.add_argument("--output", type=str, help="指定单个输出文件路径（可选，默认输出到 data/text）")
    p.add_argument("--force", action="store_true", help="强制重新抽取已存在的输出文件")
    args = p.parse_args()
    STAGE_FUNCS[args.stage](args)


if __name__ == "__main__":
    main()
