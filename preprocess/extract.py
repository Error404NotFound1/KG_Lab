"""
PDF 文本抽取模块

策略（依次尝试，全部为纯文字读取，仅最后才降级至 OCR）：
  1. PyMuPDF  get_text("rawdict") 字符级精确提取
  2. pdfminer.six  细粒度 CID 字体解析（对无 ToUnicode 映射的字型更友好）
  3. RapidOCR  纯 Python 图像 OCR（兜底）
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------- 乱码检测 ----------

def is_garbled(text: str) -> bool:
    """
    检测提取结果是否为乱码。
    规则：去除空白后，有效的中英文字符（含数字）占比低于 40% 则视为乱码。
    纯英文 / 纯数字 / 中英混排均不被误判。
    """
    stripped = re.sub(r"\s", "", text)
    if len(stripped) < 10:
        return True
    valid = len(re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]", stripped))
    return valid / len(stripped) < 0.4


# ---------- 策略 1：PyMuPDF rawdict 字符级提取 ----------

def _extract_page_pymupdf(page) -> str:
    """
    使用 PyMuPDF 的 rawdict 模式逐字符重建文本。
    rawdict 可以拿到每个 char 以及对应的 glyph origin，即便 ToUnicode 不完整，
    部分字体仍可通过 FontName 替补映射得到可读字符。
    """
    raw = page.get_text("rawdict", flags=0)
    lines = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:   # 0 = text block
            continue
        for line in block.get("lines", []):
            chars = []
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    c = ch.get("c", "")
                    if c:
                        chars.append(c)
            if chars:
                lines.append("".join(chars))
    return "\n".join(lines)


# ---------- 策略 2：pdfminer.six 字符流解析 ----------

def _extract_page_pdfminer(pdf_path: Path, page_num: int) -> str:
    """
    使用 pdfminer.six 对指定页进行低级字符流解析。
    pdfminer 有独立的 CMap 重建逻辑，对部分国产 PDF 制作工具生成的 CID 字体
    有更强的容错能力（它会尝试从 font stream 中反推 GB2312 / BIG5 映射）。
    """
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.layout import LAParams
    except ImportError:
        raise ImportError("请执行：pip install pdfminer.six")

    from io import StringIO
    buf = StringIO()
    with open(pdf_path, "rb") as f:
        extract_text_to_fp(
            f, buf,
            laparams=LAParams(line_margin=0.5),
            page_numbers={page_num},
            output_type="text",
            codec="utf-8",
        )
    return buf.getvalue()


# ---------- 策略 2.5：CID→GBK/GB2312 强制解码 ----------

_CID_PAT = re.compile(r"\(cid:(\d+)\)")

def _decode_cid_as_gbk(text: str) -> str:
    """
    将 pdfminer 无法映射时输出的 (cid:XXXX) 占位符，
    按 GBK/GB2312 两字节大端序强制解码。

    原理：许多国产 PDF 工具（WPS / 方正 / Acrobat 中文版）在嵌入 CID 字体时，
    会省略 ToUnicode 表，但字形的 CID 编号与 GBK 的两字节编码一一对应。
    把 CID 数字直接解释成 GBK 双字节即可还原汉字。
    """
    def _replace(m: re.Match) -> str:
        cid = int(m.group(1))
        raw = cid.to_bytes(2, "big")
        for enc in ("gbk", "gb2312", "gb18030", "big5"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, ValueError):
                pass
        return m.group(0)   # 全部失败则保留原占位符

    return _CID_PAT.sub(_replace, text)


# ---------- 策略 3：RapidOCR（纯 Python，兜底） ----------

def _ocr_page(page, pdf_name: str) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
    except ImportError:
        raise ImportError("请执行：pip install rapidocr-onnxruntime")

    import fitz
    zoom = 2.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    engine = RapidOCR()
    result, _ = engine(img)
    if result:
        return "\n".join(line[1] for line in result if line[1])
    return ""


# ---------- 主入口 ----------

def extract_text(pdf_path: str) -> str:
    """
    三级纯文字优先抽取，只有在前两级均输出乱码时才启动 OCR。
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("请执行：pip install PyMuPDF")

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF 文件未找到: {pdf_path}")

    text_blocks = []
    with fitz.open(pdf_file) as doc:
        for page in doc:
            pn = page.number  # 0-indexed

            # --- 策略 1: PyMuPDF rawdict ---
            text = _extract_page_pymupdf(page)

            if is_garbled(text):
                logger.debug("[%s] 第 %d 页 PyMuPDF rawdict 乱码，尝试 pdfminer.six", pdf_file.name, pn + 1)
                # --- 策略 2: pdfminer.six ---
                try:
                    text = _extract_page_pdfminer(pdf_file, pn)
                except Exception as e:
                    logger.warning("[%s] 第 %d 页 pdfminer 失败: %s", pdf_file.name, pn + 1, e)
                    text = ""

            # --- 策略 2.5: 尝试将 pdfminer 输出的 (cid:XXXX) 按 GBK 强解码 ---
            if _CID_PAT.search(text):
                logger.debug("[%s] 第 %d 页检测到 (cid:...) 占位符，尝试 GBK 强制解码", pdf_file.name, pn + 1)
                decoded = _decode_cid_as_gbk(text)
                if not is_garbled(decoded):
                    text = decoded

            if is_garbled(text):
                logger.warning(
                    "[%s] 第 %d 页文字层彻底不可用（字体无 ToUnicode 映射），降级至 OCR ...",
                    pdf_file.name, pn + 1
                )
                # --- 策略 3: OCR 兜底 ---
                try:
                    text = _ocr_page(page, pdf_file.name)
                except Exception as e:
                    logger.error("[%s] 第 %d 页 OCR 失败: %s", pdf_file.name, pn + 1, e)
                    text = ""

            text_blocks.append(text)

    return "\n".join(text_blocks)
