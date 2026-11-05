"""Kitchen documents (SOPs, food safety rules, donation policies, menus...) that FeedForward takes into account.

Retrieval augmented generation, kept local and explainable:
1. Upload: PDF (pypdf), Word .docx (read from its XML), plain text, Markdown or CSV. The text is cut into passages of
   about 120 words that keep paragraphs together, each remembering its document and page.
2. Retrieval: TF-IDF over the passages (scikit-learn), cosine similarity to the question. No outside service and no
   key: the same question always finds the same passages, and each one says where it came from.
3. Use: the copilot puts the best passages next to the forecast figures it explains (so the language model may follow
   and quote them) and shows them under its answer; the Documents view answers questions from them; the Donations
   view and Plans read the rules found in them (rules()).

Files live in the admin log folder (knowledge/), which is never committed: SOPs are the kitchen's own.
"""

import io
import json
import re
import secrets
import threading
import zipfile
from datetime import datetime
from functools import lru_cache

from feedforward import config as C

MAX_BYTES = 12 * 1024 * 1024
PASSAGE_WORDS = 120
KINDS = {".pdf": "pdf", ".docx": "docx", ".txt": "text", ".md": "text", ".csv": "text"}
_lock = threading.RLock()


class DocumentError(ValueError):
    """A document that cannot be read or found, with a message for the person."""


def _folder():
    return C.ADMIN_LOG_DIR / "knowledge"


def _index_path():
    return _folder() / "documents.json"


def _passages_path():
    return _folder() / "passages.json"


