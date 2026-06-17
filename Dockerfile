# ═══════════════════════════════════════════════════════════════
# AI-Resume-Evolver 后端集装箱说明书 v5.1
# 构建: docker build -t ai-resume-evolver-backend .
# ═══════════════════════════════════════════════════════════════

FROM python:3.11-slim



# ── 强行插入这两行：把容器内的 Linux 软件源切换到国内中科大镜像站 ──
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources


# ── 系统依赖：gcc 编译 onnxruntime / grpcio 等 C 扩展 ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# ── 工作目录 ──
WORKDIR /app

# ── 依赖分层缓存：先拷 requirements.txt，pip install 优先利用 Docker 缓存 ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 拷贝全量源码 ──
COPY . .

# ── 确保数据目录存在（SqliteSaver / ChromaDB 持久化）──
RUN mkdir -p /app/data /app/chroma_db

# ── 暴露端口（由环境变量 PORT 控制，默认 8001）──
EXPOSE 8001

# ── 多 Worker 启动（SqliteSaver 注意：>2 worker 时并发写 SQLite 有锁风险）──
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001} --workers 2 --timeout-keep-alive 300 --timeout-graceful-shutdown 30"]
