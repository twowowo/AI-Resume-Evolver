# ═══════════════════════════════════════════════════════════════
# AI-Resume-Evolver 前端集装箱说明书 v5.1
# 构建: docker build -t ai-resume-evolver-frontend ./frontend
# ═══════════════════════════════════════════════════════════════

# ── 阶段 1: 编译（Node.js 20 Alpine）──
FROM node:20-alpine AS builder

WORKDIR /app

# 依赖分层缓存
COPY package.json package-lock.json ./
RUN npm install

# 拷贝源码并构建（next.config.ts 已配置 output: 'export' → 产出 ./out/）
COPY . .
RUN npm run build

# ── 阶段 2: 托管（Nginx Alpine 超轻量）──
FROM nginx:alpine

# 静态文件 → Nginx 默认根目录
COPY --from=builder /app/out /usr/share/nginx/html

# SPA 防 404 路由表
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
