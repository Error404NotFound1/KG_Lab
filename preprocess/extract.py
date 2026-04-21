"""
PDF 文本抽取模块

策略（依次尝试，全部为纯文字读取，仅最后才降级至大模型 OCR）：
  1. PyMuPDF  get_text("rawdict") 字符级精确提取
  2. pdfminer.six  细粒度 CID 字体解析（对无 ToUnicode 映射的字型更友好）
    3. OpenAI 兼容视觉模型（兜底）
"""

import base64
import json
import logging
import os
import re
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OCR_CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_TEXT_SCAN_WORKERS = 10
DEFAULT_OCR_WORKERS = 10
PAGE_PROGRESS_STEP = 5

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WEIRD_SYMBOL_RE = re.compile(r"[\uFFFD\u2022\u25A0\u25CF\u25AA\u25AB\u2605\u2606]")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+")
_NOISY_TOKEN_RE = re.compile(r"[A-Za-z0-9]{8,}")
_OCR_MODE_LOCK = threading.Lock()
_OCR_CLIENT_LOCK = threading.Lock()
_OCR_CLIENT = None
_OCR_CONFIG_LOCK = threading.Lock()
_OCR_CONFIG = None
_OCR_MODE_REPORTED = False


def _report_ocr_mode(mode_label: str) -> None:
    global _OCR_MODE_REPORTED
    with _OCR_MODE_LOCK:
        if _OCR_MODE_REPORTED:
            return
        _OCR_MODE_REPORTED = True
    print(f"[识别] 当前使用: {mode_label}")
    logger.info("[识别] 当前使用: %s", mode_label)


