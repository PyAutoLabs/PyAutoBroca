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
    setup = sub.add_parser("setup", help="preview or resume empty local instance setup")
    setup.add_argument("--repos", type=Path, required=True)
    setup.add_argument("--repo", required=True, help="canonical repository key")
    setup.add_argument("--pages-url", required=True)
    setup.add_argument("--brain", type=Path, required=True)
    setup.add_argument("--apply", action="store_true")
    publication = sub.add_parser("publication", help="prepare a static Pages bundle")
    publication.add_argument("--repos", type=Path, required=True)
    publication.add_argument("--repo", required=True)
    publication.add_argument("--pages-url", required=True)
    publication.add_argument("--brain", type=Path, required=True)
    publication.add_argument("--output", type=Path, required=True)
    publication.add_argument("--branch", default="main")
    publication.add_argument("--apply", action="store_true")
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
    board.add_argument("--state-output", type=Path, help="also write the shared organ feed")
    board.add_argument("--repository", help="canonical owner/repository from the publishing context")
    board.add_argument("--pages-url", help="override the configured public board directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            from .setup import prepare, apply
            prepared = prepare(args.root, args.repos, args.repo, args.pages_url, args.brain)
            missing = apply(prepared) if args.apply else prepared[2]
            print(("Created: " if args.apply else "Would create: ") + (", ".join(missing) or "nothing"))
            print("Local setup only; publication and Scientist connection remain separate.")
            return 0
        if args.command == "publication":
            from .publication import prepare, apply
            prepared = prepare(args.root, args.repos, args.repo, args.pages_url,
                               args.brain, args.output, args.branch)
            if args.apply:
                apply(prepared)
            print(("Created: " if args.apply else "Would create: ") + str(prepared[0]))
            print("\n".join(prepared[1]))
            print("Review rendered content before publishing; no remote changes made.")
            return 0
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
            state = None
            if args.state_output:
                if args.state_output.resolve() == args.output.resolve():
                    raise ValueError("HTML and state output paths must differ")
                from .state import build
                state = build(args.root, args.brain, args.repository, args.pages_url)
            page = render(args.root, args.brain, repository=args.repository or "PyAutoLabs/PyAutoBroca")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(page)
            if state is not None:
                args.state_output.parent.mkdir(parents=True, exist_ok=True)
                args.state_output.write_text(json.dumps(state, indent=2) + "\n")
            print(args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Broca: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
