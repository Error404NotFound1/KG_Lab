import re
import jieba

def clean_text(text: str) -> str:
    """清理文本：统一换行、去除多余空白、合并断行"""
    # 统一换行
    text = text.replace('\r\n', '\n')
    # 合并断行：如果行尾跟着中文，且没有标点符号，或者带有连字符（英文），可以去除换行符，但这里提供一个简单的通用版本
    # 这里我们只做最基础的清洗：把多个空行合并，并去掉首尾多余空格
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    return '\n'.join(cleaned_lines)

def split_sentences(text: str) -> list[str]:
    """句子切分"""
    # 基于常见标点符号进行切分
    # 替换句号、感叹号、问号为自身+换行符，以保留标点
    text = re.sub(r'([。！？!?])', r'\1\n', text)
    sentences = text.split('\n')
    return [s.strip() for s in sentences if s.strip()]

def tokenize_sentence(sentence: str) -> list[str]:
    """中文分词"""
    return list(jieba.cut(sentence))
