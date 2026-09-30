import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def base_temporal(tmp_path, monkeypatch):
    """Base vacía por prueba. Con TEST_DATABASE_URL definido, las pruebas corren contra Postgres."""
    from remu import config as C
    from remu import db
    monkeypatch.setattr(C, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(C, "EXPORTS_DIR", tmp_path)
    monkeypatch.delenv("BASECON_SECRET", raising=False)
    pg = os.environ.get("TEST_DATABASE_URL")
    if pg:
        monkeypatch.setenv("DATABASE_URL", pg)
        conn = db.get_conn()
        for t in reversed(list(db.TABLAS)):
            conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        conn.commit()
        conn.close()
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    db._init_done = False
    db.init_db()
    yield tmp_path
    db._init_done = False
