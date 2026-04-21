import re
import jieba

def clean_text(text: str) -> str:
    """清理文本：统一换行、去除多余空白、合并断行"""
    if not text:
        return ""

    # 统一换行
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = text.replace('\u00a0', ' ')

    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r'\d{1,4}', line):
            continue
        if len(line) >= 12 and len(set(line)) <= 3:
            continue
        line = re.sub(r'[ \t\f\v]+', ' ', line)
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)

def split_sentences(text: str) -> list[str]:
    """句子切分"""
    if not text:
        return []

    # 基于常见标点符号进行切分，并兼容中文文献常见的分号、冒号和换行断句
    text = re.sub(r'([。！？!?；;])', r'\1\n', text)
    text = re.sub(r'\n+', '\n', text)
    sentences = text.split('\n')
    return [s.strip() for s in sentences if s.strip()]

def tokenize_sentence(sentence: str) -> list[str]:
    """中文分词"""
    return list(jieba.cut(sentence))
