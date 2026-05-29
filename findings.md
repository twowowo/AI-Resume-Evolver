# Findings & Decisions

## Requirements
- 砍掉 v1.0 简单管线，全面拥抱 v2.0 LangGraph 多智能体架构
- 将 refiner.py 的 Prompt 工程精华（术语注入 + 案例融合）全量注入 editor.py
- 保持代码库高内聚，唯一应用入口为 run_app.py

## Research Findings

### 1. 已删除的 v1.0 文件清单

| 文件 | 原因 |
|------|------|
| `main.py` | v1.0 入口，GraphState 管线 |
| `debug_run.py` | v1.0 调试脚本，依赖 analyzer + refiner |
| `pipelinetry.py` | v1.0 测试脚本，依赖 analyzer |
| `cli_helper.py` | v1.0 CLI 包装器，subprocess 调用 main.py |
| `src/nodes/analyzer.py` | v1.0 JD 分析节点，输出 gap_list + rich_context_list |
| `src/nodes/refiner.py` | v1.0 简历优化节点（资产已提取至 editor.py） |

### 2. refiner → editor 资产注入明细

| 资产 | 原位置 (refiner.py) | 新位置 (editor.py) | 说明 |
|------|---------------------|---------------------|------|
| `_build_gap_terms_text()` | 原基于 gap_list | `_build_term_injection()` | 改为从 RAG 上下文智能提取短术语 |
| `_build_golden_cases_text()` | 原基于 rich_context_list | `_build_golden_cases()` | 改为从 RAG 上下文提取长条目并编号 |
| `_extract_thinking()` | 原在 refiner | 同名移植 | 提取 Pro 模型 thinking 思维链 |
| `REFINER_SYSTEM_PROMPT` 术语平替段 | 原 prompt 规则二 | 融入 EDITOR_SYSTEM_PROMPT 规则二 | "术语注入库"章节 |
| `REFINER_SYSTEM_PROMPT` 案例利用段 | 原 prompt 底部 | 融入 EDITOR_SYSTEM_PROMPT 规则五 | "金牌案例素材"增强指令 |
| 量化标注规范 | 原 "估算" 标注 | 融入 EDITOR_SYSTEM_PROMPT 规则四 | "（估算）"和"（待确认指标）" |
| 技术深度挖掘示例 | 原 3 条示例 | 扩展为 EDITOR_SYSTEM_PROMPT 规则三 | 增补"缓存三问题"示例 |
| `traceback.print_exc()` | 原错误处理 | 融入 editor_node 异常处理 | 更完整的错误诊断 |

### 3. editor.py 核心架构（v2.0 满血版）

```
editor_node(state: AgentState)
│
├── _split_rag_items(rag_context) → list[str]
│   └── 按双换行拆分，过滤空项和标签头
│
├── _build_term_injection(items) → str
│   └── 短条目(<150字) → 术语平替库 | 长条目首句 → 术语参考
│       └── 最多 25 条，去重，编号
│
├── _build_golden_cases(items) → str
│   └── 长条目(≥80字) → 案例库 | 最多 8 条，编号
│
├── EDITOR_SYSTEM_PROMPT (融合版)
│   ├── 规则一：STAR 法则强制重构
│   ├── 规则二：动词升级 + {term_injection} 术语注入库
│   ├── 规则三：技术深度挖掘（含 3 条对照示例）
│   ├── 规则四：指标量化（"估算"/"待确认指标"双标注）
│   ├── 规则五：金牌案例深度利用 + {golden_cases}
│   ├── 规则六：严禁编造
│   ├── 规则七：输出格式
│   ├── {web_search_context} 联网搜索补充
│   ├── {jd} 目标岗位
│   └── {resume} 原始简历
│
├── LLM 调用 (Flash 或 Pro + Thinking)
│   └── _extract_thinking(response) → 思维链
│
├── _build_critique(original, revised, thinking) → 毒舌批评
│
└── return { revised_resume, internal_monologue }
```

### 4. 当前 v2.0 节点全景

| 节点 | 文件 | 角色 | 模型 |
|------|------|------|------|
| retriever | `src/nodes/retriever.py` | RAG 混合检索（向量+BM25 RRF） | ONNX Embedding |
| tavily_search | `src/tools/search.py` | 联网搜索公司文化/技术趋势 | Tavily API |
| **editor** | **`src/nodes/editor.py`** | **粗/中粒度完整重写 + 术语灌注** | **Flash/Pro** |
| evaluator | `src/nodes/evaluator.py` | 三维评分（JD/STAR/动词） | Flash |
| polisher | `src/nodes/polisher.py` | 靶向精修（仅改被点名问题） | Pro + Thinking |

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| RAG 自动拆分代替 gap_list | 不依赖已删除的 analyzer.py，editor 从 rag_context 自给自足 |
| 短条目→术语注入库 | action_verbs / industry_standard 的短条目天然适合做动词平替 |
| 长条目→金牌案例 | 完整技术段落保留上下文，模型可理解逻辑链而非生硬照搬 |
| 保留 Pro + Thinking 双模式 | 与 polisher 一致，Pro 模式提供思维链审计能力 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 删除 analyzer.py 后失去 gap_list 关键词来源 | 改为从 RAG 上下文自动拆分提取，短条目→术语，长条目→案例 |

## Resources
- 唯一入口: `run_app.py`
- 核心图: `src/graph.py` (v2.0 LangGraph 工作流)
- 状态定义: `src/state.py` (仅 AgentState)
- 节点: `src/nodes/retriever.py`, `editor.py`, `evaluator.py`, `polisher.py`
- 工具: `src/tools/search.py`, `src/utils/{llm,vector_store,exporter,loader}.py`
- RAG 存储: `chroma_db/` (352 条术语)
- 参考数据: `data/reference/` (4 个源文件)

---
*Update this file after every 2 view/browser/search operations*
