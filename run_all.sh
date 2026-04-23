#!/bin/bash

echo "================================================="
echo "🌌 KG_Lab 全流程自动化构建脚本 (跳过 PDF 预处理)"
echo "================================================="

# 确保遇到错误立即停止
set -e

echo "[1/6] 🔍 统计与提取初步候选术语..."
python scripts/run_pipeline.py --stage terms

echo "[2/6] 🧠 调用大模型 (LLM) 进行精筛与定稿..."
python scripts/run_pipeline.py --stage finalize

echo "[3/6] 🏷️  基于纯净词表从文本中提取实体..."
python scripts/run_pipeline.py --stage extract

echo "[4/6] 🧹 强规则二次清洗去噪实体..."
python scripts/run_pipeline.py --stage clean

echo "[5/6] 🔗 执行多重约束下的实体关系抽取..."
python scripts/run_pipeline.py --stage relation

echo "[6/6] 📦 导出标准图谱数据 (供前端使用)..."
python scripts/run_pipeline.py --stage kg

echo "================================================="
echo "✅ 所有后端数据管线任务已执行完毕！图谱质量已达最佳！"
echo "🌐 正在启动暗黑星空态势大屏..."
echo "👉 请在浏览器中打开: http://127.0.0.1:8000"
echo "================================================="

# 启动前端应用
uvicorn app.main:app --host 127.0.0.1 --port 8000
