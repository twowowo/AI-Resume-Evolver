"""
物理数据库初始化脚本 —— 自动建库 + ORM 建表

运行方式:
  source .venv/Scripts/activate && python init_db.py

执行顺序:
  1. 通过 pymysql 连接 MySQL（不指定数据库），确保目标库 ai_resume_evolver 存在
  2. 通过 SQLAlchemy engine 连接目标库
  3. Base.metadata.create_all(engine) 执行 DDL 物理建表
  4. 打印每张表的列信息验证
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

import pymysql
from sqlalchemy import create_engine, inspect, text
from src.database.models import Base
from src.database.connection import DATABASE_URL


def ensure_database_exists():
    """通过 pymysql 直连 MySQL（无数据库），确保目标库存在。"""
    db_name = os.getenv("DB_NAME", "ai_resume_evolver")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "3306"))
    db_user = os.getenv("DB_USER", "root")
    db_pwd = os.getenv("DB_PASSWORD", "")

    conn = pymysql.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_pwd,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        print(f"[init] 数据库 `{db_name}` 已就绪 (不存在则自动创建)")
    finally:
        conn.close()


def create_tables():
    """通过 SQLAlchemy engine 执行 DDL 物理建表。"""
    engine = create_engine(DATABASE_URL, echo=False)

    print(f"[init] 连接目标库: {DATABASE_URL.replace(os.getenv('DB_PASSWORD', ''), '***')}")

    # 物理建表（已存在的表自动跳过）
    Base.metadata.create_all(engine)

    # 验证表结构
    inspector = inspect(engine)

    for table_name in inspector.get_table_names():
        print(f"\n{'=' * 60}")
        print(f"表: {table_name}")
        print(f"{'=' * 60}")

        # 列信息
        for col in inspector.get_columns(table_name):
            flags = []
            if col.get("primary_key"):
                flags.append("PK")
            if not col.get("nullable"):
                flags.append("NOT NULL")
            extra = " | ".join(flags) if flags else ""
            print(f"  {col['name']:20s} {str(col['type']):15s} {extra}")

        # 索引
        for idx in inspector.get_indexes(table_name):
            print(f"  INDEX: {idx['name']} -> {idx['column_names']}")

        # 唯一约束
        for uq in inspector.get_unique_constraints(table_name):
            print(f"  UNIQUE: {uq['name']} -> {uq['column_names']}")

    print(f"\n[init] 物理建表完成 — {len(inspector.get_table_names())} 张表已落盘 MySQL")


if __name__ == "__main__":
    print("=" * 60)
    print("AI-Resume-Evolver 物理数据库初始化")
    print("=" * 60)
    ensure_database_exists()
    create_tables()
    print("\n[OK] init_db 执行成功 - 长期记忆表已焊入 MySQL 物理层")
