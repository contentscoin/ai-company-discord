#!/usr/bin/env python3
"""companyctl — single source-of-truth CLI for ai-company-discord.

Consumes templates/company.discord.json. Python 3 standard library only
(no `pip install`), so it runs the same on Linux, macOS, and Windows.

Phase 1 subcommands:
  validate   check company.discord.json against the schema + filesystem
  scaffold   create ~/.hermes/profiles/<name>/ from the roles in the JSON

Later roadmap phases add: bootstrap, doctor, standup, decision, lint,
digest, archive, status. See ROADMAP.md.

Secrets are never read from arguments and never printed. Runtime state
(channel maps, decision logs) lives under ~/.hermes/ai-company/, never in
this repo.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "templates" / "company.discord.json"

# Access-list tokens that are not role ids.
#   board = the human founder; exec = every role (all bots).
ACCESS_SPECIAL = {"board", "exec"}

PROFILE_ID_OK = "abcdefghijklmnopqrstuvwxyz0123456789-"
CHANNEL_NAME_OK = PROFILE_ID_OK


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Validation (hand-rolled; mirrors templates/company.schema.json + filesystem)
# --------------------------------------------------------------------------- #
def _is_id(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) > 0
        and value[0].isalpha()
        and all(c in PROFILE_ID_OK for c in value)
    )


def _is_channel_name(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) > 0
        and value[0] in (PROFILE_ID_OK.replace("-", ""))
        and all(c in CHANNEL_NAME_OK for c in value)
    )


def _looks_like_cron(value) -> bool:
    return isinstance(value, str) and len(value.split()) == 5


def validate(config: dict, repo_root: Path) -> list[str]:
    """Return a list of human-readable errors. Empty list means valid."""
    errors: list[str] = []

    def err(where: str, msg: str) -> None:
        errors.append(f"{where}: {msg}")

    # -- top level --------------------------------------------------------- #
    if not isinstance(config.get("name"), str) or not config.get("name"):
        err("name", "required non-empty string")
    version = config.get("version")
    if not isinstance(version, str) or version.count(".") != 2:
        err("version", "required string like MAJOR.MINOR.PATCH")

    # -- roles ------------------------------------------------------------- #
    roles = config.get("roles")
    role_ids: list[str] = []
    if not isinstance(roles, list) or not roles:
        err("roles", "required non-empty array")
    else:
        for i, role in enumerate(roles):
            where = f"roles[{i}]"
            if not isinstance(role, dict):
                err(where, "must be an object")
                continue
            rid = role.get("id")
            if not _is_id(rid):
                err(f"{where}.id", "required, ^[a-z][a-z0-9-]*$")
            else:
                role_ids.append(rid)
            for key in ("title", "discordBot", "runtime"):
                if not isinstance(role.get(key), str) or not role.get(key):
                    err(f"{where}.{key}", "required non-empty string")
            profile = role.get("hermesProfile")
            if not _is_id(profile):
                err(f"{where}.hermesProfile", "required, ^[a-z][a-z0-9-]*$")
            else:
                soul = repo_root / "profiles" / profile / "SOUL.md"
                if not soul.is_file():
                    err(
                        f"{where}.hermesProfile",
                        f"no SOUL.md at profiles/{profile}/SOUL.md",
                    )
            if "gjcRole" in role and not (
                role["gjcRole"] is None or isinstance(role["gjcRole"], str)
            ):
                err(f"{where}.gjcRole", "must be a string or null")

        dupes = {r for r in role_ids if role_ids.count(r) > 1}
        if dupes:
            err("roles", f"duplicate role id(s): {', '.join(sorted(dupes))}")

    # -- discord ----------------------------------------------------------- #
    discord = config.get("discord")
    if not isinstance(discord, dict):
        err("discord", "required object")
        return errors  # nothing more to check without it

    for key in ("requireMention", "autoThread"):
        if not isinstance(discord.get(key), bool):
            err(f"discord.{key}", "required boolean")

    categories = discord.get("categories")
    category_set: set[str] = set()
    if not isinstance(categories, list) or not categories:
        err("discord.categories", "required non-empty array of strings")
    else:
        for c in categories:
            if not isinstance(c, str) or not c:
                err("discord.categories", "entries must be non-empty strings")
            else:
                category_set.add(c)

    allowed_access = ACCESS_SPECIAL | set(role_ids)
    channels = discord.get("channels")
    seen_names: set[str] = set()
    if not isinstance(channels, list) or not channels:
        err("discord.channels", "required non-empty array")
    else:
        for i, ch in enumerate(channels):
            where = f"discord.channels[{i}]"
            if not isinstance(ch, dict):
                err(where, "must be an object")
                continue
            name = ch.get("name")
            if not _is_channel_name(name):
                err(f"{where}.name", "required, ^[a-z0-9][a-z0-9-]*$")
            elif name in seen_names:
                err(f"{where}.name", f"duplicate channel name: {name}")
            else:
                seen_names.add(name)
            cat = ch.get("category")
            if not isinstance(cat, str) or not cat:
                err(f"{where}.category", "required non-empty string")
            elif category_set and cat not in category_set:
                err(
                    f"{where}.category",
                    f"'{cat}' not in discord.categories",
                )
            access = ch.get("access")
            if not isinstance(access, list) or not access:
                err(f"{where}.access", "required non-empty array")
            else:
                for a in access:
                    if a not in allowed_access:
                        err(
                            f"{where}.access",
                            f"'{a}' is not 'board', 'exec', or a role id",
                        )
            if "freeResponse" in ch and not isinstance(ch["freeResponse"], bool):
                err(f"{where}.freeResponse", "must be a boolean")

    # -- meetings (optional) ---------------------------------------------- #
    meetings = config.get("meetings")
    if meetings is not None:
        if not isinstance(meetings, dict):
            err("meetings", "must be an object")
        else:
            for key in ("standupCron", "execMeetingCron"):
                if key in meetings and not _looks_like_cron(meetings[key]):
                    err(f"meetings.{key}", "must be a 5-field cron string")

    return errors


def cmd_validate(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {config_path}: {exc}", file=sys.stderr)
        return 2

    errors = validate(config, REPO_ROOT)
    if errors:
        print(f"FAIL: {config_path} ({len(errors)} error(s))")
        for e in errors:
            print(f"  - {e}")
        return 1
    role_count = len(config.get("roles", []))
    chan_count = len(config.get("discord", {}).get("channels", []))
    print(f"OK: {config_path} — {role_count} roles, {chan_count} channels")
    return 0


# --------------------------------------------------------------------------- #
# Scaffold (JSON-driven replacement for scaffold-profiles.sh)
# --------------------------------------------------------------------------- #
CEO_STANDUP_HINT = """
# CEO standup hint: to let cron post to #standup without an @mention, add the
# line below INSIDE the discord: block above. Do NOT create a second discord:
# key — a duplicate top-level mapping is a YAML error (see TROUBLESHOOTING.md).
#   free_response_channels: "STANDUP_CHANNEL_ID"
"""


def cmd_scaffold(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {config_path}: {exc}", file=sys.stderr)
        return 2

    errors = validate(config, REPO_ROOT)
    if errors:
        print("ERROR: config is invalid — run `companyctl validate` first:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    hermes_home = Path(args.hermes_home).expanduser()
    profiles_dir = hermes_home / "profiles"
    print(f"==> Hermes home: {hermes_home}")
    profiles_dir.mkdir(parents=True, exist_ok=True)

    template_config = REPO_ROOT / "templates" / "config.yaml"
    template_env = REPO_ROOT / "templates" / "env.example"

    for role in config["roles"]:
        profile = role["hermesProfile"]
        dest = profiles_dir / profile
        (dest / "skills").mkdir(parents=True, exist_ok=True)
        (dest / "memories").mkdir(parents=True, exist_ok=True)
        print(f"-- profile: {profile}")

        soul_dest = dest / "SOUL.md"
        if not soul_dest.exists():
            shutil.copyfile(REPO_ROOT / "profiles" / profile / "SOUL.md", soul_dest)
            print("   wrote SOUL.md")
        else:
            print("   keep existing SOUL.md")

        config_dest = dest / "config.yaml"
        if not config_dest.exists():
            shutil.copyfile(template_config, config_dest)
            if profile == "ceo":
                with config_dest.open("a", encoding="utf-8") as fh:
                    fh.write(CEO_STANDUP_HINT)
            print("   wrote config.yaml")
        else:
            print("   keep existing config.yaml")

        env_dest = dest / ".env"
        if not env_dest.exists():
            shutil.copyfile(template_env, env_dest)
            print("   wrote .env (fill DISCORD_BOT_TOKEN)")
        else:
            print("   keep existing .env")

    print()
    print("Next:")
    print("  1) Create Discord apps/bots and paste tokens into each .env")
    print("  2) Invite bots to your server (see SETUP.md)")
    print("  3) hermes -p ceo gateway start   # repeat for each profile")
    print("  4) Smoke-test @mentions in #exec-meeting")
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="companyctl",
        description="Single source-of-truth CLI for ai-company-discord.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="path to company.discord.json (default: templates/company.discord.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate", help="check company.discord.json against schema + filesystem"
    )
    p_validate.set_defaults(func=cmd_validate)

    p_scaffold = sub.add_parser(
        "scaffold", help="create ~/.hermes/profiles/<name>/ from the JSON roles"
    )
    p_scaffold.add_argument(
        "--hermes-home",
        default="~/.hermes",
        help="Hermes home directory (default: ~/.hermes, or $HERMES_HOME)",
    )
    p_scaffold.set_defaults(func=cmd_scaffold)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # $HERMES_HOME overrides the scaffold default unless --hermes-home was given.
    if getattr(args, "func", None) is cmd_scaffold and args.hermes_home == "~/.hermes":
        args.hermes_home = os.environ.get("HERMES_HOME", "~/.hermes")
    return args.func(args)


if __name__ == "__main__":
    try:
        rc = main()
        sys.stdout.flush()
    except BrokenPipeError:
        # A downstream reader (e.g. `| head`) closed the pipe early. Redirect
        # stdout to devnull so the interpreter's shutdown flush stays quiet.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        rc = 0
    raise SystemExit(rc)
