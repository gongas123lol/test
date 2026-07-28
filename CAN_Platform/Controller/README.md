# CAN Platform Controller

Controller em Python para ler dados da ECU, guardar frames CAN em SQLite e
mostrar os valores num ecrã Nextion ou na interface PyQt.

O arranque é feito em `main.py`:

1. lê o `config.json`;
2. cria as tabelas da base de dados;
3. arranca o producer (`rusefi_can` ou `speeduino_arduino`);
4. atualiza o `signal_cache` com os últimos valores;
5. arranca o modo de saída (`nextion` ou `pi_screen`).

Ficheiros principais:

| Path | Uso |
| --- | --- |
| `main.py` | Arranque da aplicação. |
| `Producer/thread.py` | Leitura CAN/serial e tradução dos dados da ECU. |
| `extra/signal_cache.py` | Guarda o último estado recebido. |
| `nextion/thread.py` | Envia valores para o Nextion. |
| `UI/App.py` | Dashboard PyQt. |
| `repository/` | Acesso à base de dados SQLite. |
| `rusefi.dbc` | DBC usada para descodificar as frames rusefi. |
| `init.sh` | Script de arranque no Raspberry Pi. |

## Configuration

The controller is configured with `config.json`.

There are two independent configuration concepts:

- `type`: where ECU data comes from.
- `mode`: where decoded state is sent/displayed.

### Producer Types

#### `rusefi_can`

Reads CAN frames through a GVRET-compatible serial adapter, decodes them with a
DBC file, saves raw CAN frames, maps decoded signals into vehicle state, and
saves periodic state snapshots.

Example:

```json
{
  "type": "rusefi_can",
  "mode": "nextion",
  "com": "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_58:E6:C5:10:77:9C-if00",
  "baud_rate": 2000000,
  "dbc": "./rusefi.dbc",
  "session_description": "CAN acquisition",
  "state_save_interval": 1.0,
  "log_can_activity": true,
  "can_log_interval": 5.0,
  "nextion_port": "/dev/serial0",
  "nextion_baud": 115200
}
```

Fields:

| Field | Required | Description |
| --- | --- | --- |
| `type` | Yes | Must be `rusefi_can`. |
| `com` | Yes | Serial device for the GVRET/CAN adapter. Prefer `/dev/serial/by-id/...` on Raspberry Pi. |
| `baud_rate` | Yes | Serial baud rate for the CAN adapter. |
| `dbc` | Yes | Path to the DBC file. Relative paths are resolved from the controller directory. |
| `session_description` | No | Description stored in the `sessions` table. |
| `state_save_interval` | No | Seconds between periodic vehicle state DB snapshots. Default: `1.0`. |
| `log_can_activity` | No | Enables periodic CAN activity summaries in the service log. Default: `true`. |
| `can_log_interval` | No | Seconds between CAN activity log summaries. Default: `5.0`. |

#### `speeduino_arduino`

Reads Speeduino serial data directly and parses the 114-byte response.

Example:

```json
{
  "type": "speeduino_arduino",
  "mode": "pi_screen",
  "port": "/dev/ttyUSB0",
  "baudrate": 115200,
  "command": "A"
}
```

Fields:

| Field | Required | Description |
| --- | --- | --- |
| `type` | Yes | Must be `speeduino_arduino`. |
| `port` | Yes | Serial device for the Speeduino connection. |
| `baudrate` | Yes | Serial baud rate. |
| `command` | No | Command sent before reading the 114-byte payload. Default: `A`. |

## Output Modes

### `nextion`

Starts `nextion/thread.py`. The Nextion worker reads the latest values from
`signal_cache` and sends them to the display over serial.

Required fields:

| Field | Description |
| --- | --- |
| `mode` | Must be `nextion`. |
| `nextion_port` | Serial device, usually `/dev/serial0` on Raspberry Pi UART. |
| `nextion_baud` | Nextion baud rate. |

Example:

```json
{
  "mode": "nextion",
  "nextion_port": "/dev/serial0",
  "nextion_baud": 115200
}
```

### `pi_screen`

Starts the PyQt dashboard in `UI/App.py`. The dashboard reads the latest values
from `signal_cache` on a Qt timer.

Required fields:

| Field | Description |
| --- | --- |
| `mode` | Must be `pi_screen`. |

This mode requires `PyQt5` and a graphical environment. In `nextion` mode,
`PyQt5` is not imported.

## Rusefi CAN

No modo `rusefi_can`, as frames GVRET são descodificadas com `rusefi.dbc`.
Depois disso, `Producer/thread.py` copia os sinais das mensagens `BASE0`,
`BASE1`, `BASE2`, `BASE3`, `BASE4`, `BASE5` e `BASE7` para o estado usado pela
UI, Nextion e base de dados.

Se for preciso adicionar outro valor ao estado, é preciso alterar:

- `update_rusefi_state()` em `Producer/thread.py`;
- a tabela `vehicle_state` em `database_manager.py`;
- o insert em `StateRepo.py`.

## Database

SQLite database file:

```text
ecu_data.db
```

Tables:

| Table | Purpose |
| --- | --- |
| `sessions` | One acquisition session per controller run. |
| `can_frames` | Raw CAN frames. |
| `signals` | Optional decoded signal storage from older controller flow. |
| `vehicle_state` | Periodic normalized vehicle state snapshots. |

### `vehicle_state` Schema

The `vehicle_state` table includes a timestamp:

