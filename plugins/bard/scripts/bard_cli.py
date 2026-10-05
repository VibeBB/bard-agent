#!/usr/bin/env python3
"""bard CLI: VibeBB Record Protocol writers and the SLP v2 liaison inbox.

All commands print one JSON object to stdout. A rejected record or response
exits 2 with ``{"status": "rejected", "reasons": [...]}``; I/O and usage
errors exit 3. ``ux-inbox`` always exits 0 — it reports malformed files in
its output instead of failing.

Python 3.12+, standard library only.

Usage::

    python3 bard_cli.py record decision --json <file|-> [--root DIR]
    python3 bard_cli.py record impression --json <file|-> [--root DIR]
    python3 bard_cli.py record vision-review --json <file|-> [--root DIR]
    python3 bard_cli.py record status [--root DIR]
    python3 bard_cli.py ux-inbox [--root DIR]
    python3 bard_cli.py ux-respond --json <file|-> [--root DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load {name} from {_SCRIPTS}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bard_records = _load("bard_records")
bard_liaison = _load("bard_liaison")


def _read_json_arg(value: str) -> Any:
    if value == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bard_cli.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="append a VRP record")
    record_sub = record.add_subparsers(dest="kind", required=True)
    for kind in ("decision", "impression", "vision-review"):
        p = record_sub.add_parser(kind)
        p.add_argument(
            "--json", required=True, help="payload JSON file or '-' for stdin"
        )
        p.add_argument("--root", type=Path, default=None, help="workspace root")
    status = record_sub.add_parser("status", help="show records summary")
    status.add_argument("--root", type=Path, default=None, help="workspace root")

    inbox_p = sub.add_parser("ux-inbox", help="list bard liaison requests")
    inbox_p.add_argument("--root", type=Path, default=None, help="workspace root")

    respond_p = sub.add_parser("ux-respond", help="write a liaison response")
    respond_p.add_argument(
        "--json", required=True, help="payload JSON file or '-' for stdin"
    )
    respond_p.add_argument("--root", type=Path, default=None, help="workspace root")

    args = parser.parse_args(argv)

    try:
        if args.command == "record":
            root = args.root.resolve() if args.root is not None else None
            if args.kind == "status":
                _emit(bard_records.records_summary(root))
                return 0
            payload = _read_json_arg(args.json)
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            _emit(bard_records.RECORDERS[args.kind](payload, root))
            return 0
        if args.command == "ux-inbox":
            root = args.root.resolve() if args.root is not None else None
            _emit(bard_liaison.inbox(root))
            return 0
        if args.command == "ux-respond":
            payload = _read_json_arg(args.json)
            if not isinstance(payload, dict):
                raise ValueError("respond payload must be a JSON object")
            root = args.root.resolve() if args.root is not None else None
            _emit(bard_liaison.respond(payload, root))
            return 0
    except (ValueError, json.JSONDecodeError) as exc:
        reasons = [str(exc)]
        _emit({"status": "rejected", "reasons": reasons})
        return 2
    except OSError as exc:
        _emit({"status": "error", "reasons": [f"io: {exc}"]})
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
