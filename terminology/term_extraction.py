import csv, json, math, re
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    import jieba
except ImportError:
    jieba = None
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except ImportError:
    TfidfVectorizer = None

DEFAULT_MIN_FREQ = 2
DEFAULT_MAX_NGRAM = 4
DEFAULT_MAX_TERMS_FOR_PMI = 4000
DEFAULT_MAX_OUTPUT_TERMS = 1200
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
TEXT_DIR = DATA_DIR / "text"
TERMS_DIR = DATA_DIR / "terminology"
METADATA_DIR = DATA_DIR / "metadata"
PROCESSED_DIR = DATA_DIR / "processed"
TERM_STOPWORDS = {"研究","分析","设计","方法","技术","系统","模型","问题","结果","实验","结构","控制","性能","进行","提出","一种","本文","可以","具有","以及","采用","目录","摘要","关键词","作者","出版社","文献","引言","收稿日期","录用日期","其中","因此","所示","图","表","式中","例如","此外","近年来","在文献","在此基础上","同时","项目","切块","北京","王道","目前","由于","为此","平均时间"}
ENGLISH_STOPWORDS = {"a","an","analysis","and","application","as","at","based","by","cn","control","controlfor","controlof","decision","deformation","design","development","dynamic","dynamics","edu","et","etal","feedback","flight","flexible","for","from","gain","http","https","in","into","integral","is","journal","journalof","learning","method","mission","mode","model","modeling","multibody","neural","nonlin","nonlinear","of","on","optimization","or","partial","performance","policy","press","quad","research","review","right","science","simulation","sliding","state","study","sweep","switched","switching","system","systems","technology","the","time","to","uncertain","variable","vehicle","with","www","begin","end","dot","dfrac","sqrt","frac","cdot","bmatrix","qquad"}
ENGLISH_METADATA_TERMS = {"aiaa","aerospace","buaa","chinese","hkxb","ieee","journal","press","science","piscataway","wang","aviation","editorial"}
FORMULA_TERMS = {"sin","cos","tan","alpha","beta","gamma","delta","theta","omega","rho","mu","psi","phi","varphi","sigma","lambda","dt","lpv","pid","phing","trol"}
ENGLISH_TERM_WHITELIST = {"aircraft","morphing","uav","wing","mpc"}
PERSON_NAME_STOPWORDS = {"王育","王道"}
TYPE_RULES = [("ControlMethod", ["控制","预测控制","自适应","鲁棒","滑模","规划","决策","算法","MPC","反步法"]),("Mechanism", ["机制","驱动","变形","展开","折叠","切换","重构","morphing","变换策略"]),("Structure", ["机翼","翼型","翼面","机身","尾翼","结构","铰接","舵面","wing"]),("Performance", ["升阻比","稳定性","机动性","效率","气动","航程","载荷","性能","高度"]),("Mission", ["任务","巡航","起飞","着陆","机动","跨域","飞行"]),("Parameter", ["攻角","速度","马赫数","参数","角度","载荷因子","雷诺数","高度"]),("Aircraft", ["飞行器","航天器","飞机","无人机","变体","空天","aircraft","uav"])]
TOKEN_PATTERN = re.compile(r"^[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9\-]*$")
ASCII_ONLY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9\-]*$")
LOWER_ASCII_PATTERN = re.compile(r"^[a-z][a-z0-9\-]*$")
CAMEL_JOIN_PATTERN = re.compile(r"[a-z]{2,}[A-Z][a-z]+")
FIGURE_TABLE_PATTERN = re.compile(r"^[图表式]\d+$")


