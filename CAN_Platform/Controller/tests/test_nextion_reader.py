import sys
import threading
from pathlib import Path


CONTROLLER_DIR = Path(__file__).resolve().parents[1]
if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))

from nextion.protocol import GraphRequest
from nextion.reader import nextion_reader_worker


class FakeSerial:
    def __init__(self, payload, stop_event):
        self.payload = bytearray(payload)
        self.stop_event = stop_event
        self.empty_reads = 0

    def read(self, size):
        if not self.payload:
            self.empty_reads += 1
            if self.empty_reads > 10:
                self.stop_event.set()
            return b""

        data = self.payload[:size]
        del self.payload[:size]
        return bytes(data)


def read_one_request(payload):
    stop_event = threading.Event()
    requests = []

    def on_request(_ser, request, _config):
        requests.append(request)
        stop_event.set()

    nextion_reader_worker(
        FakeSerial(payload, stop_event),
        {"nextion_rx_idle_flush_seconds": 0},
        stop_event=stop_event,
        on_request=on_request,
    )

    return requests


def test_reader_dispatches_pipe_terminated_graph_requests():
    requests = read_one_request(b"PARAMS:0:rpm,afr|")

    assert requests == [GraphRequest(0, ("rpm", "afr"))]


def test_reader_dispatches_nextion_ff_terminated_graph_requests():
    requests = read_one_request(b"PARAMS:1:rpm,clt\xff\xff\xff")

    assert requests == [GraphRequest(1, ("rpm", "clt"))]


def test_reader_dispatches_idle_terminated_graph_requests():
    requests = read_one_request(b"PARAMS:2:vss,tps")

    assert requests == [GraphRequest(2, ("vss", "tps"))]
