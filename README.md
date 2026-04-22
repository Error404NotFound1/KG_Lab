# KG_Lab：变构飞行器领域知识图谱构建与应用系统

本项目面向课程大作业，围绕**变构飞行器领域文本**构建一个完整的知识图谱系统，并实现一个可演示的**知识图谱应用程序**。

项目目标不是单独完成某个抽取模块，而是形成一个完整闭环：

- 文献文本获取与清洗
- 领域术语抽取
- 实体识别与关系抽取
- 知识图谱构建与存储
- 人工标注与算法评估
- 应用程序展示与查询

该项目按照 **2 人组课程作业**要求设计，最终将输出：

- 不少于 500 个概念节点
- 不少于 1000 条关系
- 不少于 200 个概念标注样本
- 不少于 400 条关系标注样本
- 一个可运行的知识图谱应用程序
- 完整文档、源代码与演示视频

---

## 1. 项目定位

推荐项目题目：

**变构飞行器领域知识图谱构建与应用系统设计**

或：

**基于领域文本抽取与规则融合的变构飞行器知识图谱构建及应用实现**

---

## 2. 当前项目进度

### 已完成

- PDF 文本提取与清洗分句
- 术语清洗与 LLM 自动化定稿
- 实体识别（去噪清洗）
- 关系抽取（类型约束、位置约束）
- 图谱导出（节点 1200+，关系 5300+）
- Neo4j 数据库接入（Docker-Compose + Python 导入）
- 炫酷暗黑科技风图谱 Web 应用开发（FastAPI + ECharts）

### 待完成

- 构建人工标注集并进行算法评估 (P/R/F1)
- 演示视频录制

---

## 3. 项目整体流程

项目整体流程如下：

1. 定义研究范围与本体
2. 整理并清洗领域语料
3. 提取领域术语并构建词表
4. 基于规则与词典进行实体识别
5. 基于模式与触发词进行关系抽取
6. 构建三元组并导入图数据库
7. 构建人工标注集并进行评估
8. 开发知识图谱应用程序
9. 形成文档、代码和演示视频

详细说明见：

- `开发指南.md`
- `techs.md`
- `流程图.puml`

---

## 4. 推荐本体范围

### 实体类型

- `Aircraft`
- `Structure`
- `Mechanism`
- `ControlMethod`
- `Performance`
- `Mission`
- `Parameter`
- `Document`

### 关系类型

- `is_a`
- `part_of`
- `has_component`
- `uses_method`
- `has_mechanism`
- `affects`
- `applies_to`
- `has_parameter`
- `supports_mission`
- `documented_in`

---

## 5. 目录结构

```text
KG_Lab/
├── data/
│   └── text/                   # 已提取的领域文本
├── preprocess/                # 文本抽取、清洗、分句
├── terminology/               # 术语抽取与词表构建
├── candidate_extraction/      # 实体与关系候选抽取
├── annotation/                # 标注数据导入导出与互操作
├── kg/                        # 图谱构建、导出、图数据库接入
├── evaluation/                # 评估脚本
├── scripts/                   # 流水线运行脚本
├── 开发指南.md                # 项目执行方案与作业对齐说明
├── techs.md                   # 技术选型与分工说明
├── 流程图.puml                # 项目流程图
├── config.json                # OCR 配置
├── requirements.txt           # Python 依赖
└── README.md                  # 项目说明
```

---

## 6. 快速开始

### 6.1 安装依赖

```bash
pip install -r requirements.txt
```

### 6.2 配置 OCR

项目中的 PDF 预处理支持文本层抽取优先、视觉模型 OCR 兜底。

在 `config.json` 中配置：

- `api_key`
- `base_url`
- `model`

### 6.3 运行预处理

```bash
python scripts/run_pipeline.py --stage preprocess
```

### 6.4 运行图谱抽取全流程

依次运行流水线生成干净的图谱数据：
```bash
python scripts/run_pipeline.py --stage terms     # 抽取初步术语
python scripts/run_pipeline.py --stage finalize  # LLM辅助清洗并定稿
python scripts/run_pipeline.py --stage extract   # 提取实体
python scripts/run_pipeline.py --stage clean     # 清洗实体
python scripts/run_pipeline.py --stage relation  # 关系抽取
python scripts/run_pipeline.py --stage kg        # 导出图谱
```

### 6.5 启动 Neo4j 并导入数据 (可选，系统支持无库内存运行)

项目内置了 Neo4j 的 Docker 配置：

```bash
# 启动 Neo4j 数据库
cd docker
docker compose up -d

# 导入抽取的节点和关系
cd ..
python -c "from kg.export import import_neo4j; import_neo4j()"
```

### 6.6 启动知识图谱 Web 应用程序

本项目自带一个炫酷的暗色科技风 Web 应用：

```bash
# 确保在 KG conda 环境下
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
启动后在浏览器打开：[http://localhost:8000](http://localhost:8000)

---

## 7. 应用程序目标

由于本项目是 **2 人组作业**，必须做出一个知识图谱应用程序。

推荐实现：

**变构飞行器知识图谱查询与辅助分析系统**

最低功能包括：

- 实体搜索
- 实体详情展示
- 图谱子图可视化
- 关系查询
- 证据句追溯
- 图谱统计面板

推荐技术：

- 后端：`FastAPI`
- 图数据库：`Neo4j`
- 可视化：`PyVis` / `ECharts`

---

## 8. 2 人组分工建议

### 成员 A

负责：

- 文本预处理
- 术语抽取
- 实体识别
- 关系抽取
- 图谱数据构建

### 成员 B

负责：

- 标注与评估
- Neo4j 接入
- Web 应用开发
- 可视化与视频展示

### 共同完成

- 本体设计
- 结果分析
- 文档撰写
- 演示录制

---

## 9. 项目交付目标

最终项目应包含：

1. 图谱节点不少于 500
2. 图谱关系不少于 1000
3. 至少 200 个概念标注样本
4. 至少 400 条关系标注样本
5. 自动抽取算法源码
6. 可运行知识图谱应用程序
7. 技术报告
8. 4–5 分钟讲解视频

---
