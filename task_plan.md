# Task Plan: AI-Resume-Evolver 核心节点深度开发

## Goal
在纯净 v2.0 LangGraph 多智能体博弈架构上，持续打磨 editor → evaluator ⇄ polisher 闭环的每一环质量。

## Current Phase
Phase 2: editor.py 满血版已就绪 — 等待端到端验证

## Phases

### Phase 1: 架构审计与 v1.0 瘦身 ✅
- [x] 全量源码扫描，理清模块依赖关系
- [x] 确认 RAG 数据灌注链路完整性（352 条术语，ChromaDB + BM25 + RRF）
- [x] 梳理 v2.0-alpha 博弈论闭环现状
- [x] **砍掉 v1.0 简单管线**：删除 main.py, debug_run.py, pipelinetry.py, cli_helper.py
- [x] **删除 v1.0 节点**：src/nodes/analyzer.py, src/nodes/refiner.py
- [x] **清理 GraphState**：src/state.py 仅保留 AgentState
- **Status:** complete

### Phase 2: refiner → editor 核心合并 ✅
- [x] 提取 refiner.py 的术语注入逻辑（_build_term_injection）
- [x] 提取 refiner.py 的案例融合逻辑（_build_golden_cases）
- [x] 提取 refiner.py 的 thinking 提取逻辑（_extract_thinking）
- [x] 融合 prompt：术语平替 + 金牌案例 + 联网搜索 + STAR + 量化指标
- [x] 实现智能 RAG 拆分器（_split_rag_items）：短条目→术语库，长条目→案例库
- [x] 语法验证通过
- **Status:** complete

### Phase 3: 端到端集成验证
- [ ] 运行 `python run_app.py` 全链路测试
- [ ] 验证 retriever → editor 的 RAG 数据流正确传递
- [ ] 验证 evaluator 对 editor 输出的评分
- [ ] 验证 polisher 精修闭环正常工作
- [ ] 边界情况：空简历、空 RAG、API 超时
- **Status:** pending

### Phase 4: 终极博弈论架构升级
- [ ] 设计多模型对抗配置（如 DeepSeek-V4 Polisher vs Qwen3 Evaluator）
- [ ] 在 .env 中预留 MODEL_EVALUATOR / MODEL_POLISHER 配置位
- [ ] 设计评分趋势追踪（记录每轮 score 变化曲线）
- [ ] 可配置的对抗轮次与通过阈值
- **Status:** pending

---

## 当前 v2.0 纯净架构

```
run_app.py (唯一入口)
       │
       ▼
  src/graph.py
       │
       ├── retriever (RAG 混合检索)
       │       │
       │       ▼
       ├── [条件: needs_web_search?]
       │       ├── YES → tavily_search → editor
       │       └── NO  ─────────────────→ editor (满血版·术语+案例双通道注入)
       │                                      │
       │                                      ▼
       ├────────────────────────────── evaluator (三维评分)
       │                                      │
       │                              [条件: score<70 & iter<3?]
       │                                  ├── YES → polisher (靶向精修) → evaluator (闭环)
       │                                  └── NO  → END
```

## Key Questions
1. 多模型对抗（终极博弈架构）是否在当前迭代实现，还是本次打磨 editor 质量？
2. 是否需要给 editor 增加多轮自我反思机制（不等 evaluator 反馈，内部先自检）？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 砍掉全部 v1.0 管线 | 保持代码库高内聚，唯一入口 run_app.py |
| refiner 资产注入 editor | 术语注入+案例融合是核心能力，editor 是唯一粗优化入口 |
| RAG 自动拆分（短→术语，长→案例） | 不依赖已删除的 analyzer.py 的 gap_list，editor 自给自足 |
| GraphState 彻底移除 | v1.0 管线已不存在，无任何引用 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| - | - | - |

## Notes
- 当前分支 `529try`，基于 `5a83cd2`
- 删除的文件：main.py, debug_run.py, pipelinetry.py, cli_helper.py, src/nodes/analyzer.py, src/nodes/refiner.py
- 修改的文件：src/state.py (移除 GraphState), src/nodes/editor.py (全量重写, 融合 refiner 资产)
