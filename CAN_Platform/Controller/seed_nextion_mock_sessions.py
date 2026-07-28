import argparse

from nextion.graph_test_data import DEFAULT_TEST_SIGNALS
from nextion.mock_sessions import seed_mock_sessions


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Seed ecu_data.db with deterministic mock sessions for the Nextion "
            "graph controls."
        )
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=5,
        help="Number of mock sessions to create. Default: 5.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=180,
        help="Vehicle-state samples per session. Default: 180.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25,
        help="Seconds between mock samples. Default: 0.25.",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=600,
        help="Seconds between mock session start times. Default: 600.",
    )
    parser.add_argument(
        "--keep-existing-mocks",
        action="store_true",
        help="Do not delete previous [MOCK] sessions before inserting new ones.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite DB path. Default: ecu_data.db from the current directory.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    result = seed_mock_sessions(
        session_count=args.sessions,
        samples_per_session=args.samples,
        interval_seconds=args.interval,
        spacing_seconds=args.spacing,
        replace=not args.keep_existing_mocks,
        db_path=args.db,
    )

    print(f"DB: {result['db_path']}")
    print(f"Removed old mock sessions: {result['removed_sessions']}")
    print("Created mock sessions for Nextion display indices:")

    for session in result["sessions"]:
        print(
            f"  {session['display_index']}: id={session['id']} "
            f"samples={session['samples']} {session['description']}"
        )

    default_signals = ",".join(DEFAULT_TEST_SIGNALS)
    print()
    print("Example Nextion graph request messages:")
    print(f"  PARAMS:0:{default_signals}|")
    print("  PARAMS:1:rpm,afr,clt|")
    print("  PARAMS:2:vss,tps,map|")


if __name__ == "__main__":
    main()
