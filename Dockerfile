# ═══════════════════════════════════════════════════════════════
# AI-Resume-Evolver 后端 v7.0
# 构建: docker build -t ai-resume-evolver-backend .
# ═══════════════════════════════════════════════════════════════

FROM python:3.11-slim

# ── 系统镜像 + 编译链 (中科大源) ──
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc g++ make libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── HuggingFace 模型缓存路径 (映射到项目本地，而非 ~/.cache) ──
ENV HF_HOME=/app/models/huggingface
ENV HF_HUB_CACHE=/app/models/huggingface

# ── 依赖分层 (清华 PyPI 镜像) ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# ── 源码 ──
COPY . .

# ── 运行时目录 ──
RUN mkdir -p /app/data /app/chroma_db /app/models/huggingface

EXPOSE 8001

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001} --workers 2 --timeout-keep-alive 300 --timeout-graceful-shutdown 30"]
