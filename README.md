<div align="center">
  <img src="https://img.icons8.com/color/120/000000/network.png" alt="KG Logo"/>
  <h1>🌌 KG_Lab: 变构飞行器领域知识图谱系统</h1>
  <p>基于领域文本自动化抽取的图谱构建与炫酷可视化大屏</p>
  
  <p>
    <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.100+-00a393.svg" alt="FastAPI">
    <img src="https://img.shields.io/badge/Neo4j-5.0+-4581c3.svg" alt="Neo4j">
    <img src="https://img.shields.io/badge/ECharts-5.5-E43961.svg" alt="ECharts">
    <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
  </p>
</div>

## 📖 项目简介

**KG_Lab** 是一个完整的知识图谱闭环系统。我们以“变构飞行器”相关文献为数据源，实现了从 PDF 文本提取、术语挖掘、实体关系抽取、图数据库存储，到前端炫酷交互大屏的全链路落地。本项目旨在为垂直领域的知识图谱自动化构建与展示提供可参考的工程化范例。

**项目特色：**
- 🚀 **全链路自动化提取**：内建 PDF 解析、TF-IDF/PMI 术语抽取、基于大模型与强规则的去噪提纯引擎。
- 📊 **高质量数据约束**：采用四重维度约束（触发词黑名单、首尾距离、实体类型映射）有效过滤 90% 的无效关系噪声。
- 🔮 **炫酷前端交互**：星空粒子特效、暗黑科技风玻璃拟态卡片、力导向 ECharts 动态双击追溯子图。
- 🐳 **开箱即用架构**：前端不仅支持对接 Neo4j 图数据库，还支持完全脱库的“纯内存极速运行模式”，免去配置烦恼，随时演示。

---

## 🛠️ 技术栈架构

| 模块 | 技术选型 | 说明 |
| --- | --- | --- |
| **文本预处理** | `PyMuPDF`, `pdfminer.six`, `OpenAI` | 支持 PDF 文本层优先提取及视觉模型 OCR 兜底 |
| **术语与清洗** | `jieba`, `scikit-learn`, `LLM` | N-gram 抽取、频次过滤、大模型上下文纠错对齐 |
| **规则提取引擎** | `Python Regex` | 多约束抽取，控制词距、类型强制映射 |
| **图数据库** | `Neo4j 5`, `Docker`, `neo4j-driver` | Bolt 协议交互，`MERGE` 语句幂等导入 |
| **Web 后端** | `FastAPI`, `Uvicorn` | 异步高性能接口，提供搜索、节点拓展、子图构建 |
| **可视化前端** | `ECharts 5`, `Particles.js`, `Vanilla JS` | 零前端框架负担，原生实现暗黑玻璃拟态大屏展示 |

---

## 📂 项目目录说明

```text
KG_Lab/
├── data/
│   ├── text/                  # 解析后的纯文本语料
│   ├── entities/              # 抽取的实体集 (含 raw 与 clean 版本)
│   ├── relations/             # 抽取的三元组关系集 (含去噪 clean 版)
│   └── kg/                    # 图谱最终数据 (kg.json, nodes.csv, edges.csv)
├── preprocess/                # PDF 文本抽取、清洗、分句脚本
├── terminology/               # 领域术语发现、LLM 清洗与定稿策略
├── candidate_extraction/      # 基于规则与约束的实体识别与关系抽取
├── kg/                        # Neo4j 数据库导入导出脚本
├── docker/                    # Neo4j 服务的 docker-compose 部署文件
├── app/                       # FastAPI Web 应用
│   ├── main.py                # 后台路由与核心接口
│   ├── templates/             # HTML 前端页面
│   └── static/                # 静态资源 (CSS, JS)
├── scripts/                   # 一键化流水线运行脚本 (run_pipeline.py)
├── requirements.txt           # Python 依赖项
└── .gitignore                 # Git 忽略配置
```

---

## 🚀 快速开始

### 1. 环境准备与依赖安装

建议使用 `conda` 创建隔离环境（推荐 Python 3.10+）：

```bash
conda create -n KG python=3.10
conda activate KG
pip install -r requirements.txt
```

*(可选) 如需重新解析扫描版 PDF，需在 `config.json` 中配置大模型 API 密钥。*

### 2. 运行完整的数据提炼管线

项目数据流是解耦的，你可以通过流水线脚本一键化生成高质量图谱数据：

```bash
python scripts/run_pipeline.py --stage preprocess # (可选) 重新提取 PDF 文本
python scripts/run_pipeline.py --stage terms      # 统计与提取候选术语
python scripts/run_pipeline.py --stage finalize   # 结合 LLM 进行术语清洗与词表定稿
python scripts/run_pipeline.py --stage extract    # 粗颗粒度实体抽取
python scripts/run_pipeline.py --stage clean      # 实体强规则清洗去噪
python scripts/run_pipeline.py --stage relation   # 类型约束下的精确关系抽取
python scripts/run_pipeline.py --stage kg         # 导出为知识图谱标准文件
```

### 3. 启动炫酷 Web 可视化大屏

经过管线生成的图谱数据（`data/kg/kg.json`）即可直接驱动 Web 页面，**无需**启动笨重的图数据库！

```bash
# 启动 FastAPI 服务
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
启动后，浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000) 即可体验交互系统！

*(注意：若在 Mac 等系统遇到 HTTP 502 错误，请确保访问的是 `127.0.0.1` 而不是 `0.0.0.0`)*

### 4. (可选) 部署接入 Neo4j 图数据库

如果需要深入原生图分析，本项目也自带了一键 Neo4j 接入方案：

```bash
# 启动 Docker Neo4j 容器
cd docker
docker compose up -d

# 自动连接 Neo4j 导入海量节点与关系
cd ..
python -c "from kg.export import import_neo4j; import_neo4j()"
```

---

## 📊 图谱当前规模指标 (v1.0)

经过严格的黑名单过滤、约束判定后的图谱质量指标：

- **概念节点总量**：1200+
- **有效关系边数**：5300+
- **核心实体分类**：`Aircraft` (飞行器), `Structure` (结构), `Mechanism` (机构), `ControlMethod` (控制方法), `Performance` (性能参数) 等。

---

## 🤝 协作与贡献

目前项目核心工程已完工，正处于最终的人工标注 (T4 阶段) 和质量评估。
相关人员职责：
- **开发组长**：图谱工程架构、管线闭环搭建、前端应用开发
- **协作组员**：负责抽取规则调优、实体人工纠错、评估算法输出

> 开发状态详细追踪请参考 [`项目待办状态说明.md`](项目待办状态说明.md) 与 [`techs.md`](techs.md)。