def _load_ocr_config() -> dict:
    global _OCR_CONFIG
    if _OCR_CONFIG is not None:
        return _OCR_CONFIG

    with _OCR_CONFIG_LOCK:
        if _OCR_CONFIG is not None:
            return _OCR_CONFIG

        if not OCR_CONFIG_PATH.exists():
            raise FileNotFoundError(f"未找到 OCR 配置文件: {OCR_CONFIG_PATH}")

        with open(OCR_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        config = data.get("ocr", data)
        if not isinstance(config, dict):
            raise ValueError("config.json 中的 ocr 配置必须是对象")

        required_keys = ["api_key", "base_url", "model"]
        missing_keys = [key for key in required_keys if not str(config.get(key, "")).strip()]
        if missing_keys:
            raise ValueError(f"OCR 配置缺少必要字段: {', '.join(missing_keys)}")

        api_key = str(config.get("api_key", "")).strip()
        if api_key.upper().startswith("YOUR_"):
            raise ValueError("请先在 config.json 中填入有效的 api_key")

        _OCR_CONFIG = config
        return _OCR_CONFIG


def preview_ocr_backend() -> str:
    """预览当前视觉模型识别配置。"""
    try:
        config = _load_ocr_config()
        return f"视觉模型({config['model']}) @ {config['base_url']}"
    except Exception as exc:
        return f"视觉模型(未配置: {exc})"


def _strip_model_wrapping(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text|markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _format_page_ranges(page_numbers: list[int]) -> str:
    if not page_numbers:
        return ""

    sorted_pages = sorted(page + 1 for page in page_numbers)
    ranges = []
    start = prev = sorted_pages[0]

    for page in sorted_pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = page

    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(ranges)


def _get_ocr_client():
    global _OCR_CLIENT
    if _OCR_CLIENT is not None:
        return _OCR_CLIENT

    with _OCR_CLIENT_LOCK:
        if _OCR_CLIENT is not None:
            return _OCR_CLIENT

        config = _load_ocr_config()
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError("请执行：pip install openai") from exc

        client_kwargs = {
            "api_key": config["api_key"],
            "base_url": config["base_url"],
        }
        timeout = config.get("timeout")
        if timeout:
            client_kwargs["timeout"] = timeout

        _OCR_CLIENT = OpenAI(**client_kwargs)
        _report_ocr_mode(f"视觉模型({config['model']})")
        return _OCR_CLIENT

# ---------- 乱码检测 ----------

def is_garbled(text: str) -> bool:
    """
    检测提取结果是否为乱码。
    规则：综合判断汉字占比、符号占比、异常长串 token 和控制字符。
    主要面向中文语料，若几乎没有汉字且充满符号/乱码 token，则判定为乱码。
    """
    stripped = re.sub(r"\s", "", text)
    if len(stripped) < 10:
        return True

    han_count = len(_HAN_RE.findall(stripped))
    latin_count = len(_LATIN_WORD_RE.findall(stripped))
    valid_count = len(re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]", stripped))
    symbol_count = len(re.findall(r"[^\u4e00-\u9fa5a-zA-Z0-9]", stripped))
    noisy_tokens = len(_NOISY_TOKEN_RE.findall(stripped))
    control_count = len(_CONTROL_CHAR_RE.findall(text))

    han_ratio = han_count / len(stripped)
    symbol_ratio = symbol_count / len(stripped)
    valid_ratio = valid_count / len(stripped)

    if control_count > 0:
        return True

    # 中文文档中，几乎没有汉字但出现大量符号、长串字母数字混排时，基本就是抽取乱码。
    if han_ratio < 0.05 and symbol_ratio > 0.25:
        return True

    # 这类页面常见于乱码：大量不间断的字母数字串，缺少正常词语边界。
    if han_ratio < 0.08 and noisy_tokens >= 2 and symbol_ratio > 0.15:
        return True

    # 纯英文说明页不应误杀；如果确实是正常英文段落，通常会有较明显的词边界。
    if han_ratio < 0.02 and latin_count >= 3 and symbol_ratio > 0.35 and " " not in text:
        return True

    return valid_ratio < 0.45 and han_ratio < 0.12


def normalize_extracted_text(text: str) -> str:
    """尽量移除抽取中的控制字符、重复空白和明显的页眉页脚残片。"""
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHAR_RE.sub("", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    cleaned_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) >= 12 and len(set(line)) <= 3:
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def text_quality_score(text: str) -> float:
    """评估可读性，分数越高越像正常文本。"""
    if not text:
        return 0.0

    stripped = re.sub(r"\s", "", text)
    if not stripped:
        return 0.0

    valid = len(re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]", stripped))
    han = len(_HAN_RE.findall(stripped))
    symbol = len(re.findall(r"[^\u4e00-\u9fa5a-zA-Z0-9]", stripped))
    control = len(_CONTROL_CHAR_RE.findall(text))
    weird = len(_WEIRD_SYMBOL_RE.findall(text))
    valid_ratio = valid / len(stripped)
    han_ratio = han / len(stripped)
    symbol_ratio = symbol / len(stripped)
    penalty = (control + weird) / max(len(stripped), 1)
    return valid_ratio + han_ratio * 0.8 - symbol_ratio * 0.6 - penalty


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


def _extract_page_pymupdf_text(page) -> str:
    """使用 PyMuPDF 普通文本模式作为补充抽取。"""
    try:
        return page.get_text("text", sort=True)
    except Exception:
        return ""


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


def _scan_page_text(pdf_path: Path, page_num: int) -> str:
    """并行扫描单页的文本层，优先纯文字提取，必要时回退到 pdfminer。"""
    try:
        import fitz
    except ImportError:
        raise ImportError("请执行：pip install PyMuPDF")

    with fitz.open(pdf_path) as doc:
        page = doc[page_num]

        candidates = []
        text = normalize_extracted_text(_extract_page_pymupdf(page))
        if text:
            candidates.append(text)

        plain_text = normalize_extracted_text(_extract_page_pymupdf_text(page))
        if plain_text:
            candidates.append(plain_text)

        best_text = max(candidates, key=text_quality_score) if candidates else ""

        if is_garbled(best_text):
            try:
                text = normalize_extracted_text(_extract_page_pdfminer(pdf_path, page_num))
            except Exception as exc:
                logger.debug("[%s] 第 %d 页 pdfminer 失败: %s", pdf_path.name, page_num + 1, exc)
                text = ""
            if text:
                candidates.append(text)
            best_text = max(candidates, key=text_quality_score) if candidates else ""

        if _CID_PAT.search(best_text):
            decoded = normalize_extracted_text(_decode_cid_as_gbk(best_text))
            if not is_garbled(decoded):
                best_text = decoded

        return best_text


# ---------- 策略 3：OpenAI 兼容视觉模型识别 ----------

def _ocr_page_from_pdf(pdf_path: Path, page_num: int, pdf_name: str) -> str:
    try:
        import fitz
    except ImportError:
        raise ImportError("请执行：pip install PyMuPDF")

    config = _load_ocr_config()
    zoom = float(config.get("render_zoom", 1.5))
    with fitz.open(pdf_path) as doc:
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image_bytes = pix.tobytes("png")
    image_base64 = base64.b64encode(image_bytes).decode("ascii")

    client = _get_ocr_client()
    user_prompt = config.get(
        "user_prompt",
        "请准确识别这页图片中的正文文字，只输出可见文本，保持原文顺序，不要解释，不要添加额外内容。",
    )
    system_prompt = config.get(
        "system_prompt",
        "你是一个高精度 OCR 引擎。只输出图片中可见的正文文字，尽量保留原始换行、标点和段落结构。",
    )
    detail = config.get("detail", "high")

    data_url = f"data:image/png;base64,{image_base64}"
    try:
        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": detail}},
                    ],
                },
            ],
            temperature=float(config.get("temperature", 0)),
            max_tokens=int(config.get("max_tokens", 4096)),
        )
    except Exception as exc:
        raise RuntimeError(f"[{pdf_name}] 第 {page_num + 1} 页视觉模型识别失败: {exc}") from exc

    content = response.choices[0].message.content if response.choices else ""
    return _strip_model_wrapping(content or "")


