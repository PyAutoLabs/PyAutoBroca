"""Local commands: no implicit compute submission or publication."""
import argparse
import json
from pathlib import Path
import sys

from .collect import config, load_snapshot, refresh, check_receipts
from .records import ingest, load_records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Broca data checkout")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    add = sub.add_parser("ingest")
    add.add_argument("record", type=Path)
    collect = sub.add_parser("refresh")
    collect.add_argument("--workspace", type=Path, required=True)
    collect.add_argument("--mind", type=Path, required=True)
    collect.add_argument("--import-history", action="store_true")
    collect.add_argument("--pilot", action="store_true", help="record a cheap committed-file inventory, not an LLM benchmark")
    board = sub.add_parser("render")
    board.add_argument("--brain", type=Path, required=True)
    board.add_argument("--output", type=Path, default=Path("dashboard.html"))
    args = parser.parse_args(argv)
    try:
        names = config(args.root)["assistants"]
        if args.command == "check":
            records = load_records(args.root, names)
            check_receipts(args.root)
            load_snapshot(args.root)
            print(f"Valid: {len(names)} assistants, {len(records)} records")
        elif args.command == "ingest":
            changed = ingest(args.root, json.loads(args.record.read_text()), names)
            print("Imported" if changed else "Already recorded")
        elif args.command == "refresh":
            result = refresh(args.root, args.workspace, args.mind, import_history=args.import_history, pilot=args.pilot)
            for row in result["assistants"]:
                print(f'{row["assistant"]}: {row["status"]}; {len(row["errors"])} collection/import errors')
            return 0 if result["refreshed_at"] else 1
        else:
            from .board import render
            page = render(args.root, args.brain)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(page)
            print(args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Broca: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
