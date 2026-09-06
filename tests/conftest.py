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

    # ``client=`` يضبط عنوان الطالب: افتراضه "testclient" ليس عنوان IP، وفحص
    # «الوصول من خارج الجهاز بلا رمز» في ``security.py`` يقرأه
    with TestClient(main.app, client=("127.0.0.1", 45678)) as c:
        yield c
