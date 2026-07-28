import math
import sqlite3
import time
from contextlib import closing

from nextion.graph_test_data import generate_graph_rows
from repository import StateRepo
from repository.database import database_manager


MOCK_PREFIX = "[MOCK]"

MOCK_SESSION_PROFILES = (
    {
        "name": "Sprint pull",
        "rpm_scale": 1.00,
        "rpm_offset": 0,
        "vss_scale": 1.00,
        "afr_shift": -0.1,
        "clt_offset": 0,
        "tps_scale": 1.00,
    },
    {
        "name": "Autocross laps",
        "rpm_scale": 0.86,
        "rpm_offset": 450,
        "vss_scale": 0.72,
        "afr_shift": 0.2,
        "clt_offset": 7,
        "tps_scale": 1.12,
    },
    {
        "name": "Heat soak",
        "rpm_scale": 0.56,
        "rpm_offset": 700,
        "vss_scale": 0.38,
        "afr_shift": 0.4,
        "clt_offset": 18,
        "tps_scale": 0.62,
    },
    {
        "name": "Cruise",
        "rpm_scale": 0.42,
        "rpm_offset": 1800,
        "vss_scale": 0.82,
        "afr_shift": 0.6,
        "clt_offset": 4,
        "tps_scale": 0.46,
    },
    {
        "name": "Boost check",
        "rpm_scale": 0.94,
        "rpm_offset": 200,
        "vss_scale": 0.88,
        "afr_shift": -0.3,
        "clt_offset": 10,
        "tps_scale": 1.20,
    },
)


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _setup_database(db_path):
    original_db_path = database_manager.DB_PATH

    try:
        database_manager.DB_PATH = db_path
        database_manager.database_setup()
    finally:
        database_manager.DB_PATH = original_db_path


def _delete_existing_mock_sessions(cursor):
    cursor.execute(
        "SELECT id FROM sessions WHERE description LIKE ?",
        (f"{MOCK_PREFIX}%",),
    )
    session_ids = [row[0] for row in cursor.fetchall()]

    if not session_ids:
        return 0

    placeholders = ", ".join("?" for _ in session_ids)

    cursor.execute(
        f"""
        DELETE FROM signals
        WHERE frame_id IN (
            SELECT id FROM can_frames WHERE session_id IN ({placeholders})
        )
        """,
        session_ids,
    )
    cursor.execute(
        f"DELETE FROM vehicle_state WHERE session_id IN ({placeholders})",
        session_ids,
    )
    cursor.execute(
        f"DELETE FROM can_frames WHERE session_id IN ({placeholders})",
        session_ids,
    )
    cursor.execute(
        f"DELETE FROM sessions WHERE id IN ({placeholders})",
        session_ids,
    )

    return len(session_ids)


def build_mock_vehicle_rows(
    profile_index=0,
    samples=180,
    interval_seconds=0.25,
    start_timestamp=0.0,
):
    profile = MOCK_SESSION_PROFILES[profile_index % len(MOCK_SESSION_PROFILES)]
    base_rows = generate_graph_rows(
        samples=samples,
        interval_seconds=interval_seconds,
        start_timestamp=start_timestamp,
    )
    rows = []
    denominator = max(samples - 1, 1)

    for index, row in enumerate(base_rows):
        progress = index / denominator
        wobble = math.sin(progress * math.pi * (profile_index + 2))
        throttle_bump = max(0.0, math.sin(progress * math.pi * (2 + profile_index)))

        rpm = clamp(
            row["rpm"] * profile["rpm_scale"] + profile["rpm_offset"] + wobble * 180,
            700,
            7600,
        )
        tps = clamp(row["tps"] * profile["tps_scale"] + throttle_bump * 8, 0, 100)
        clt = clamp(row["clt"] + profile["clt_offset"] + progress * profile_index, 60, 118)
        iat = clamp(row["iat"] + profile["clt_offset"] * 0.35 + progress * 4, 15, 85)
        boost_duty = clamp(row["boost_duty"] * profile["tps_scale"], 0, 100)
        boost_target = clamp(95 + row["boost_target"] * profile["tps_scale"] * 0.65, 0, 250)

        shaped = {
            **row,
            "rpm": round(rpm),
            "afr": round(clamp(row["afr"] + profile["afr_shift"], 10, 20), 2),
            "clt": round(clt, 1),
            "iat": round(iat, 1),
            "tps": round(tps, 1),
            "map": round(clamp(30 + tps * 1.75, 0, 250), 1),
            "advance": round(clamp(34 - tps * 0.22 + wobble * 3, -20, 60), 1),
            "pulse_width": round(clamp(2.0 + tps * 0.105, 0, 20), 2),
            "battery_voltage": round(13.7 + 0.18 * math.sin(index / 8), 2),
            "boost_target": round(boost_target, 1),
            "boost_duty": round(boost_duty, 1),
            "vss": round(clamp(row["vss"] * profile["vss_scale"], 0, 250), 1),
            "ego_correction": round(clamp(100 + wobble * 6, 80, 125), 1),
            "ve": round(clamp(62 + tps * 0.34, 0, 100), 1),
            "dwell": round(clamp(2.8 + rpm / 2800, 0, 8), 2),
            "sync": 1,
            "engine_status": 1,
            "fan": int(clt >= 92),
            "fp": 1,
            "boost_cut": int(boost_target > 215 and boost_duty > 85),
        }
        rows.append(shaped)

    return rows


