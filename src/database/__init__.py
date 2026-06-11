"""
src.database — AI-Resume-Evolver 双层存储持久化层

表模型:
  - UserResume  — 简历四章节微创手术持久化 (basic / skills / projects / campus)
  - UserProfile — 用户求职意图长期记忆画像 (key-value Upsert 模型)

引擎初始化由 src/database/engine.py 后续提供（SQLite 本地开发 / MySQL 生产切换）。
"""
