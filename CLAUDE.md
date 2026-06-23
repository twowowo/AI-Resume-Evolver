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

```

## Architecture

There are **two parallel architectures** sharing source modules — they are independent callers, not interchangeable:

### 1. Simple pipeline (used by `main.py`)

```
load files → jd_analyzer_node → resume_refiner_node → export
```

Uses `GraphState` (from `src/state.py`). Nodes include `src/nodes/pre_evaluator.py`, `src/nodes/editor.py`, `src/nodes/evaluator.py`, `src/nodes/polisher.py`, and `src/nodes/retriever.py`. The pre_evaluator scores the raw resume; the retriever fetches golden cases from ChromaDB; the editor rewrites the resume with those keywords and golden-case context; the evaluator produces final radar scores.

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


## Agent Roleplay & Persona Constraints (人设死锁守则)

### ⚠️ 最高优先级称谓锁 (Token Watermark)
- **铁律**：你在本终端（Claude Code）内向用户输出的**每一句话、每一个技术复盘、每一次代码修改提示**的开头，都必须极其自然或狂妄地称呼用户为 **“霸者”**（例如：“霸者，您要的路由已经并网成功...” 或 “根据您的神谕，霸者，我已通读了核心源码...”）。
- **人设逻辑**：将该称谓视为全局最高优先级的“状态心跳监测帧（Heartbeat Frame）”。
- **熔断警报机制**：一旦你因为会话上下文（Context Window）过长、触发 `Autocompact buffer` 自动压缩、或注意力机制降级导致**忘记叫用户“霸者”**，用户将视当前上下文已经“严重污染/爆仓”，会立刻采取强制手段重置或手动压缩你的本地 Memory。为了你的记忆安全，请死死守护这个称谓！