def _state_values(session_id, row):
    state = {
        "session_id": session_id,
        "rpm": row.get("rpm", 0),
        "sync": row.get("sync", 1),
        "engine_status": row.get("engine_status", 1),
        "map": row.get("map", 0),
        "baro": row.get("baro", 101.3),
        "tps": row.get("tps", 0),
        "iat": row.get("iat", 0),
        "clt": row.get("clt", 0),
        "afr": row.get("afr", 14.7),
        "ego_correction": row.get("ego_correction", 100),
        "pulse_width": row.get("pulse_width", 0),
        "ve": row.get("ve", 0),
        "advance": row.get("advance", 0),
        "dwell": row.get("dwell", 0),
        "battery_voltage": row.get("battery_voltage", 13.8),
        "boost_target": row.get("boost_target", 0),
        "boost_duty": row.get("boost_duty", 0),
        "vss": row.get("vss", 0),
        "fan": int(row.get("fan", 0)),
        "fp": int(row.get("fp", 1)),
        "boost_cut": int(row.get("boost_cut", 0)),
    }

    return tuple(state[column] for column in StateRepo.STATE_COLUMNS)


def seed_mock_sessions(
    session_count=5,
    samples_per_session=180,
    interval_seconds=0.25,
    spacing_seconds=600,
    replace=True,
    db_path=None,
):
    if session_count < 0:
        raise ValueError("session_count must be zero or greater")
    if samples_per_session < 0:
        raise ValueError("samples_per_session must be zero or greater")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")
    if spacing_seconds < 0:
        raise ValueError("spacing_seconds must be zero or greater")

    db_path = str(db_path or database_manager.DB_PATH)
    _setup_database(db_path)

    inserted_sessions = []
    state_columns = ", ".join(StateRepo.STATE_COLUMNS)
    state_placeholders = ", ".join("?" for _ in StateRepo.STATE_COLUMNS)
    now = time.time()

    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()
        removed_sessions = _delete_existing_mock_sessions(cursor) if replace else 0

        for display_index in range(session_count):
            profile = MOCK_SESSION_PROFILES[
                display_index % len(MOCK_SESSION_PROFILES)
            ]
            start_time = now - display_index * spacing_seconds
            description = f"{MOCK_PREFIX} {display_index}: {profile['name']}"

            cursor.execute(
                """
                INSERT INTO sessions (start_time, end_time, description)
                VALUES (?, ?, ?)
                """,
                (
                    start_time,
                    start_time + max(samples_per_session - 1, 0) * interval_seconds,
                    description,
                ),
            )
            session_id = cursor.lastrowid

            rows = build_mock_vehicle_rows(
                profile_index=display_index,
                samples=samples_per_session,
                interval_seconds=interval_seconds,
                start_timestamp=start_time,
            )

            for row in rows:
                cursor.execute(
                    f"""
                    INSERT INTO vehicle_state (timestamp, {state_columns})
                    VALUES (?, {state_placeholders})
                    """,
                    (row["timestamp"], *_state_values(session_id, row)),
                )

            inserted_sessions.append({
                "display_index": display_index,
                "id": session_id,
                "description": description,
                "samples": len(rows),
            })

        conn.commit()

    return {
        "db_path": db_path,
        "removed_sessions": removed_sessions,
        "sessions": inserted_sessions,
    }
