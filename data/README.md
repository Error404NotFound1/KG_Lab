data 目录说明

- `raw/`：存放原始文件（PDF、OCR 输出、爬取的 HTML 等）。
- `cleaned/`：存放清洗后的文本（按文档或按句子分文件或 JSONL）。

建议：不要将大文件提交到版本库；将 `data/` 加入 `.gitignore`（已在 `code/.gitignore`）。
