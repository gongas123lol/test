import sys
from pathlib import Path


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))

from nextion.protocol import parse_nextion_message


def test_parse_graph_params_message_normalizes_aliases():
    request = parse_nextion_message(b"PARAMS:4:vss,afr,adv,pw,|")

    assert request.session_index == 4
    assert request.signals == ("vss", "afr", "advance", "pulse_width")


def test_parse_graph_params_message_accepts_missing_pipe_terminator():
    request = parse_nextion_message(b"PARAMS:1:rpm,afr,clt")

    assert request.session_index == 1
    assert request.signals == ("rpm", "afr", "clt")


def test_parse_non_params_message_is_ignored():
    assert parse_nextion_message(b"\x01\xff\xff\xff") is None


def test_parse_new_session_message():
    request = parse_nextion_message(b"NEW_SESSION|")

    assert request.__class__.__name__ == "NewSessionRequest"