def _resolve_ocr_workers(ocr_workers: int | None = None) -> int:
    if ocr_workers is None:
        return min(DEFAULT_OCR_WORKERS, os.cpu_count() or 1)
    return max(1, ocr_workers)


def _resolve_scan_workers(scan_workers: int | None = None) -> int:
    if scan_workers is None:
        return min(DEFAULT_TEXT_SCAN_WORKERS, os.cpu_count() or 1)
    return max(1, scan_workers)


# ---------- 主入口 ----------

def extract_text(pdf_path: str, ocr_workers: int | None = None) -> str:
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

    with fitz.open(pdf_file) as doc:
        total_pages = doc.page_count
        scan_workers = _resolve_scan_workers()
        print(f"[识别] 正在并行扫描文本层，共 {total_pages} 页，采用 {scan_workers} 线程: {pdf_file.name}")
        text_blocks = [""] * doc.page_count
        ocr_pages = []
        with ThreadPoolExecutor(max_workers=scan_workers) as executor:
            futures = {executor.submit(_scan_page_text, pdf_file, pn): pn for pn in range(total_pages)}
            for index, future in enumerate(as_completed(futures), start=1):
                pn = futures[future]
                page_no = pn + 1
                try:
                    best_text = future.result()
                except Exception as exc:
                    logger.warning("[%s] 第 %d 页文本层扫描失败: %s", pdf_file.name, page_no, exc)
                    best_text = ""

                if is_garbled(best_text):
                    ocr_pages.append(pn)
                    text_blocks[pn] = ""
                else:
                    text_blocks[pn] = best_text

                if page_no == 1 or page_no == total_pages or index % PAGE_PROGRESS_STEP == 0:
                    print(f"[识别] 文本层扫描进度: {index}/{total_pages} 页 - {pdf_file.name}")

        ocr_pages.sort()

    if ocr_pages:
        workers = _resolve_ocr_workers(ocr_workers) if len(ocr_pages) > 1 else 1
        page_range_text = _format_page_ranges(ocr_pages)
        print(f"[识别] 需要视觉模型识别 {len(ocr_pages)} 页，采用 {workers} 线程并发：{page_range_text}")

        total_ocr_pages = len(ocr_pages)
        page_positions = {page_num: index + 1 for index, page_num in enumerate(ocr_pages)}

        def _ocr_job(page_num: int) -> tuple[int, str]:
            try:
                text = normalize_extracted_text(
                    _ocr_page_from_pdf(
                        pdf_file,
                        page_num,
                        pdf_file.name,
                    )
                )
            except Exception as e:
                logger.error("[%s] 第 %d 页 OCR 失败: %s", pdf_file.name, page_num + 1, e)
                text = ""
            if is_garbled(text):
                logger.warning("[%s] 第 %d 页抽取结果仍然异常，保留空白占位以便后续人工复核", pdf_file.name, page_num + 1)
                text = ""
            return page_num, text

        if workers == 1 or len(ocr_pages) == 1:
            for page_num in ocr_pages:
                page_index = page_positions[page_num]
                _, text = _ocr_job(page_num)
                text_blocks[page_num] = text
                print(f"[识别] 完成第 {page_index}/{total_ocr_pages} 页: {pdf_file.name} 第 {page_num + 1} 页")
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for page_num in ocr_pages:
                    page_index = page_positions[page_num]
                    futures[executor.submit(_ocr_job, page_num)] = page_num
                for future in as_completed(futures):
                    page_num, text = future.result()
                    text_blocks[page_num] = text
                    page_index = page_positions[page_num]
                    print(f"[识别] 完成第 {page_index}/{total_ocr_pages} 页: {pdf_file.name} 第 {page_num + 1} 页")

    return "\n".join(text_blocks)
