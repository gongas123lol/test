import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))

from nextion.graph_requests import build_graph_payload
from nextion.mock_sessions import MOCK_PREFIX, seed_mock_sessions
from nextion.protocol import GraphRequest
from repository import SessionRepo, StateRepo
from repository.database import database_manager


@contextmanager
def isolated_database():
    temp_dir = tempfile.TemporaryDirectory()
    db_path = str(Path(temp_dir.name) / "ecu_data_mock_test.db")
    original_paths = {
        database_manager: database_manager.DB_PATH,
        SessionRepo: SessionRepo.DB_PATH,
        StateRepo: StateRepo.DB_PATH,
    }

    try:
        for module in original_paths:
            module.DB_PATH = db_path

        database_manager.database_setup()
        yield db_path
    finally:
        for module, path in original_paths.items():
            module.DB_PATH = path

        temp_dir.cleanup()


def count_rows(db_path, table_name):
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()
        return cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def test_seed_mock_sessions_creates_recent_sessions_and_vehicle_rows():
    with isolated_database() as db_path:
        result = seed_mock_sessions(
            session_count=3,
            samples_per_session=12,
            db_path=db_path,
        )
        sessions = SessionRepo.get_recent_sessions(3)

        assert result["removed_sessions"] == 0
        assert count_rows(db_path, "sessions") == 3
        assert count_rows(db_path, "vehicle_state") == 36
        assert [session.description for session in sessions] == [
            f"{MOCK_PREFIX} Session 0",
            f"{MOCK_PREFIX} Session 1",
            f"{MOCK_PREFIX} Session 2",
        ]


def test_seed_mock_sessions_replaces_only_previous_mock_sessions():
    with isolated_database() as db_path:
        real_session = SessionRepo.create_session("real session")

        first = seed_mock_sessions(
            session_count=2,
            samples_per_session=4,
            db_path=db_path,
        )
        second = seed_mock_sessions(
            session_count=1,
            samples_per_session=5,
            db_path=db_path,
        )

        sessions = SessionRepo.get_all_sessions()

        assert first["removed_sessions"] == 0
        assert second["removed_sessions"] == 2
        assert count_rows(db_path, "sessions") == 2
        assert count_rows(db_path, "vehicle_state") == 5
        assert any(session.id == real_session.id for session in sessions)
        assert any(session.description == f"{MOCK_PREFIX} Session 0" for session in sessions)


def test_nextion_graph_payload_uses_mock_session_display_index_and_signals():
    with isolated_database() as db_path:
        seed_mock_sessions(
            session_count=2,
            samples_per_session=9,
            db_path=db_path,
        )

        payload = build_graph_payload(GraphRequest(1, ("rpm", "afr", "clt")))

        assert payload["session"].description == f"{MOCK_PREFIX} Session 1"
        assert len(payload["rows"]) == 9
        assert set(payload["rows"][0]) == {"timestamp", "rpm", "afr", "clt"}
