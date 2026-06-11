"""
SQLAlchemy 同步引擎 + 会话工厂 — MySQL 持久化连接池

配置来源: .env (DATABASE_URL / DB_* 参数)
驱动: pymysql (同步, 兼容 agent_tools.py 同步调用栈)

用法:
  from src.database.connection import get_session
  with get_session() as session:
      session.add(obj)
      session.commit()
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 确保 .env 已加载（模块级副作用，与 main.py 启动逻辑对齐）
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

# ── 连接字符串构造 ──
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # fallback: 从离散参数拼接
    db_user = os.getenv("DB_USER", "root")
    db_pwd = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "ai_resume_evolver")
    db_charset = os.getenv("DB_CHARSET", "utf8mb4")
    DATABASE_URL = (
        f"mysql+pymysql://{db_user}:{db_pwd}@{db_host}:{db_port}"
        f"/{db_name}?charset={db_charset}"
    )

# ── 同步引擎（对齐 agent_tools 同步调用链路）──
engine: Engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,          # 连接回收前 ping 检测存活
    pool_recycle=3600,           # 1 小时强制回收
)

# ── 会话工厂 ──
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_session() -> Session:
    """
    获取一个同步数据库会话（上下文管理器风格）。

    示例:
        with get_session() as session:
            user = session.query(UserResume).filter_by(user_id="xxx").first()
    """
    return SessionLocal()
