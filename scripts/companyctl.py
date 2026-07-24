#!/usr/bin/env python3
"""companyctl — single source-of-truth CLI for ai-company-discord.

Consumes templates/company.discord.json. Python 3 standard library only
(no `pip install`), so it runs the same on Linux, macOS, and Windows.

Subcommands:
  validate    check company.discord.json against the schema + filesystem
  scaffold    create ~/.hermes/profiles/<name>/ from the roles in the JSON
  bootstrap   create Discord roles/categories/channels from the JSON (idempotent)
  doctor      health-check profiles, tokens, and config for drift
  standup     post (or preview) the daily standup message to #standup

Later roadmap phases add: decision, lint, digest, archive, status. See ROADMAP.md.

Secrets are never read from arguments and never printed. Runtime state
(channel maps, decision logs) lives under ~/.hermes/ai-company/, never in
this repo.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "templates" / "company.discord.json"

# Access-list tokens that are not role ids.
#   board = the human founder; exec = every role (all bots).
ACCESS_SPECIAL = {"board", "exec"}

PROFILE_ID_OK = "abcdefghijklmnopqrstuvwxyz0123456789-"
CHANNEL_NAME_OK = PROFILE_ID_OK
ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"

# Discord REST -------------------------------------------------------------- #
DISCORD_API = "https://discord.com/api/v10"
CH_TEXT = 0
CH_CATEGORY = 4
OW_ROLE = 0
# Server roles bootstrap manages (matches CHANNELS.md tiers).
SERVER_ROLES = ["Board", "Exec", "Observer"]

# Permission bits (Discord API string-encoded bitfield).
VIEW_CHANNEL = 1 << 10
SEND_MESSAGES = 1 << 11
ADD_REACTIONS = 1 << 6
READ_MESSAGE_HISTORY = 1 << 16
CREATE_PUBLIC_THREADS = 1 << 34
SEND_MESSAGES_IN_THREADS = 1 << 38
PARTICIPANT_ALLOW = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | ADD_REACTIONS
    | READ_MESSAGE_HISTORY
    | CREATE_PUBLIC_THREADS
    | SEND_MESSAGES_IN_THREADS
)


class DiscordError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Loading / paths
# --------------------------------------------------------------------------- #
def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def resolve_hermes_home(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "hermes_home", None)
    raw = explicit or os.environ.get("HERMES_HOME", "~/.hermes")
    return Path(raw).expanduser()


def state_dir(hermes_home: Path) -> Path:
    return hermes_home / "ai-company"


def map_path(hermes_home: Path) -> Path:
    return state_dir(hermes_home) / "discord.map.json"


def read_env_value(env_path: Path, key: str) -> str | None:
    """Return the value of KEY=... from a .env file, or None. Never logged."""
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return None


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
        and value[0] in ALNUM
        and all(c in CHANNEL_NAME_OK for c in value)
    )


def _looks_like_cron(value) -> bool:
    return isinstance(value, str) and len(value.split()) == 5


def validate(config: dict, repo_root: Path) -> list[str]:
    """Return a list of human-readable errors. Empty list means valid."""
    errors: list[str] = []

    def err(where: str, msg: str) -> None:
        errors.append(f"{where}: {msg}")

    if not isinstance(config.get("name"), str) or not config.get("name"):
        err("name", "required non-empty string")
    version = config.get("version")
    if not isinstance(version, str) or version.count(".") != 2:
        err("version", "required string like MAJOR.MINOR.PATCH")

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

    discord = config.get("discord")
    if not isinstance(discord, dict):
        err("discord", "required object")
        return errors

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
                err(f"{where}.category", f"'{cat}' not in discord.categories")
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

    meetings = config.get("meetings")
    if meetings is not None:
        if not isinstance(meetings, dict):
            err("meetings", "must be an object")
        else:
            for key in ("standupCron", "execMeetingCron"):
                if key in meetings and not _looks_like_cron(meetings[key]):
                    err(f"meetings.{key}", "must be a 5-field cron string")

    return errors


def load_valid_config(config_path: Path) -> dict:
    """Load + validate, or raise SystemExit with a clear message."""
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        raise SystemExit(f"ERROR: config not found: {config_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid JSON in {config_path}: {exc}")
    errors = validate(config, REPO_ROOT)
    if errors:
        lines = "\n".join(f"  - {e}" for e in errors)
        raise SystemExit(
            f"ERROR: {config_path} is invalid — run `companyctl validate`:\n{lines}"
        )
    return config


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
    config = load_valid_config(Path(args.config))

    hermes_home = resolve_hermes_home(args)
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
    print("  2) companyctl bootstrap --guild <id>   # create channels/roles")
    print("  3) hermes -p ceo gateway start   # repeat for each profile")
    print("  4) companyctl doctor              # health-check")
    return 0


# --------------------------------------------------------------------------- #
# Discord REST (network; isolated from the pure planners above)
# --------------------------------------------------------------------------- #
def discord_request(method: str, path: str, token: str, payload=None, _retries=3):
    url = DISCORD_API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "companyctl (ai-company-discord)")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and _retries > 0:
            retry_after = float(exc.headers.get("Retry-After", "1"))
            time.sleep(min(retry_after, 10))
            return discord_request(method, path, token, payload, _retries - 1)
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise DiscordError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DiscordError(f"{method} {path} -> {exc.reason}") from exc


# --------------------------------------------------------------------------- #
# Bootstrap (pure planner + apply)
# --------------------------------------------------------------------------- #
def compute_bootstrap_plan(
    config: dict, existing_role_names: set[str], existing_channels: list[dict]
) -> dict:
    """Pure. Decide what to create; never delete. Match by exact name."""
    discord = config["discord"]

    roles_to_create = [r for r in SERVER_ROLES if r not in existing_role_names]

    existing_cats = {c["name"] for c in existing_channels if c.get("type") == CH_CATEGORY}
    categories_to_create = [c for c in discord["categories"] if c not in existing_cats]

    existing_text = {c["name"] for c in existing_channels if c.get("type") == CH_TEXT}
    channels_to_create = [
        {"name": ch["name"], "category": ch["category"]}
        for ch in discord["channels"]
        if ch["name"] not in existing_text
    ]

    # Channels whose declared access is narrower than the Exec tier that
    # bootstrap can enforce with server-wide roles. Surfaced as a note so the
    # operator knows what to tighten manually (needs per-bot member overwrites).
    narrower = [
        {"name": ch["name"], "access": ch["access"]}
        for ch in discord["channels"]
        if "exec" not in set(ch["access"]) and (set(ch["access"]) - {"board"})
    ]

    return {
        "roles_to_create": roles_to_create,
        "categories_to_create": categories_to_create,
        "channels_to_create": channels_to_create,
        "narrower_access": narrower,
    }


def _category_overwrites(category: str, guild_id: str, role_ids: dict) -> list[dict]:
    overwrites = [
        {"id": str(guild_id), "type": OW_ROLE, "deny": str(VIEW_CHANNEL)},
        {"id": role_ids["Board"], "type": OW_ROLE, "allow": str(PARTICIPANT_ALLOW)},
    ]
    if category != "board":
        overwrites.append(
            {"id": role_ids["Exec"], "type": OW_ROLE, "allow": str(PARTICIPANT_ALLOW)}
        )
    return overwrites


def cmd_bootstrap(args: argparse.Namespace) -> int:
    config = load_valid_config(Path(args.config))
    token = os.environ.get("DISCORD_SETUP_TOKEN")
    if not token:
        print("ERROR: set DISCORD_SETUP_TOKEN (bot token) in the environment.", file=sys.stderr)
        return 2
    guild = args.guild or os.environ.get("DISCORD_GUILD_ID")
    if not guild:
        print("ERROR: pass --guild <id> or set DISCORD_GUILD_ID.", file=sys.stderr)
        return 2

    try:
        roles = discord_request("GET", f"/guilds/{guild}/roles", token)
        channels = discord_request("GET", f"/guilds/{guild}/channels", token)
    except DiscordError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    existing_role_names = {r["name"] for r in roles}
    plan = compute_bootstrap_plan(config, existing_role_names, channels)

    print(f"Guild: {guild}")
    print(f"  roles to create      : {plan['roles_to_create'] or '(none)'}")
    print(f"  categories to create : {plan['categories_to_create'] or '(none)'}")
    print(f"  channels to create   : {[c['name'] for c in plan['channels_to_create']] or '(none)'}")
    if plan["narrower_access"]:
        print("  note: these channels declare access narrower than the Exec tier;")
        print("        tighten with per-bot member overwrites after bots join:")
        for n in plan["narrower_access"]:
            print(f"          #{n['name']} -> {n['access']}")

    total = (
        len(plan["roles_to_create"])
        + len(plan["categories_to_create"])
        + len(plan["channels_to_create"])
    )
    if not args.apply:
        print(f"\n(dry-run) {total} change(s). Re-run with --apply to create them.")
        return 0
    if total == 0:
        print("\n0 changes — already in sync.")
        return 0

    # Apply: roles, then categories, then channels.
    role_ids = {r["name"]: str(r["id"]) for r in roles}
    for name in plan["roles_to_create"]:
        created = discord_request("POST", f"/guilds/{guild}/roles", token, {"name": name})
        role_ids[name] = str(created["id"])
        print(f"  + role {name}")

    cat_ids = {c["name"]: str(c["id"]) for c in channels if c.get("type") == CH_CATEGORY}
    for name in plan["categories_to_create"]:
        created = discord_request(
            "POST",
            f"/guilds/{guild}/channels",
            token,
            {
                "name": name,
                "type": CH_CATEGORY,
                "permission_overwrites": _category_overwrites(name, guild, role_ids),
            },
        )
        cat_ids[name] = str(created["id"])
        print(f"  + category {name}")

    chan_ids = {c["name"]: str(c["id"]) for c in channels if c.get("type") == CH_TEXT}
    for ch in plan["channels_to_create"]:
        created = discord_request(
            "POST",
            f"/guilds/{guild}/channels",
            token,
            {"name": ch["name"], "type": CH_TEXT, "parent_id": cat_ids[ch["category"]]},
        )
        chan_ids[ch["name"]] = str(created["id"])
        print(f"  + channel #{ch['name']}")

    hermes_home = resolve_hermes_home(args)
    state_dir(hermes_home).mkdir(parents=True, exist_ok=True)
    mp = map_path(hermes_home)
    mp.write_text(
        json.dumps(
            {
                "guildId": str(guild),
                "roles": {k: role_ids[k] for k in SERVER_ROLES if k in role_ids},
                "categories": cat_ids,
                "channels": chan_ids,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote channel map: {mp}")
    return 0


# --------------------------------------------------------------------------- #
# Doctor
# --------------------------------------------------------------------------- #
def count_top_level_key(config_yaml_text: str, key: str) -> int:
    prefix = f"{key}:"
    return sum(1 for line in config_yaml_text.splitlines() if line.startswith(prefix))


def doctor_offline(config: dict, hermes_home: Path) -> list[tuple[str, str]]:
    """Return (level, message) rows. level in {PASS, WARN, FAIL}."""
    rows: list[tuple[str, str]] = []
    profiles_dir = hermes_home / "profiles"
    token_owners: dict[str, list[str]] = {}

    for role in config["roles"]:
        profile = role["hermesProfile"]
        pdir = profiles_dir / profile
        if not pdir.is_dir():
            rows.append(("WARN", f"{profile}: not scaffolded (run `companyctl scaffold`)"))
            continue
        for fname in ("SOUL.md", "config.yaml", ".env"):
            if not (pdir / fname).is_file():
                rows.append(("FAIL", f"{profile}: missing {fname}"))

        cfg_file = pdir / "config.yaml"
        if cfg_file.is_file():
            dupes = count_top_level_key(cfg_file.read_text(encoding="utf-8"), "discord")
            if dupes > 1:
                rows.append(("FAIL", f"{profile}: duplicate top-level `discord:` key in config.yaml"))

        token = read_env_value(pdir / ".env", "DISCORD_BOT_TOKEN")
        if not token:
            rows.append(("WARN", f"{profile}: DISCORD_BOT_TOKEN is empty"))
        else:
            digest = hashlib.sha256(token.encode()).hexdigest()
            token_owners.setdefault(digest, []).append(profile)

    for owners in token_owners.values():
        if len(owners) > 1:
            rows.append(
                ("FAIL", f"shared DISCORD_BOT_TOKEN across profiles: {', '.join(sorted(owners))}")
            )

    rows.append(
        ("WARN", "Message Content Intent cannot be verified via API — confirm it is ON in the Developer Portal")
    )
    return rows


def doctor_online(config: dict, hermes_home: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    profiles_dir = hermes_home / "profiles"
    for role in config["roles"]:
        profile = role["hermesProfile"]
        token = read_env_value(profiles_dir / profile / ".env", "DISCORD_BOT_TOKEN")
        if not token:
            continue
        try:
            me = discord_request("GET", "/users/@me", token)
            rows.append(("PASS", f"{profile}: token valid (bot {me.get('username')})"))
        except DiscordError as exc:
            rows.append(("FAIL", f"{profile}: token check failed — {exc}"))

    mp = map_path(hermes_home)
    if mp.is_file():
        setup_token = os.environ.get("DISCORD_SETUP_TOKEN")
        data = json.loads(mp.read_text(encoding="utf-8"))
        if setup_token and data.get("guildId"):
            try:
                live = discord_request("GET", f"/guilds/{data['guildId']}/channels", setup_token)
                live_names = {c["name"] for c in live}
                for name in data.get("channels", {}):
                    if name not in live_names:
                        rows.append(("FAIL", f"channel #{name} in map but not in guild (drift)"))
            except DiscordError as exc:
                rows.append(("WARN", f"channel drift check skipped — {exc}"))
    return rows


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_valid_config(Path(args.config))
    hermes_home = resolve_hermes_home(args)

    rows = doctor_offline(config, hermes_home)
    if args.online:
        rows += doctor_online(config, hermes_home)

    worst = 0
    for level, msg in rows:
        print(f"  {level:4} {msg}")
        if level == "FAIL":
            worst = 1
    summary = "FAIL" if worst else "OK"
    print(f"\n{summary}: {sum(1 for l, _ in rows if l == 'FAIL')} fail, "
          f"{sum(1 for l, _ in rows if l == 'WARN')} warn")
    return worst


# --------------------------------------------------------------------------- #
# Standup
# --------------------------------------------------------------------------- #
def render_standup(date_iso: str, mention_roles: list[str]) -> str:
    mentions = " ".join(f"@{r}" for r in mention_roles)
    return (
        f"Daily standup — {date_iso}\n"
        f"각 본부장: 어제 / 오늘 / 블로커 (각 1줄)\n"
        f"{mentions}"
    )


def cmd_standup(args: argparse.Namespace) -> int:
    config = load_valid_config(Path(args.config))
    hermes_home = resolve_hermes_home(args)

    today = datetime.date.today().isoformat()
    # Default mentions: the non-CEO working leads (CTO/Loop/Growth), by title-ish id.
    mention_roles = [r["id"].upper() for r in config["roles"] if r["id"] in {"cto", "loop", "growth"}]
    body = render_standup(today, mention_roles)

    if args.dry_run:
        print("(dry-run) would post to #standup:\n")
        print(body)
        return 0

    mp = map_path(hermes_home)
    if not mp.is_file():
        print(f"ERROR: no channel map at {mp} — run `companyctl bootstrap` first.", file=sys.stderr)
        return 2
    data = json.loads(mp.read_text(encoding="utf-8"))
    channel_id = data.get("channels", {}).get("standup")
    if not channel_id:
        print("ERROR: #standup not found in channel map.", file=sys.stderr)
        return 2

    token = os.environ.get("DISCORD_STANDUP_TOKEN") or read_env_value(
        hermes_home / "profiles" / "ceo" / ".env", "DISCORD_BOT_TOKEN"
    )
    if not token:
        print("ERROR: no CEO token (set DISCORD_STANDUP_TOKEN or fill ceo/.env).", file=sys.stderr)
        return 2
    try:
        discord_request("POST", f"/channels/{channel_id}/messages", token, {"content": body})
    except DiscordError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"Posted standup to #standup ({channel_id}).")
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def _add_hermes_home(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--hermes-home",
        default=None,
        help="Hermes home directory (default: $HERMES_HOME or ~/.hermes)",
    )


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

    sub.add_parser("validate", help="check company.discord.json").set_defaults(func=cmd_validate)

    p_scaffold = sub.add_parser("scaffold", help="create ~/.hermes/profiles/<name>/ from the JSON")
    _add_hermes_home(p_scaffold)
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_boot = sub.add_parser("bootstrap", help="create Discord roles/categories/channels (idempotent)")
    p_boot.add_argument("--guild", help="Discord guild (server) id, or set DISCORD_GUILD_ID")
    p_boot.add_argument("--apply", action="store_true", help="apply changes (default: dry-run)")
    _add_hermes_home(p_boot)
    p_boot.set_defaults(func=cmd_bootstrap)

    p_doc = sub.add_parser("doctor", help="health-check profiles, tokens, and config")
    p_doc.add_argument("--online", action="store_true", help="also check tokens/channels via Discord")
    _add_hermes_home(p_doc)
    p_doc.set_defaults(func=cmd_doctor)

    p_stand = sub.add_parser("standup", help="post or preview the daily standup message")
    p_stand.add_argument("action", choices=["post"], help="what to do")
    p_stand.add_argument("--dry-run", action="store_true", help="print the message instead of posting")
    _add_hermes_home(p_stand)
    p_stand.set_defaults(func=cmd_standup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
