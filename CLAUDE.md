# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

AI-Resume-Evolver is an AI-powered resume optimization tool. It takes a raw resume + a target job description (JD), uses LangGraph agents with DeepSeek LLMs to analyze gaps, retrieves "golden case" material from a ChromaDB vector store, optionally searches the web via Tavily for company culture / tech trends, and rewrites the resume applying STAR methodology, upgraded verbs, and quantified metrics. Output can be exported as DOCX or PDF.

## Environment & dependencies

Python 3.12 in `.venv/`. There is **no `requirements.txt` or `pyproject.toml`** — dependencies were installed directly. Key packages: `langgraph`, `langchain-openai`, `langchain-core`, `chromadb`, `rank-bm25`, `uvicorn`, `python-dotenv`, `openai`, `onnxruntime`.

Before running, ensure these are also in the venv (they are imported but may be missing from the current install):
```
fastapi, python-docx, docx2txt, reportlab, tavily-python, langchain-chroma, langchain-classic
```

API keys in `.env` (never commit this file). Required: `DEEPSEEK_API_KEY` and `TAVILY_API_KEY`. The `.env` also sets model names (`MODEL_FLASH`, `MODEL_PRO`), `USE_PRO_MODEL`, and `FORCE_WEB_SEARCH`.

## Common commands

```bash
# Ingest reference data into ChromaDB
python scripts/ingest_data.py

# Run the simple pipeline (CLI mode)
python main.py -r data/resumes/简历.docx -j data/jds/jd.txt -e docx -o output/result

# Run the simple pipeline with built-in test JD (no JD file)
python main.py -r data/resumes/简历.docx -e pdf

# Start FastAPI server
python main.py --server

# Run the interactive LangGraph agent pipeline
python run_app.py

# Interactive CLI helper (wraps main.py via subprocess)
python cli_helper.py
```

## Architecture

There are **two parallel architectures** sharing source modules — they are independent callers, not interchangeable:

### 1. Simple pipeline (used by `main.py`, `debug_run.py`, `pipelinetry.py`)

```
load files → jd_analyzer_node → resume_refiner_node → export
```

Uses `GraphState` (from `src/state.py`). Nodes are in `src/nodes/analyzer.py` and `src/nodes/refiner.py`. The analyzer extracts keywords from the JD and enriches them via hybrid RAG retrieval; the refiner rewrites the resume with those keywords and golden-case context.

### 2. LangGraph agent (used by `run_app.py`)

```
retriever → [conditional: needs_web_search?] → tavily_search (optional) → editor → END
```

Uses `AgentState` (from `src/state.py`). Graph is built in `src/graph.py`. Nodes: `src/nodes/retriever.py`, `src/tools/search.py` (Tavily), `src/nodes/editor.py`. The editor generates a "毒舌批评" (brutal critique) as `internal_monologue` alongside the revised resume.

### Key source modules

| Module | Purpose |
|---|---|
| `src/utils/llm.py` | ChatOpenAI factory for DeepSeek (`get_flash_client`, `get_pro_client`). Pro client enables `thinking` extra_body. |
| `src/utils/vector_store.py` | ChromaDB wrapper + CJK tokenizer + BM25 + hybrid RRF retrieval. Also has `MultiQueryRetriever` via langchain-classic. |
| `src/utils/exporter.py` | Markdown → DOCX (python-docx) and Markdown → PDF (reportlab) export with Chinese font support. Font search paths: `assets/fonts/` and `C:/Windows/Fonts`. |
| `src/utils/loader.py` | DOCX (via `docx2txt`) and TXT loading. |
| `src/config.py` | ChromaDB client factory (local `PersistentClient` or remote `HttpClient`). Data stored in `chroma_db/`. |
| `src/tools/search.py` | Tavily web search with company culture detection map (ByteDance, Alibaba, Tencent, etc.) and tech keyword regex extraction. |
| `scripts/ingest_data.py` | Ingests `data/reference/` files into ChromaDB, then rebuilds BM25 index. |
| `data/reference/` | Source material for RAG (action_verbs.txt, industry_standard.txt, 金牌案例库.docx). 352 terms total. |

### State schemas

Two `TypedDict` classes in `src/state.py`:
- **`GraphState`** — `raw_resume`, `target_jd`, `gap_list`, `rich_context_list`, `rag_context`, `refined_resume`, `feedback`, `revision_count`
- **`AgentState`** — `resume`, `jd`, `rag_context`, `revised_resume`, `internal_monologue`, `tool_outputs` (with `operator.add` reducer for list append)

The editor node (`src/nodes/editor.py`) writes `internal_monologue` as a brutally honest Chinese critique of the original resume, describing 3 core flaws and what the revision changed.
