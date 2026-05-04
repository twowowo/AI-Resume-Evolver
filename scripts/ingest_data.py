import os
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


def _clean_text(raw: str) -> list[str]:
    paragraphs = raw.split("\n\n")
    terms = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        lines = para.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            cleaned = line.lstrip("-•·*#0123456789.。、)）】〗>»› ")
            cleaned = cleaned.strip()

            if len(cleaned) >= MIN_TERM_LENGTH:
                terms.append(cleaned)

    return terms


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
    all_terms = []

    for file_path in all_files:
        file_name = os.path.basename(file_path)
        log(f"[ingest] 读取: {file_name}")

        raw_text = _load_file(file_path)
        if not raw_text:
            log(f"[ingest] 跳过空文件: {file_name}")
            continue

        terms = _clean_text(raw_text)
        log(f"[ingest]   -> 清洗后得到 {len(terms)} 条有效术语")
        all_terms.extend(terms)

    if not all_terms:
        log("[ingest] 没有有效术语可写入")
        return

    log(f"[ingest] 共 {len(all_terms)} 条术语，开始写入 ChromaDB ...")
    add_terms(all_terms)
    log(f"[ingest] 灌注完成！成功存入 {len(all_terms)} 条术语到 resume_evolution_v1")


if __name__ == "__main__":
    run()