def _load(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------- reading files

def _pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(p.extract_text() or "") for p in reader.pages]
    except Exception as exc:  # noqa: BLE001  (a damaged or encrypted PDF)
        raise DocumentError(f"This PDF could not be read ({type(exc).__name__}). Save it again as a normal PDF, or upload it as text.") from exc


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise DocumentError("This Word file could not be read. Save it as .docx (not .doc) and upload it again.") from exc
    xml = re.sub(r"</w:p>", "\n\n", xml)
    xml = re.sub(r"<w:tab/>", " ", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", text)))


def read_pages(filename: str, data: bytes) -> tuple[str, list[str]]:
    """(kind, text of each page). Word and text files count as one page."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = KINDS.get(ext)
    if kind is None:
        raise DocumentError("Upload a PDF, a Word file (.docx), or a text, Markdown or CSV file.")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB. Split it or upload the relevant part.")
    if kind == "pdf":
        pages = _pdf_pages(data)
    elif kind == "docx":
        pages = [_docx_text(data)]
    else:
        pages = [data.decode("utf-8", errors="replace")]
    if not "".join(pages).strip():
        raise DocumentError("No text was found in this file. A scanned PDF needs text recognition first.")
    return kind, pages


def split_passages(pages: list[str], words: int = PASSAGE_WORDS) -> list[dict]:
    """Passages of about `words` words that keep paragraphs together. Each has its page number (from 1)."""
    out = []
    for page_no, text in enumerate(pages, start=1):
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text)]
        paras = [p for p in paras if p]
        if len(paras) <= 1:   # PDFs often lose blank lines: fall back to sentences
            paras = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]
        cur: list[str] = []
        for p in paras:
            if cur and len(" ".join(cur).split()) + len(p.split()) > words:
                out.append({"page": page_no, "text": " ".join(cur)})
                cur = []
            cur.append(p)
        if cur:
            out.append({"page": page_no, "text": " ".join(cur)})
    return out


# ---------- the library

def documents() -> list[dict]:
    """Every document, newest first (no text)."""
    return sorted(_load(_index_path(), {}).values(), key=lambda d: d["uploaded_at"], reverse=True)


def add_document(filename: str, data: bytes, title: str = "", category: str = "sop", uploaded_by: str = "") -> dict:
    """Read, split and store a document. Returns its entry."""
    kind, pages = read_pages(filename, data)
    passages = split_passages(pages)
    with _lock:
        index, store = _load(_index_path(), {}), _load(_passages_path(), [])
        doc_id = secrets.token_hex(5)
        doc = {"id": doc_id, "filename": filename[:160], "title": (title or filename.rsplit(".", 1)[0]).strip()[:160],
               "category": category, "kind": kind, "pages": len(pages), "passages": len(passages),
               "words": sum(len(p["text"].split()) for p in passages), "uploaded_by": uploaded_by,
               "uploaded_at": datetime.now().isoformat(timespec="seconds")}
        index[doc_id] = doc
        store += [{"doc_id": doc_id, "n": i, **p} for i, p in enumerate(passages)]
        _save(_index_path(), index)
        _save(_passages_path(), store)
        _search_index.cache_clear()
    return doc


def delete_document(doc_id: str) -> None:
    with _lock:
        index = _load(_index_path(), {})
        if index.pop(doc_id, None) is None:
            raise DocumentError("No such document.")
        _save(_index_path(), index)
        _save(_passages_path(), [p for p in _load(_passages_path(), []) if p["doc_id"] != doc_id])
        _search_index.cache_clear()


def _signature() -> tuple:
    p = _passages_path()
    return (str(p), p.stat().st_mtime_ns) if p.exists() else (str(p), 0)


@lru_cache(maxsize=4)
def _search_index(signature: tuple):
    from sklearn.feature_extraction.text import TfidfVectorizer
    passages = _load(_passages_path(), [])
    if not passages:
        return None, []
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    matrix = vec.fit_transform([p["text"] for p in passages])
    return (vec, matrix), passages


def search(question: str, k: int = 4, min_score: float = 0.06) -> list[dict]:
    """The passages that best match the question, best first, each with its document title, page and score."""
    model, passages = _search_index(_signature())
    if model is None or not question.strip():
        return []
    vec, matrix = model
    scores = (matrix @ vec.transform([question]).T).toarray().ravel()
    titles = {d["id"]: d for d in documents()}
    out = []
    for i in scores.argsort()[::-1][:k]:
        if scores[i] < min_score:
            break
        p, d = passages[i], titles.get(passages[i]["doc_id"])
        if d:
            out.append({"doc_id": d["id"], "title": d["title"], "category": d["category"], "page": p["page"],
                        "text": p["text"], "score": round(float(scores[i]), 3)})
    return out


# ---------- rules the rest of FeedForward uses

RULES = [
    ("handover_hours", "Hand over surplus cooked food within", r"(?:donat|distribut|hand(?:ed)? over|serv|consum|surplus|leftover|cooked food)[^.]{0,80}?within\s+(\d+(?:\.\d+)?)\s*(?:hours|hrs|hour|h)\b", "hours"),
    ("hot_holding_c", "Keep hot food at or above", r"(?:hot|holding|reheat)[^.]{0,60}?(?:above|at least|minimum of|over|≥|>=)\s*(\d{2})\s*(?:°|degrees|deg)?\s*C", "°C"),
    ("cold_holding_c", "Keep cold food at or below", r"(?:cold|chill|refrigerat)[^.]{0,60}?(?:below|under|at most|maximum of|≤|<=)\s*(\d{1,2})\s*(?:°|degrees|deg)?\s*C", "°C"),
    ("safety_margin_pct", "Cook a safety margin of", r"(?:buffer|margin|extra)[^.]{0,40}?(\d{1,2})\s*(?:%|percent)", "percent"),
    ("min_donation_portions", "Smallest donation worth arranging", r"(?:minimum|at least)\s+(\d{2,4})\s*(?:portions|meals|plates)[^.]{0,40}?(?:donat|pick)", "portions"),
]


def rules() -> list[dict]:
    """Rules found in the documents that FeedForward can use, each with the passage it came from."""
    passages = _load(_passages_path(), [])
    titles = {d["id"]: d["title"] for d in documents()}
    found = {}
    for p in passages:
        for key, label, pattern, unit in RULES:
            if key in found:
                continue
            m = re.search(pattern, p["text"], re.I)
            if m:
                value = float(m.group(1))
                found[key] = {"key": key, "label": label, "value": int(value) if value.is_integer() else value, "unit": unit,
                              "source": titles.get(p["doc_id"], "a document"), "page": p["page"],
                              "quote": p["text"][max(0, m.start() - 60): m.end() + 60].strip()}
    return list(found.values())


def rule_value(key: str, default=None):
    """One rule's value, or `default` when no document states it."""
    return next((r["value"] for r in rules() if r["key"] == key), default)


def summary() -> dict:
    docs = documents()
    return {"documents": len(docs), "passages": sum(d["passages"] for d in docs), "rules": rules()}