def ensure_dirs() -> None:
    for path in (TERMS_DIR, METADATA_DIR, PROCESSED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def list_text_files(corpus_dir: str | Path | None = None) -> list[Path]:
    if corpus_dir is None:
        base = TEXT_DIR
    else:
        base = Path(corpus_dir)
        if not base.is_absolute():
            base = (PROJECT_ROOT / base).resolve()
    if base.is_file():
        return [base]
    return sorted(base.glob("*.txt"))


def infer_topic(title: str) -> str:
    for topic, keywords in [("变构飞行器", ["变构", "变体", "跨域"]),("飞行控制", ["控制", "姿态", "预测控制", "自学习"]),("气动设计", ["气动", "翼型", "升阻比"]),("结构设计", ["结构", "机翼", "机身"]),("飞行动力学", ["动力学", "轨道", "航天"])]:
        if any(k in title for k in keywords):
            return topic
    return "综合"


def tokenize(text: str) -> list[str]:
    if jieba is None:
        return [t for t in re.split(r"[^\u4e00-\u9fffA-Za-z0-9]+", text) if t]
    return [t.strip() for t in jieba.cut(text) if t.strip()]


def normalize_term(term: str) -> str:
    return term.lower() if ASCII_ONLY_PATTERN.match(term) else term


def is_noise_term(token: str) -> bool:
    lower = token.lower()
    if token in PERSON_NAME_STOPWORDS or token in TERM_STOPWORDS or lower in ENGLISH_STOPWORDS or lower in ENGLISH_METADATA_TERMS or lower in FORMULA_TERMS:
        return True
    if any(k in token for k in ["学报","编辑部","大学","学院","研究所","出版社","期刊","报社"]):
        return True
    if any(p in token for p in ["由式","将式","代入式","根据式","则式","把式","见图","如图","参考文献","绪论"]):
        return True
    if token.startswith("第") and token.endswith("章"):
        return True
    if token in {"可得","可见","所以","但是","这样","此时","显然","得到","方程","代入","计算","基于","然而","注意","如果","由此可见","可以看出","一般来说","另一方面","另外","时间","火箭","美国","左右","导弹","温度","英尺"}:
        return True
    if FIGURE_TABLE_PATTERN.match(token) or (token.startswith("图") and len(token) <= 4) or (token.startswith("表") and len(token) <= 4):
        return True
    if CAMEL_JOIN_PATTERN.search(token):
        return True
    if any(p in lower for p in ["journalof","ofmorphing","inchinese","controlof","controlfor","editor","journal","press","http","https","www","edu","cn"]):
        return True
    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", token))
    has_ascii = bool(re.search(r"[A-Za-z]", token))
    if has_chinese and has_ascii:
        return True
    if ASCII_ONLY_PATTERN.match(token):
        if lower in ENGLISH_TERM_WHITELIST or token.upper() in {"MPC", "UAV"}:
            return False
        if LOWER_ASCII_PATTERN.match(token) or len(token) <= 3 or token[:1].isupper():
            return True
    return False


def valid_token(token: str) -> bool:
    return 2 <= len(token) <= 20 and bool(TOKEN_PATTERN.match(token)) and not is_noise_term(token)


def generate_candidate_terms(tokens: list[str], max_ngram: int = DEFAULT_MAX_NGRAM) -> Counter:
    counter: Counter = Counter(); filtered = [normalize_term(t) for t in tokens if valid_token(t)]
    for n in range(1, max_ngram + 1):
        for idx in range(0, max(0, len(filtered) - n + 1)):
            term = "".join(filtered[idx: idx + n])
            if 2 <= len(term) <= 24 and not is_noise_term(term):
                counter[term] += 1
    return counter


def compute_tfidf_scores(documents: list[str]) -> dict[str, float]:
    if not documents:
        return {}
    if TfidfVectorizer is None:
        doc_tokens = [set(normalize_term(t) for t in tokenize(doc) if valid_token(t)) for doc in documents]
        doc_count, df_counter, tf_counter = len(documents), Counter(), Counter()
        for doc in documents:
            tf_counter.update(normalize_term(t) for t in tokenize(doc) if valid_token(t))
        for tokens in doc_tokens:
            df_counter.update(tokens)
        return {term: float(tf * (math.log((1 + doc_count) / (1 + df_counter.get(term, 1))) + 1)) for term, tf in tf_counter.items()}
    vectorizer = TfidfVectorizer(tokenizer=tokenize, token_pattern=None, lowercase=False, max_features=8000)
    matrix = vectorizer.fit_transform(documents); scores = matrix.sum(axis=0).A1; merged: dict[str, float] = {}
    for term, score in zip([normalize_term(t) for t in vectorizer.get_feature_names_out()], scores):
        if valid_token(term):
            merged[term] = merged.get(term, 0.0) + float(score)
    return merged


def compute_pmi_scores(documents: list[str], candidates: Iterable[str]) -> dict[str, float]:
    joined_corpus = "\n".join(documents).lower(); char_count = max(len(joined_corpus), 1)
    ranked_candidates = sorted(candidates, key=lambda term: (-len(term), term))[:DEFAULT_MAX_TERMS_FOR_PMI]
    pmi_scores: dict[str, float] = {}; total = len(ranked_candidates)
    if total:
        print(f"[terms] 开始计算 PMI，共 {total} 个候选")
    for index, term in enumerate(ranked_candidates, start=1):
        normalized = normalize_term(term); term_freq = joined_corpus.count(normalized.lower())
        if term_freq == 0:
            continue
        splits = []
        for i in range(1, len(normalized)):
            left, right = normalized[:i], normalized[i:]
            left_freq, right_freq = max(joined_corpus.count(left.lower()), 1), max(joined_corpus.count(right.lower()), 1)
            splits.append(math.log2((term_freq * char_count) / (left_freq * right_freq)))
        if splits:
            pmi_scores[normalized] = min(splits)
        if index == 1 or index == total or index % 500 == 0:
            print(f"[terms] PMI 进度: {index}/{total}")
    return pmi_scores


def infer_entity_type(term: str) -> str:
    for entity_type, keywords in TYPE_RULES:
        if any(keyword in term for keyword in keywords):
            return entity_type
    return "Concept"


def build_documents_metadata(files: list[Path]) -> list[dict]:
    return [{"doc_id": f"DOC{index:03d}", "title": file.stem, "file_name": file.name, "topic": infer_topic(file.stem), "path": str(file.relative_to(PROJECT_ROOT))} for index, file in enumerate(files, start=1)]


def export_metadata(files: list[Path], out_path: str | Path | None = None) -> Path:
    ensure_dirs(); target = Path(out_path) if out_path else METADATA_DIR / "documents.csv"
    with open(target, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["doc_id", "title", "file_name", "topic", "path"])
        writer.writeheader(); writer.writerows(build_documents_metadata(files))
    return target


def export_sentences(files: list[Path], out_path: str | Path | None = None) -> Path:
    ensure_dirs(); target = Path(out_path) if out_path else PROCESSED_DIR / "sentences.jsonl"; metadata = build_documents_metadata(files); name_to_doc = {r["file_name"]: r for r in metadata}
    with open(target, "w", encoding="utf-8") as f:
        for file in files:
            record = name_to_doc[file.name]
            lines = [line.strip() for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
            for sentence_id, sentence in enumerate(lines, start=1):
                f.write(json.dumps({"doc_id": record["doc_id"], "title": record["title"], "file_name": record["file_name"], "sentence_id": sentence_id, "text": sentence}, ensure_ascii=False) + "\n")
    return target


def write_terms_csv(rows: list[dict], out_path: Path) -> Path:
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["term", "freq", "tfidf", "pmi", "score", "entity_type", "keep", "alias"])
        writer.writeheader(); writer.writerows(rows)
    return out_path


def extract_terms(corpus_dir: str | Path | None = None, out_path: str | Path | None = None) -> dict[str, Path]:
    ensure_dirs(); files = list_text_files(corpus_dir)
    if not files:
        raise FileNotFoundError("未找到可用的文本语料文件")
    print(f"[terms] 读取文本文件 {len(files)} 篇")
    documents = [file.read_text(encoding="utf-8") for file in files]
    print("[terms] 计算 TF-IDF 分数")
    tfidf_scores = compute_tfidf_scores(documents)
    print("[terms] 生成 n-gram 候选与词频")
    corpus_counter: Counter = Counter()
    for index, document in enumerate(documents, start=1):
        corpus_counter.update(generate_candidate_terms(tokenize(document)))
        if index == 1 or index == len(documents) or index % 5 == 0:
            print(f"[terms] 候选生成进度: {index}/{len(documents)}")
    filtered_terms = [term for term, freq in corpus_counter.items() if freq >= DEFAULT_MIN_FREQ and valid_token(term)]
    filtered_terms.sort(key=lambda term: (-corpus_counter[term], -len(term), term))
    pmi_scores = compute_pmi_scores(documents, filtered_terms[:DEFAULT_MAX_TERMS_FOR_PMI])
    rows = []
    for term in filtered_terms:
        freq, tfidf, pmi = corpus_counter[term], tfidf_scores.get(term, 0.0), pmi_scores.get(term, 0.0)
        rows.append({"term": term, "freq": freq, "tfidf": round(tfidf, 6), "pmi": round(pmi, 6), "score": round(freq * 0.6 + tfidf * 0.3 + max(pmi, 0) * 0.1, 6), "entity_type": infer_entity_type(term), "keep": "Y", "alias": ""})
    rows.sort(key=lambda row: (-float(row["score"]), -int(row["freq"]), row["term"]))
    raw_path = Path(out_path) if out_path else TERMS_DIR / "terms_raw.csv"; clean_path, alias_path = TERMS_DIR / "terms_clean.csv", TERMS_DIR / "alias.csv"
    metadata_path, sentences_path = export_metadata(files), export_sentences(files)
    write_terms_csv(rows, raw_path); write_terms_csv(rows[: min(len(rows), DEFAULT_MAX_OUTPUT_TERMS)], clean_path)
    if not alias_path.exists():
        with open(alias_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["alias", "canonical", "entity_type"])
            writer.writeheader()
    print(f"[terms] 共生成候选术语 {len(rows)} 条")
    return {"terms_raw": raw_path, "terms_clean": clean_path, "alias": alias_path, "metadata": metadata_path, "sentences": sentences_path}
