知识图谱构建（模块化）项目 — 代码目录

本目录包含实现流程图中各模块的代码副本，便于作为独立工程使用。

快速开始

```bash
cd code
pip install -r requirements.txt
python scripts/run_pipeline.py --stage preprocess
```

OCR 默认通过根目录的 [config.json](config.json) 调用 OpenAI 兼容视觉模型。你只需要把里面的 `api_key`、`base_url` 和 `model` 改成自己的配置即可。

主要子目录与职责

- `data/`：原始与清洗数据
- `preprocess/`：文本抽取、清洗、分句、分词
- `terminology/`：术语提取与词表管理
- `candidate_extraction/`：规则与模型候选抽取
- `annotation/`：与 doccano/label-studio 的交换脚本与质检
- `kg/`：实体融合、RDF/TTL 导出、Neo4j 导入
- `evaluation/`：评估指标计算与报告生成
- `scripts/`：运行与训练脚本
- `docker/`：服务编排（Neo4j、doccano）

说明：这是对仓库根目录实现的代码复制，便于直接进入 `code/` 运行和开发。