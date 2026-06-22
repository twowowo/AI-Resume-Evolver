"""
SQLAlchemy 同步引擎 + 会话工厂 — MySQL / SQLite 双模持久化

配置来源: .env (DATABASE_URL / DB_* 参数)
驱动: pymysql (MySQL) / sqlite3 (SQLite 降级)

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

# ── 连接字符串构造（模块级，仅拼接 URL，不建立 TCP 连接）──
DATABASE_URL = os.getenv("DATABASE_URL")
_SQLITE_FALLBACK = False

if not DATABASE_URL:
    db_host = os.getenv("DB_HOST", "localhost")

    if not db_host:
        # DB_HOST 为空 → 自动降级为 SQLite（无需 MySQL）
        _sqlite_path = (
            Path(__file__).resolve().parent.parent.parent
            / "data" / "auth.db"
        )
        _sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        DATABASE_URL = f"sqlite:///{_sqlite_path}"
        _SQLITE_FALLBACK = True
    else:
        # DB_HOST 有值 → 拼装 MySQL URL
        db_user = os.getenv("DB_USER", "root")
        db_pwd = os.getenv("DB_PASSWORD", "")
        db_port = os.getenv("DB_PORT", "3306")
        db_name = os.getenv("DB_NAME", "ai_resume_evolver")
        db_charset = os.getenv("DB_CHARSET", "utf8mb4")
        DATABASE_URL = (
            f"mysql+pymysql://{db_user}:{db_pwd}@{db_host}:{db_port}"
            f"/{db_name}?charset={db_charset}"
        )

# ── 惰性引擎：首次调用 _get_engine() 或 get_session() 时才创建连接池 ──
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    """惰性创建并返回 SQLAlchemy 同步引擎（首次调用时初始化连接池）。"""
    global _engine
    if _engine is None:
        _engine_kwargs = {
            "echo": os.getenv("DB_ECHO", "false").lower() == "true",
        }
        if _SQLITE_FALLBACK:
            # SQLite 模式：禁掉 MySQL 专属参数
            _engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # MySQL 模式：连接池配置
            _engine_kwargs.update({
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            })
        _engine = create_engine(DATABASE_URL, **_engine_kwargs)
    return _engine


def _get_session_local() -> sessionmaker[Session]:
    """惰性创建并返回 SessionLocal 工厂。"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


def get_session() -> Session:
    """
    获取一个同步数据库会话（上下文管理器风格）。

    示例:
        with get_session() as session:
            user = session.query(UserResume).filter_by(user_id="xxx").first()
    """
    return _get_session_local()()
