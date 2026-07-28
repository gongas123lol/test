import serial
import threading
import time
import logging
from extra.signal_cache import signal_cache
from extra.logging_setup import configure_logging
from nextion.reader import start_nextion_reader
from nextion.writer import nextion_writer
from repository import SessionRepo

LOG_PATH = configure_logging()
logger = logging.getLogger(__name__)


def send_cmd(ser, cmd):
    return nextion_writer.write(ser, cmd)


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def _sanitize_nextion_text(value):
    return str(value).replace('"', "'").replace("\n", " ").replace("\r", " ")


def format_sessions_text(sessions):
    lines = []

    for index, session in enumerate(sessions):
        description = session.description or f"Session {session.id}"
        lines.append(f"{index}: {_sanitize_nextion_text(description)}")

    return "\r\n".join(lines)


def update_sessions_list(ser, limit=5):
    sessions = SessionRepo.get_recent_sessions(limit)
    text = format_sessions_text(sessions)
    return send_cmd(ser, f'sessions.txt="{text}"')


def build_nextion_commands(data, max_rpm, shift_point):
    rpm_percent = int((data["rpm"] / max_rpm) * 100)
    clt = data["clt"]
    clt_gauge = clamp(int(((clt - 60) / 60) * 100))
    afr_gauge = clamp(int(((float(data["afr"]) - 10) / 10) * 100))
    shiftlight_color = 6400 if int(data["rpm"]) > shift_point else 0

    return {
        "rpm": f'rpm.txt="{int(data["rpm"])}"',
        "afr": f'afr.txt="AFR: {data["afr"]:.1f} AFR"',
        "clt": f'clt.txt="CLT: {int(data["clt"])} C"',
        "adv": f'adv.txt="ADV: {data["advance"]:.1f} deg"',
        "map": f'map.txt="MAP: {data["map"]:.1f} kPa"',
        "baro": f'baro.txt="BARO: {data["baro"]:.1f} kPa"',
        "tps": f'tps.txt="TPS: {data["tps"]:.1f} %"',
        "iat": f'iat.txt="IAT: {int(data["iat"])} C"',
        "ego": f'ego.txt="EGO: {data["ego_correction"]:.0f} %"',
        "pw": f'pw.txt="PW: {data["pulse_width"]:.2f} ms"',
        "ve": f've.txt="VE: {int(data["ve"])} %"',
        "dwell": f'dwell.txt="DWELL: {data["dwell"]:.1f} ms"',
        "bat": f'bat.txt="BAT: {data["battery_voltage"]:.1f} V"',
        "boost": f'boost.txt="BOOST: {data["boost_target"]:.1f} kPa"',
        "duty": f'duty.txt="DUTY: {data["boost_duty"]:.0f} %"',
        "sync": f'sync.txt="SYNC: {int(data["sync"])}"',
        "engine": f'engine.txt="ENGINE: {int(data["engine_status"])}"',
        "fan": f'fan.txt="FAN: {int(data["fan"])}"',
        "fp": f'fp.txt="FP: {int(data["fp"])}"',
        "boostcut": f'boostcut.txt="BOOSTCUT: {int(data["boost_cut"])}"',
        "rpmgauge": f'rpmgauge.val="{rpm_percent}"',
        "cltgauge": f'cltgauge.val={clt_gauge}',
        "afrgauge": f'afrgauge.val={afr_gauge}',
        "vss": f'vss.txt="VSS: {int(data["vss"])} km/h"',
        "shiftlight": f'shiftlight.pco="{shiftlight_color}"',
    }


def get_changed_commands(commands, last_commands):
    changed_commands = {}

    for name, command in commands.items():
        if last_commands.get(name) != command:
            changed_commands[name] = command

    return changed_commands


def send_commands(ser, commands):
    return nextion_writer.write_batch(ser, commands.values())


def update_nextion(ser, data, max_rpm, shift_point, last_commands=None):
    try:
        commands = build_nextion_commands(data, max_rpm, shift_point)

        if last_commands is None:
            commands_to_send = commands
        else:
            commands_to_send = get_changed_commands(commands, last_commands)

        bytes_written, commands_sent = send_commands(ser, commands_to_send)

        if last_commands is not None:
            last_commands.update(commands_to_send)

        logger.info(
            "sent to nextion: version=%s decoded=%s commands=%s/%s bytes=%s "
            "rpm=%s afr=%.1f clt=%s advance=%.1f map=%.1f tps=%.1f vss=%s",
            data.get("_version"),
            data.get("decoded"),
            commands_sent,
            len(commands),
            bytes_written,
            int(data["rpm"]),
            float(data["afr"]),
            int(data["clt"]),
            float(data["advance"]),
            float(data["map"]),
            float(data["tps"]),
            int(data["vss"]),
        )

        return True

    except Exception as exc:

        logger.exception("NEXTION UPDATE ERROR: %s", exc)
        return False


def nextion_worker(config):
    try:
        ser = serial.Serial(
            port=config["nextion_port"],
            baudrate=config.get("nextion_baud", 115200),
            timeout=float(config.get("nextion_read_timeout", 0.05))
        )

        time.sleep(2)

        logger.info(
            "Nextion connected on %s @ %s is_open=%s",
            ser.port,
            ser.baudrate,
            ser.is_open,
        )
        start_nextion_reader(ser, config)

    except Exception as exc:

        logger.exception("SERIAL INIT ERROR: %s", exc)
        return

    last_version = None
    last_commands = {}
    last_sessions_update = 0
    sessions_interval = float(config.get("nextion_sessions_interval", 1.0))
    sessions_limit = int(config.get("nextion_sessions_limit", 5))

    while True:

        try:

            data = signal_cache.get_all()
            version = data.get("_version")
            now = time.time()

            if version != last_version:

                if update_nextion(
                    ser,
                    data,
                    config["redline"],
                    config["shift_point"],
                    last_commands,
                ):
                    last_version = version

            if now - last_sessions_update >= sessions_interval:
                update_sessions_list(ser, sessions_limit)
                last_sessions_update = now

            time.sleep(0.1)

        except Exception as exc:

            logger.exception("NEXTION ERROR: %s", exc)

            time.sleep(1)


def start_nextion(config):

    thread = threading.Thread(
        target=nextion_worker,
        args=(config,),
        daemon=True,
        name="NextionThread"
    )

    thread.start()

    logger.info("Nextion thread started")

    return thread
