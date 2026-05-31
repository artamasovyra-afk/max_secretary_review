#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PATH = REPO_ROOT / "backend"
for import_path in (BACKEND_PATH, REPO_ROOT):
    if import_path.exists() and str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from app.core.config import get_settings  # noqa: E402
from app.modules.integrations.max.bot_commands import (  # noqa: E402
    default_max_bot_commands,
)
from app.modules.integrations.max.client import MaxApiClient  # noqa: E402
from app.modules.integrations.max.exceptions import MaxApiError  # noqa: E402


def build_default_commands_payload() -> dict[str, object]:
    return {"commands": default_max_bot_commands()}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register MAX bot commands for the native slash popup.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print sanitized payload without calling MAX API.")
    mode.add_argument("--apply", action="store_true", help="Patch current MAX bot profile commands.")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override MAX API base URL. Defaults to MAX_API_BASE_URL from environment.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    apply_changes = bool(args.apply)
    commands = default_max_bot_commands()
    payload = {"commands": commands}

    print("MAX bot command registration")
    print(f"mode={'apply' if apply_changes else 'dry-run'}")
    print("command_name_format=without_slash")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not apply_changes:
        print("dry_run=ok")
        print("max_api_called=no")
        return 0

    settings = get_settings()
    try:
        with MaxApiClient(settings=settings, base_url=args.base_url) as client:
            result = client.patch_bot_commands(commands)
    except MaxApiError as exc:
        print(f"apply=failed:{exc.__class__.__name__}", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print("apply=ok")
    print("max_api_called=yes")
    print(f"response_keys={_response_keys(result)}")
    return 0


def _response_keys(result: dict[str, Any]) -> str:
    if not result:
        return "-"
    return ",".join(sorted(result.keys()))


if __name__ == "__main__":
    raise SystemExit(main())
