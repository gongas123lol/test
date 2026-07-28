import importlib.util
import logging
import sys
import types
from pathlib import Path


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))

if "serial" not in sys.modules and importlib.util.find_spec("serial") is None:
    sys.modules["serial"] = types.ModuleType("serial")

from nextion.thread import format_sessions_text, update_nextion


class FakeSerial:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


class BrokenSerial:
    def write(self, data):
        raise OSError("serial write failed")


class FakeSession:
    def __init__(self, id, description):
        self.id = id
        self.description = description


def build_test_data():
    return {
        "rpm": 3120,
        "afr": 14.68,
        "clt": 86,
        "advance": 22.54,
        "map": 123.4,
        "baro": 101.3,
        "tps": 42.2,
        "iat": 31,
        "ego_correction": 100,
        "pulse_width": 4.2,
        "ve": 73,
        "dwell": 3.4,
        "battery_voltage": 13.8,
        "boost_target": 150.0,
        "boost_duty": 55.0,
        "sync": 1,
        "engine_status": 1,
        "fan": True,
        "fp": True,
        "boost_cut": False,
        "vss": 58,
    }


def test_format_sessions_text_uses_display_indices_and_sanitizes_names():
    text = format_sessions_text([
        FakeSession(10, 'Track "A"'),
        FakeSession(9, None),
    ])

    assert text == "0: Track 'A'\r\n1: Session 9"


def test_update_nextion_sends_expected_hardcoded_fields():
    ser = FakeSerial()

    ok = update_nextion(ser, build_test_data(), 9000, 7000)

    assert ok is True
    assert ser.writes == [
        b'rpm.txt="3120"',
        b"\xff\xff\xff",
        b'afr.txt="AFR: 14.7 AFR"',
        b"\xff\xff\xff",
        b'clt.txt="CLT: 86 C"',
        b"\xff\xff\xff",
        b'adv.txt="ADV: 22.5 deg"',
        b"\xff\xff\xff",
        b'map.txt="MAP: 123.4 kPa"',
        b"\xff\xff\xff",
        b'baro.txt="BARO: 101.3 kPa"',
        b"\xff\xff\xff",
        b'tps.txt="TPS: 42.2 %"',
        b"\xff\xff\xff",
        b'iat.txt="IAT: 31 C"',
        b"\xff\xff\xff",
        b'ego.txt="EGO: 100 %"',
        b"\xff\xff\xff",
        b'pw.txt="PW: 4.20 ms"',
        b"\xff\xff\xff",
        b've.txt="VE: 73 %"',
        b"\xff\xff\xff",
        b'dwell.txt="DWELL: 3.4 ms"',
        b"\xff\xff\xff",
        b'bat.txt="BAT: 13.8 V"',
        b"\xff\xff\xff",
        b'boost.txt="BOOST: 150.0 kPa"',
        b"\xff\xff\xff",
        b'duty.txt="DUTY: 55 %"',
        b"\xff\xff\xff",
        b'sync.txt="SYNC: 1"',
        b"\xff\xff\xff",
        b'engine.txt="ENGINE: 1"',
        b"\xff\xff\xff",
        b'fan.txt="FAN: 1"',
        b"\xff\xff\xff",
        b'fp.txt="FP: 1"',
        b"\xff\xff\xff",
        b'boostcut.txt="BOOSTCUT: 0"',
        b"\xff\xff\xff",
        b'rpmgauge.val="34"',
        b"\xff\xff\xff",
        b"cltgauge.val=43",
        b"\xff\xff\xff",
        b"afrgauge.val=46",
        b"\xff\xff\xff",
        b'vss.txt="VSS: 58 km/h"',
        b"\xff\xff\xff",
        b'shiftlight.pco="0"',
        b"\xff\xff\xff",
    ]


def test_update_nextion_only_sends_changed_commands_when_cache_is_used():
    ser = FakeSerial()
    data = build_test_data()
    last_commands = {}

    ok = update_nextion(ser, data, 9000, 7000, last_commands)

    assert ok is True
    assert len(ser.writes) == 50

    ser.writes.clear()
    ok = update_nextion(ser, data, 9000, 7000, last_commands)

    assert ok is True
    assert ser.writes == []

    data["rpm"] = 7200
    ok = update_nextion(ser, data, 9000, 7000, last_commands)

    assert ok is True
    assert ser.writes == [
        b'rpm.txt="7200"',
        b"\xff\xff\xff",
        b'rpmgauge.val="80"',
        b"\xff\xff\xff",
        b'shiftlight.pco="6400"',
        b"\xff\xff\xff",
    ]


def test_update_nextion_reports_serial_write_failure():
    logging.disable(logging.CRITICAL)
    try:
        ok = update_nextion(BrokenSerial(), {
            "rpm": 3120,
            "afr": 14.68,
            "clt": 86,
            "advance": 22.54,
            "vss": 58,
        }, 9000, 7000)
    finally:
        logging.disable(logging.NOTSET)

    assert ok is False
