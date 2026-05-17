import os
import re
import sys
import glob

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from src.utils.loader import load_docx, load_txt
from src.utils.vector_store import add_terms

REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "reference")
REFERENCE_DIR = os.path.abspath(REFERENCE_DIR)

MIN_TERM_LENGTH = 8

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "ingest_result.txt")


def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()


_BRACKET_LABEL = re.compile(r"^\s*\[(.+?)\]\s*")


def _strip_bracket_label(line: str) -> tuple[str, str]:
    m = _BRACKET_LABEL.match(line)
    if m:
        label = m.group(1).strip()
        content = line[m.end():].strip()
        return label, content
    return "", line


def _clean_text(raw: str) -> tuple[list[str], list[dict]]:
    paragraphs = raw.split("\n\n")
    terms: list[str] = []
    metadatas: list[dict] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        lines = para.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            stripped = line.lstrip("-•·*#0123456789.。、)）】〗>»› ")
            stripped = stripped.strip()

            if not stripped:
                continue

            label, content = _strip_bracket_label(stripped)

            if not content:
                continue

            if len(content) >= MIN_TERM_LENGTH:
                terms.append(content)
                meta = {}
                if label:
                    meta["tag"] = label
                meta["source_line"] = stripped[:80]
                metadatas.append(meta)

    return terms, metadatas


def _load_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return load_docx(file_path)
    elif ext == ".txt":
        return load_txt(file_path)
    else:
        print(f"[ingest] 跳过不支持的文件类型: {file_path}")
        return ""


def run():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    txt_files = glob.glob(os.path.join(REFERENCE_DIR, "*.txt"))
    docx_files = glob.glob(os.path.join(REFERENCE_DIR, "*.docx"))
    all_files = sorted(txt_files + docx_files)

    if not all_files:
        log("[ingest] data/reference/ 目录下没有找到 .txt 或 .docx 文件")
        return

    log(f"[ingest] 发现 {len(all_files)} 个文件待处理")
    all_terms: list[str] = []
    all_metadatas: list[dict] = []

    for file_path in all_files:
        file_name = os.path.basename(file_path)
        log(f"[ingest] 读取: {file_name}")

        raw_text = _load_file(file_path)
        if not raw_text:
            log(f"[ingest] 跳过空文件: {file_name}")
            continue

        terms, metadatas = _clean_text(raw_text)
        log(f"[ingest]   -> 清洗后得到 {len(terms)} 条有效术语")
        all_terms.extend(terms)
        all_metadatas.extend(metadatas)

    if not all_terms:
        log("[ingest] 没有有效术语可写入")
        return

    tagged = sum(1 for m in all_metadatas if m.get("tag"))
    log(f"[ingest] 共 {len(all_terms)} 条术语 (其中 {tagged} 条含分类标签)，开始写入 ChromaDB ...")
    add_terms(all_terms, metadatas=all_metadatas)
    log(f"[ingest] 灌注完成！成功存入 {len(all_terms)} 条术语到 {os.path.basename(REFERENCE_DIR)}")

    from src.utils.vector_store import rebuild_bm25
    rebuild_bm25()
    log("[ingest] BM25 索引已重建")


if __name__ == "__main__":
    run()
