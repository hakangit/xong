from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

# Must set before app imports cache DATABASE_URL
TEST_DB = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://localhost/xong_test",
)
os.environ["DATABASE_URL"] = TEST_DB
os.environ["DEV_USER"] = "testuser"
if "XONG_PLUGINS" not in os.environ:
    os.environ["XONG_PLUGINS"] = "files,org,assistant,mcp,a2a"
os.environ.setdefault("XONG_ROUTER_BASE", "https://router.example")

from xong.config import get_database_url, get_dev_user  # noqa: E402
from xong.db import reset_engine  # noqa: E402

get_database_url.cache_clear()
get_dev_user.cache_clear()
reset_engine()


ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def _wipe_public_schema(url: str) -> None:
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_db() -> Generator[str, None, None]:
    """Build schema via alembic upgrade head — not create_all."""
    _wipe_public_schema(TEST_DB)
    command.upgrade(_alembic_config(), "head")
    yield TEST_DB


@pytest.fixture(scope="session")
def app_client(migrated_db: str) -> Generator[TestClient, None, None]:
    get_database_url.cache_clear()
    get_dev_user.cache_clear()
    reset_engine()
    from xong.app import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(migrated_db: str, app_client: TestClient) -> Generator[TestClient, None, None]:
    engine = create_engine(migrated_db)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE binding_events, column_fingerprints, column_bindings, "
                "managed_files, logical_fields, "
                "decision_traces, skill_usage_events, "
                "teaching_sessions, skill_edges, "
                "skill_aliases, skill_claims, skills, org_people, "
                "attachments, events, focus, tasks, lists, api_keys, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()

    get_database_url.cache_clear()
    get_dev_user.cache_clear()
    reset_engine()
    yield app_client
