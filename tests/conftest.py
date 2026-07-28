"""تهيئة مشتركة للاختبارات."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """قاعدة بيانات معزولة لكل اختبار."""
    import backend.db as db

    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return db


@pytest.fixture
def client(temp_db, monkeypatch):
    """TestClient مع DB معزولة وبلا مصادقة."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("API_TOKEN", raising=False)
    import backend.main as main

    with TestClient(main.app) as c:
        yield c