```sql
CREATE TABLE IF NOT EXISTS vehicle_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    rpm INTEGER,
    sync INTEGER,
    engine_status INTEGER,
    map REAL,
    baro REAL,
    tps REAL,
    iat REAL,
    clt REAL,
    afr REAL,
    ego_correction REAL,
    pulse_width REAL,
    ve REAL,
    advance REAL,
    dwell REAL,
    battery_voltage REAL,
    boost_target REAL,
    boost_duty REAL,
    vss REAL,
    fan INTEGER,
    fp INTEGER,
    boost_cut INTEGER
)
```

`timestamp` is generated with `time.time()`, so it is a Unix timestamp in
seconds with decimal precision.

## Raspberry Pi Startup

`init.sh` is intended to be called by a systemd service on the Raspberry Pi.

Before using it:

```bash
cd /home/goncalo/Desktop/Data-Analysis-and-Acquisition-of-Distributed-Vehicular-Systems/CAN_Platform/Controller
chmod +x init.sh
```

The script:

1. Changes into the controller directory.
2. Creates a virtual environment if needed.
3. Installs runtime dependencies on first setup.
4. Waits for the configured CAN serial device.
5. Waits for the Nextion serial device when `mode` is `nextion`.
6. Starts `main.py`.

Recommended systemd service shape:

```ini
[Unit]
Description=CAN Platform Controller
After=network.target dev-serial0.device

[Service]
Type=simple
User=goncalo
WorkingDirectory=/home/goncalo/Desktop/Data-Analysis-and-Acquisition-of-Distributed-Vehicular-Systems/CAN_Platform/Controller
ExecStart=/home/goncalo/Desktop/Data-Analysis-and-Acquisition-of-Distributed-Vehicular-Systems/CAN_Platform/Controller/init.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Useful service commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable can-controller.service
sudo systemctl restart can-controller.service
sudo systemctl status can-controller.service
journalctl -u can-controller.service -b -n 100 --no-pager
```

If serial access fails:

```bash
sudo usermod -aG dialout goncalo
sudo reboot
```

## Running Manually

From the controller directory:

```bash
./init.sh
```

Or, if dependencies already exist:

```bash
source venv/bin/activate
python main.py
```

## Tests

The automatic tests live in `tests/` and use plain Python functions with
`assert`, without a test framework.

```bash
python tests/run_tests.py
```

These tests do not need real CAN hardware. They cover:

- valores iniciais do `SignalCache`, aliases, `_version` e formato usado pelo
  BLE/mobile;
- CAN-to-database emulation with a temporary SQLite database;
- GVRET parsing of decoded, unknown, and short CAN frames.

Hardware CAN print test:

```bash
python tests/integration/test_can.py
```

This requires the real CAN serial adapter and `rusefi.dbc`.

Nextion test:

```bash
python tests/integration/test_nextion.py
```

This requires the real Nextion serial connection. It sends a short manual
sequence of fixed values to the `rpm`, `afr`, `clt`, `adv`, and `vss` fields,
so the display can be checked visually. Optional port and baud arguments:

```bash
python tests/integration/test_nextion.py /dev/serial0 115200
```

Synthetic Nextion graph test:

```bash
chmod +x run_nextion_graph_test.sh
./run_nextion_graph_test.sh
```

The script reads `nextion_port`, `nextion_baud`, and `redline` from
`config.json`. Test-specific values remain in the test itself: by default it
generates 120 samples for RPM, AFR, and coolant temperature and uses a 10 ms
delay between display commands. It draws the resulting curves on the Nextion
`graph` page. Stop the controller service before running the test so that both
processes do not write to the same serial port. Test values can also be
overridden from the command line:

```bash
./run_nextion_graph_test.sh --port /dev/serial0 --baud 115200 \
  --samples 240 --signals rpm,afr,clt --redline 7500
```

Mock sessions for the real Nextion controls:

```bash
python seed_nextion_mock_sessions.py --sessions 5 --samples 180
```

This creates deterministic `[MOCK]` sessions in `ecu_data.db`, displayed on
the Nextion as `Session 0`, `Session 1`, etc. Each session includes
vehicle-state rows for RPM, AFR, CLT, TPS, VSS, MAP, boost and the remaining
dashboard fields. Re-running the command replaces only previous `[MOCK]`
sessions and keeps real acquisition sessions.

After seeding, use the normal Nextion graph controls. The display index shown
in the `sessions` field maps to `PARAMS:<index>:<signals>|`; examples:

```text
PARAMS:0:rpm,afr,clt,tps,vss|
PARAMS:1:rpm,afr,clt|
PARAMS:2:vss,tps,map|
```

## Troubleshooting

Check whether configured devices exist:

```bash
ls -l /dev/serial/by-id/
ls -l /dev/serial0
```

Check recent service logs:

```bash
journalctl -u can-controller.service -b -n 100 --no-pager
```

Common issues:

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Service starts before CAN adapter exists | USB serial not ready at boot | `init.sh` waits for the configured `com` path. Prefer `/dev/serial/by-id/...`. |
| `Permission denied` opening serial | User missing serial permissions | Add user to `dialout` and reboot. |
| `No module named cantools` | Virtualenv not created or dependency install failed | Remove `venv` and rerun `./init.sh`. |
| `PyQt5` import error in Nextion mode | Old code imported UI at startup | Current `main.py` imports PyQt only for `pi_screen`. |
| DBC file not found | Relative path resolved from wrong directory | Current `main.py` resolves `dbc` relative to the controller directory. |
| No `vehicle_state` rows | CAN frames are not decoded | Check whether the CAN IDs match the DBC and read `logs/controller.log`. |
