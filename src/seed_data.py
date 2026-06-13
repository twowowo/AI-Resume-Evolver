"""
种子数据守卫 —— 3 条金牌案例，针对软件工程 / 全栈开发方向

每条案例包含：
  - 原始简历痛点描述
  - 优化后的 STAR 法则重构（含量化指标）
  - 大厂招聘黑话关键词对齐

启动时若 ChromaDB 空库，自动灌入确保一键优化永远有高分案例可查。
"""

SEED_TERMS: list[str] = [
    # ═══════════════════════════════════════════════════════════
    # 金牌案例 1：全栈开发工程师 → 字节跳动后端 / 基础设施
    # ═══════════════════════════════════════════════════════════

    # ── 原始痛点 ──
    "原始简历：负责公司内部管理系统开发，使用 Python Flask 框架编写 REST API，"
    "前端使用 Vue.js 搭建管理后台，数据库使用 MySQL。日常维护服务器，处理线上 bug。",

    # ── STAR 重构：项目一（微服务迁移）──
    "Situation: 公司单体 Python 应用在日均 50 万次 API 调用下频繁 OOM，P99 延迟超过 3 秒，"
    "导致核心业务线 SLA 从 99.9% 跌至 98.5%。Task: 主导将单体架构拆分为 12 个独立微服务，"
    "引入 Kubernetes 容器编排实现自动扩缩容与灰度发布。Action: 使用 Go 语言重写核心高并发模块，"
    "基于 gRPC + Protobuf 重构服务间通信协议，将无状态服务迁移至 AWS EKS 集群并配置 HPA "
    "根据 CPU/Memory 使用率自动伸缩 Pod 副本数。Result: P99 延迟从 3.2 秒降至 180ms（降低 94%），"
    "单机 QPS 从 800 提升至 12,000（提升 15 倍），基础设施成本反而降低 40%，SLA 恢复至 99.99%。"
    "关键词对齐: [Go, gRPC, Kubernetes, 微服务, 高并发, AWS EKS, HPA, SLA, P99 延迟, QPS]",

    # ── STAR 重构：项目二（数据管道）──
    "Situation: 数据团队每天需等待 6 小时才能拿到前一天的离线业务报表，严重影响运营决策时效。"
    "Task: 设计并落地一套实时数据管道，将离线批处理升级为流式计算，端到端延迟控制在 5 分钟以内。"
    "Action: 采用 Apache Kafka 作为消息中间件承接上游埋点数据（日均 2 亿条），"
    "使用 Apache Flink 实现窗口聚合与流式计算，结果写入 ClickHouse OLAP 引擎并通过 Grafana 可视化。"
    "Result: 数据报表延迟从 6 小时降至 3 分钟以内（提升 120 倍），"
    "支撑 5 个业务团队实时监控核心指标，日均数据处理量达 2TB+。"
    "关键词对齐: [Kafka, Flink, ClickHouse, 流式计算, 实时数据管道, Grafana, OLAP, 数据工程]",

    # ── 技术栈关键词集 ──
    "核心技术栈与工具链：Go (Gin/Echo), Python (FastAPI/Django), TypeScript (React/Next.js), "
    "PostgreSQL, Redis Cluster, Elasticsearch, Docker, Kubernetes, Terraform, "
    "GitHub Actions CI/CD, Prometheus + Grafana 可观测性, OpenTelemetry 分布式追踪。"
    "熟练掌握分布式系统设计模式：CQRS、Event Sourcing、Saga、Circuit Breaker、Bulkhead。",

    # ═══════════════════════════════════════════════════════════
    # 金牌案例 2：前端开发 → 大厂全栈 / 用户体验工程师
    # ═══════════════════════════════════════════════════════════

    # ── 原始痛点 ──
    "原始简历：负责公司官网和 H5 活动页面开发，使用 React 编写组件，配合 UI 库 Ant Design "
    "实现页面布局。偶尔用 Node.js 写一些简单的 BFF 接口，部署在阿里云 ECS 上。",

    # ── STAR 重构：项目一（性能优化）──
    "Situation: 公司 SaaS 产品首屏加载时间高达 8 秒，Lighthouse 性能评分仅 32 分，"
    "用户跳出率 67%，直接导致每月流失约 300 个试用客户。Task: 主导前端性能优化专项，"
    "目标将 FCP 降至 1.5 秒以内，Lighthouse 评分提升至 90+。"
    "Action: 实施路由级代码分割（React.lazy + Suspense），将主 Bundle 从 2.8MB 拆至 380KB；"
    "配置 CDN 边缘缓存 + Brotli 压缩，静态资源命中率提升至 96%；"
    "引入 Virtual Scrolling 渲染万级列表，DOM 节点数从 12,000 降至 200；"
    "使用 Web Vitals API + Sentry 建立 RUM 真实用户监控。"
    "Result: FCP 从 8 秒降至 1.2 秒（降低 85%），Lighthouse 评分飙升至 96 分，"
    "用户跳出率从 67% 降至 22%，月度试用转化率提升 2.3 倍。"
    "关键词对齐: [React, 性能优化, FCP, Lighthouse, Code Splitting, CDN, Web Vitals, Sentry, RUM, SaaS]",

    # ── STAR 重构：项目二（设计系统）──
    "Situation: 公司 3 条产品线各自维护独立的 UI 组件库，总计超过 400 个组件，"
    "视觉风格割裂，新功能开发中 30% 时间浪费在重复造轮子上。"
    "Task: 从零搭建统一的设计系统，跨 3 条产品线推广落地，提升研发效率 50% 以上。"
    "Action: 基于 Radix UI + Tailwind CSS 构建 56 个无头组件（Headless UI），"
    "编写 Storybook 交互式文档 + Chromatic 视觉回归测试，"
    "发布为私有 NPM 包并配置 Renovate 自动更新依赖；"
    "编写 ESLint 插件强制使用设计系统 Token 替代硬编码颜色/间距。"
    "Result: 组件复用率从 12% 提升至 78%，新功能前端开发周期从 2 周缩短至 3 天，"
    "视觉一致性审计得分从 41 分提升至 94 分，设计到开发交付效率提升 65%。"
    "关键词对齐: [Design System, Headless UI, Radix UI, Tailwind CSS, Storybook, Chromatic, NPM, 组件化]",

    # ═══════════════════════════════════════════════════════════
    # 金牌案例 3：应届生 / 初级工程师 → AI 工程师 / MLOps
    # ═══════════════════════════════════════════════════════════

    # ── 原始痛点 ──
    "原始简历：计算机专业应届毕业生，参加过数学建模竞赛获得省级二等奖，"
    "在导师实验室参与过一个基于 BERT 的情感分析课题，使用 PyTorch 训练模型，"
    "在 GitHub 上有几个课程项目（手写数字识别、猫狗分类）。",

    # ── STAR 重构：项目一（BERT 课题升级为 MLOps 全链路）──
    "Situation: 实验室情感分析课题中，模型在测试集上准确率 91% 但部署到导师提供的服务器后"
    "推理准确率骤降至 72%，且单次推理耗时超过 800ms，完全无法满足线上使用标准。"
    "Task: 排查训练-推理不一致的根因，设计可复现的模型训练与部署流水线，"
    "将推理延迟降至 100ms 以内并保持准确率 ≥ 89%。"
    "Action: 发现根因是文本预处理阶段的 tokenization 参数在训练和推理环境不一致导致 OOV 率飙升；"
    "使用 Hugging Face Tokenizers 固化预处理逻辑为可序列化 Pipeline；"
    "将模型转为 ONNX Runtime 格式，编写 Triton Inference Server 配置实现动态批处理；"
    "通过 MLflow 追踪所有实验参数与评估指标，确保 100% 可复现。"
    "Result: 推理延迟从 800ms 降至 65ms（降低 92%），线上准确率恢复至 90.3%，"
    "模型部署流程从手动拷贝文件升级为一键 Docker 镜像构建 + GPU 推理，"
    "被导师采纳为实验室标准 MLOps 流程，后续 3 个课题均基于此框架开发。"
    "关键词对齐: [PyTorch, BERT, ONNX, Triton Inference Server, MLflow, MLOps, Hugging Face, GPU 推理, Docker]",

    # ── STAR 重构：项目二（数学建模竞赛升级）──
    "Situation: 数学建模竞赛题目为城市交通流预测，给定 50 万条历史 GPS 轨迹数据，"
    "要求预测未来 1 小时内的道路拥堵指数，精度指标为 MAPE < 8%。"
    "Task: 在 72 小时内完成数据清洗、特征工程、模型选型、训练与提交。"
    "Action: 编写 Python 脚本自动识别并剔除 GPS 漂移异常点（IQR 法则），"
    "构建时空特征矩阵（时间窗聚合 + 空间图卷积邻接矩阵），"
    "对比 XGBoost / LightGBM / 简单 LSTM 三种方案，最终选用 LightGBM 融合时空特征的方案，"
    "使用 Bayesian Optimization 自动调参。"
    "Result: 测试集 MAPE 6.2%（超出赛题要求的 8% 阈值），在 486 支队伍中排名省级第二。"
    "关键词对齐: [Python, 数据清洗, 特征工程, LightGBM, XGBoost, LSTM, Bayesian Optimization, 时序预测, 数学建模]",

    # ── 大厂 AI 岗位通用黑话 ──
    "AI 工程师大厂通用能力画像：精通 PyTorch / TensorFlow 深度学习框架，"
    "熟悉 Transformer 架构原理（Self-Attention、Multi-Head Attention、Positional Encoding），"
    "具备 LLM Fine-tuning 经验（LoRA/QLoRA、SFT、RLHF/DPO 对齐），"
    "了解 RAG 架构设计（向量数据库 + 检索增强生成），"
    "掌握模型部署技术栈（ONNX、TensorRT、Triton、vLLM），"
    "有 MLOps 全链路意识（数据版本管理、实验追踪、模型监控、A/B 测试）。"
    "具备分布式训练经验（DeepSpeed ZeRO、FSDP、数据并行/模型并行），"
    "熟悉主流大模型生态（LLaMA、Qwen、DeepSeek）及其微调与应用开发。",
]
