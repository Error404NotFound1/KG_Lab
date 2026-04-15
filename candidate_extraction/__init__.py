"""候选抽取模块入口（规则 + NER + 关系抽取）"""
from .ner import train_ner, predict_ner

__all__ = ["train_ner", "predict_ner"]
