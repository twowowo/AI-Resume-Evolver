import docx2txt


def load_docx(file_path: str) -> str:
    text = docx2txt.process(file_path)
    if text is None:
        return ""
    return text.strip()


def load_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()
