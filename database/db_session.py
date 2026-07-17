# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/database/db_session.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from .models import Base
# 显式导入 user_models 以便 Base.metadata 包含 sys_user 表
from . import user_models  # noqa: F401
import config
from config.db_config import mysql_db_config, sqlite_db_config, postgres_db_config

# Keep a cache of engines
_engines = {}


async def create_database_if_not_exists(db_type: str):
    if db_type == "mysql" or db_type == "db":
        # Connect to the server without a database
        server_url = f"mysql+asyncmy://{mysql_db_config['user']}:{mysql_db_config['password']}@{mysql_db_config['host']}:{mysql_db_config['port']}"
        engine = create_async_engine(server_url, echo=False)
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {mysql_db_config['db_name']}"))
        await engine.dispose()
    elif db_type == "postgres":
        # Connect to the default 'postgres' database
        server_url = f"postgresql+asyncpg://{postgres_db_config['user']}:{postgres_db_config['password']}@{postgres_db_config['host']}:{postgres_db_config['port']}/postgres"
        print(f"[init_db] Connecting to Postgres: host={postgres_db_config['host']}, port={postgres_db_config['port']}, user={postgres_db_config['user']}, dbname=postgres")
        # Isolation level AUTOCOMMIT is required for CREATE DATABASE
        engine = create_async_engine(server_url, echo=False, isolation_level="AUTOCOMMIT")
        async with engine.connect() as conn:
            # Check if database exists
            result = await conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname = '{postgres_db_config['db_name']}'"))
            if not result.scalar():
                await conn.execute(text(f"CREATE DATABASE {postgres_db_config['db_name']}"))
        await engine.dispose()


def get_async_engine(db_type: str = None):
    if db_type is None:
        db_type = config.SAVE_DATA_OPTION

    if db_type in _engines:
        return _engines[db_type]

    if db_type in ["json", "jsonl", "csv"]:
        return None

    if db_type == "sqlite":
        db_url = f"sqlite+aiosqlite:///{sqlite_db_config['db_path']}"
    elif db_type == "mysql" or db_type == "db":
        db_url = f"mysql+asyncmy://{mysql_db_config['user']}:{mysql_db_config['password']}@{mysql_db_config['host']}:{mysql_db_config['port']}/{mysql_db_config['db_name']}"
    elif db_type == "postgres":
        db_url = f"postgresql+asyncpg://{postgres_db_config['user']}:{postgres_db_config['password']}@{postgres_db_config['host']}:{postgres_db_config['port']}/{postgres_db_config['db_name']}"
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

    engine = create_async_engine(db_url, echo=False)
    _engines[db_type] = engine
    return engine


async def create_tables(db_type: str = None):
    if db_type is None:
        db_type = config.SAVE_DATA_OPTION
    await create_database_if_not_exists(db_type)
    engine = get_async_engine(db_type)
    if engine:
        async with engine.begin() as conn:
            # 只创建不存在的表，不删除已有数据
            await conn.run_sync(Base.metadata.create_all)
        # 给已有业务表补充 owner_user_id 字段(数据隔离)
        await _migrate_owner_user_id(engine, db_type)
        # 人工明确确认的评论允许对同一目标发布不同文本；内容哈希幂等键仍防止重复提交。
        await _migrate_x_publish_job_constraints(engine, db_type)


async def _migrate_owner_user_id(engine, db_type: str):
    """为业务表补充 owner_user_id 字段(IF NOT EXISTS)。

    支持 PostgreSQL / SQLite / MySQL。
    SQLAlchemy 的 create_all 不会修改已存在表结构,需要手动 ALTER。
    """
    tables = [
        "crawler_task",
        "customer_lead",
        "outreach_record",
        "outreach_task",
        "auto_outreach_job",
    ]
    if db_type == "postgres":
        async with engine.begin() as conn:
            for t in tables:
                await conn.execute(
                    text(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(64) DEFAULT '' ")
                )
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{t}_owner_user_id ON {t} (owner_user_id)"))
            await conn.execute(
                text(
                    "ALTER TABLE crawler_task "
                    "ADD COLUMN IF NOT EXISTS schedule_interval_seconds INTEGER DEFAULT 900"
                )
            )
    elif db_type == "sqlite":
        async with engine.begin() as conn:
            for t in tables:
                try:
                    await conn.execute(text(f"ALTER TABLE {t} ADD COLUMN owner_user_id VARCHAR(64) DEFAULT ''"))
                except Exception:
                    pass  # 字段已存在
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE crawler_task "
                        "ADD COLUMN schedule_interval_seconds INTEGER DEFAULT 900"
                    )
                )
            except Exception:
                pass
    elif db_type in ("mysql", "db"):
        async with engine.begin() as conn:
            for t in tables:
                # MySQL 不支持 IF NOT EXISTS for ADD COLUMN(8.0+ 部分支持),用 try 包裹
                try:
                    await conn.execute(text(f"ALTER TABLE {t} ADD COLUMN owner_user_id VARCHAR(64) DEFAULT ''"))
                    await conn.execute(text(f"CREATE INDEX ix_{t}_owner_user_id ON {t} (owner_user_id)"))
                except Exception:
                    pass
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE crawler_task "
                        "ADD COLUMN schedule_interval_seconds INTEGER DEFAULT 900"
                    )
                )
            except Exception:
                pass


async def _migrate_x_publish_job_constraints(engine, db_type: str):
    """移除旧的“目标帖子 + 发布模式”唯一限制，改为普通查询索引。

    `owner_user_id + idempotency_key` 唯一约束仍保留，因此同一人工评论文本
    的重复点击仍是幂等请求；不同文本可各自生成独立、可审计的发布任务。
    """
    constraint_name = "uq_x_publish_jobs_owner_account_target_mode"
    index_name = "ix_x_publish_jobs_owner_account_target_mode"
    index_columns = "owner_user_id, account_id, target_post_id, publish_mode"

    if db_type == "postgres":
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"ALTER TABLE x_publish_jobs "
                    f"DROP CONSTRAINT IF EXISTS {constraint_name}"
                )
            )
            await conn.execute(
                text(
                    "UPDATE x_publish_jobs SET interaction_id = NULL "
                    "WHERE publish_mode = 'manual_review' AND interaction_id IS NOT NULL"
                )
            )
            await conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON x_publish_jobs ({index_columns})"
                )
            )
    elif db_type in ("mysql", "db"):
        async with engine.begin() as conn:
            try:
                await conn.execute(
                    text(f"ALTER TABLE x_publish_jobs DROP INDEX {constraint_name}")
                )
            except Exception:
                pass
            await conn.execute(
                text(
                    "UPDATE x_publish_jobs SET interaction_id = NULL "
                    "WHERE publish_mode = 'manual_review' AND interaction_id IS NOT NULL"
                )
            )
            try:
                await conn.execute(
                    text(
                        f"CREATE INDEX {index_name} "
                        f"ON x_publish_jobs ({index_columns})"
                    )
                )
            except Exception:
                pass
    # SQLite 新建数据库会直接使用模型中的普通索引。SQLite 无法直接删除
    # UniqueConstraint 生成的 autoindex；旧 SQLite 数据库需由正式迁移工具重建表。


@asynccontextmanager
async def get_session() -> AsyncSession:
    engine = get_async_engine(config.SAVE_DATA_OPTION)
    if not engine:
        yield None
        return
    AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        await session.close()
