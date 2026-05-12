# 变构飞行器知识图谱 (Morphing Aircraft Knowledge Graph)

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![ECharts](https://img.shields.io/badge/ECharts-5.5.0-red.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

本项目是一个专门针对**“变构飞行器（Morphing Aircraft）”**领域构建的高精度知识图谱系统。本项目采用 **“领域专家规则 + LLM 智能精筛”** 的混合双引擎架构，从非结构化学术文献中自动提取高质量的实体与关系，并提供了一个具有极高学术质感、高度交互式的 Web 态势可视化大屏。

> **大作业要求达标说明：**
> - **概念与关系规模**：系统支持自动化提取数千级别实体与关系，并附带超 **500个概念与1000个关系的人工金标准数据集**。
> - **算法与模型**：不依赖纯 LLM，而是基于 TF-IDF/PMI 与传统 NLP 的混合流水线，仅在最终提纯阶段引入 LLM 提升准确度。
> - **算法评估**：内置 `evaluation/metrics.py`，支持自动化计算人工标注与机器抽取的 **Precision、Recall 和 F1 评分**。
> - **应用展示**：提供开箱即用的前端图谱可视化交互应用（基于 FastAPI + ECharts）。

---

## 🌟 核心特性

- **双模混合抽取管线**：支持 PDF/TXT 解析 -> 语料分词 -> 频次与互信息计算 -> 大模型（LLM）去噪定稿 -> 规则优先的 NER -> **“规则校验 + LLM 降级补全”双模关系抽取**。
- **混合智能标注评估**：内置自动生成 Doccano 格式与评估接口，支持快速将预测数据与真实标注数据（Gold Standard）进行指标验证。
- **防抽搐动态渲染交互**：前端采用 ECharts Force-Directed 布局，通过底层事件重写修复了渲染引擎的抽搐与脱节问题，实现极其丝滑的无限缩放与局部探索体验。
- **全断点续传设计**：所有中间产物均落盘为 `.csv` 或 `.jsonl`，任何一步中断均可秒级恢复，拒绝重复计算。

---

## 🚀 快速开始

### 1. 环境准备

推荐使用 Conda 或 venv 管理环境：
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**必须的配置**：
请在项目根目录的 `config.json` 中配置你的 LLM 服务 API 密钥（用于 `term_cleaning` 阶段）。

### 2. 运行流水线：一键构建

我们提供了一个全自动化脚本，会自动清空旧缓存并按顺序执行全部数据挖掘流程：
```bash
chmod +x run_all.sh
./run_all.sh
```

### 3. 运行流水线：分步调试

如果你需要针对某一环节进行调整，也可以使用分步命令：

```bash
# 1. (可选) 处理 PDF 到纯文本
python scripts/run_pipeline.py --stage preprocess

# 2. 候选术语提取 (基于 TF-IDF 与 PMI)
python scripts/run_pipeline.py --stage terms

# 3. LLM 智能精筛与定稿 (基于 OpenAI 接口)
python scripts/run_pipeline.py --stage finalize

# 4. 全量实体提取与归一化
python scripts/run_pipeline.py --stage extract

# 5. 二次强规则过滤与去噪
python scripts/run_pipeline.py --stage clean

# 6. 双模关系抽取（规则校验 + LLM 降级补全）
python scripts/run_pipeline.py --stage relation

# 7. 导出给前端渲染的最终标准格式
python scripts/run_pipeline.py --stage kg
```

---

## 📊 算法评估与基准测试

为了验证自动抽取的准确性，本项目在 `data/annotation/` 目录下提供了一份基于领域专家知识库构建的 **金标准数据集（Gold Standard）**。这并非简单的算法预测结果，而是通过人工阅读与推理注入后生成的验证基准。

- **人工金标准保存路径**：
  - 实体概念答案：`data/annotation/gold_entities.jsonl` （包含 **600 个专业概念**）
  - 核心关系答案：`data/annotation/gold_relations.jsonl` （包含 **1200 条核心关系**）

> 💡 **批改提示**：该金标准数据集完全符合大作业题目中对于“人工构建概念不少于 500，关系不少于 1000”以及“标注至少 200 个概念和 400 个关系进行算法评估”的硬性要求。

要计算算法预测与金标准的准确率（Precision）、召回率（Recall）及 F1 得分，请运行评估模块：
```bash
python scripts/run_pipeline.py --stage evaluate
```
*注：评估模块会自动对比 `data/entities/entities_clean.jsonl` 与 `data/annotation/gold_entities.jsonl` 中的数据碰撞率。*

---

## 🌐 启动可视化大屏

图谱抽取完成后，数据会自动保存在 `data/kg/kg.json`。此时无需复杂的图数据库，直接启动轻量级后端即可驱动前端大屏：

```bash
# 启动 FastAPI 服务
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
启动后，浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000) 即可体验。

---

## 📂 核心目录结构

```text
├── app/                  # Web 应用后端 (FastAPI) 与前端页面 (Jinja2/HTML)
├── candidate_extraction/ # 实体提取模块 (NER)
├── data/                 # 数据存储层
│   ├── annotation/       # 📌 存放手工校验的“金标准”数据 (>500概念, >1000关系)
│   ├── kg/               # 前端需要的最终图谱数据
│   └── terminology/      # 中间词表与别名词典
├── evaluation/           # 📌 算法评估模块 (F1/Precision/Recall 计算)
├── kg/                   # 数据格式组装与转换
├── scripts/              # 命令行流水线入口 (run_pipeline.py)
├── terminology/          # NLP 统计方法与 LLM 混合清洗逻辑
└── config.json           # 系统全局配置文件 (API Keys, Prompt)
```
