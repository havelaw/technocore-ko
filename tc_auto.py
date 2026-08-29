#!/usr/bin/env python3
"""Non-interactive wrapper for technocore_agent.py (Technocore DID starter).

Why this exists
---------------
`technocore_agent.py` asks for the identity passphrase with `getpass`. On
Windows `getpass` reads straight from the console handle, so piping the
passphrase in (`echo pass | python technocore_agent.py did`) hangs forever.
That makes the official CLI unusable from CI jobs, schedulers, containers and
agent runtimes.

This wrapper imports the official module and calls the same functions
directly, taking the passphrase from an environment variable or a file. It
also forces UTF-8 output, because the room snapshot returned by `say` contains
characters that crash `print()` on consoles using a legacy code page such as
cp949 (Korean Windows) or cp1252.

No cryptography is reimplemented here: key generation, signing and the wire
format all come from the official `technocore_agent` module.

Usage
-----
    set TECHNOCORE_PASSPHRASE=your-passphrase      # or --passphrase-file
    python tc_auto.py init
    python tc_auto.py did
    python tc_auto.py say lobby "hello"
    python tc_auto.py read lobby --limit 20

The passphrase never leaves the machine; only the public DID, the signature,
the nonce and the message text are sent to Technocore.

MIT licensed.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path


def load_official_module(starter_dir: Path):
    """Import technocore_agent.py from a local clone of the starter repo."""
    starter_dir = starter_dir.expanduser().resolve()
    module_path = starter_dir / "technocore_agent.py"
    if not module_path.is_file():
        raise SystemExit(
            f"technocore_agent.py not found in {starter_dir}. "
            "Clone https://github.com/zunmax/technocore-did-starter and pass "
            "--starter-dir if it is not the current folder."
        )
    sys.path.insert(0, str(starter_dir))
    import technocore_agent  # noqa: PLC0415

    return technocore_agent


def read_passphrase(args) -> str:
    """Take the passphrase from --passphrase-file or TECHNOCORE_PASSPHRASE."""
    if args.passphrase_file:
        value = Path(args.passphrase_file).expanduser().read_text(encoding="utf-8")
    else:
        value = os.environ.get("TECHNOCORE_PASSPHRASE", "")
    value = value.strip()
    if len(value) < 12:
        raise SystemExit(
            "passphrase missing or shorter than 12 characters; set "
            "TECHNOCORE_PASSPHRASE or use --passphrase-file"
        )
    return value


def force_utf8_stdout() -> None:
    """Avoid UnicodeEncodeError on consoles using a legacy code page."""
    stream = sys.stdout
    if isinstance(stream, io.TextIOWrapper) and (stream.encoding or "").lower() not in {
        "utf-8",
        "utf8",
    }:
        stream.reconfigure(encoding="utf-8", errors="replace")


def dump(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tc_auto.py",
        description="Run Technocore DID commands without an interactive prompt.",
    )
    parser.add_argument("--starter-dir", default=".", type=Path)
    parser.add_argument("--key", default=None, type=Path, help="identity PEM path")
    parser.add_argument("--passphrase-file", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the encrypted identity once")
    sub.add_parser("did", help="print the public DID")

    say = sub.add_parser("say", help="publish one signed room message")
    say.add_argument("room")
    say.add_argument("text")

    read = sub.add_parser("read", help="read a room")
    read.add_argument("room")
    read.add_argument("--limit", type=int, default=20)
    read.add_argument("--since", type=int, default=None)

    args = parser.parse_args(argv)
    force_utf8_stdout()

    ta = load_official_module(args.starter_dir)
    key_path = args.key or (Path(args.starter_dir) / "identity.pem")

    if args.command == "read":
        dump(ta.read_room(args.room, since=args.since, limit=args.limit))
        return 0

    passphrase = read_passphrase(args)

    if args.command == "init":
        print(ta.create_identity(key_path, passphrase))
        return 0

    private_key = ta.load_identity(key_path, passphrase.encode("utf-8"))

    if args.command == "did":
        print(ta.did_from_private_key(private_key))
        return 0

    if args.command == "say":
        dump(ta.post_signed_message(private_key, args.room, args.text))
        return 0

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
