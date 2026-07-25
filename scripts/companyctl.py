#!/usr/bin/env python3
"""companyctl — single source-of-truth CLI for ai-company-discord.

Consumes templates/company.discord.json. Python 3 standard library only
(no `pip install`).

Portability is NOT uniform, despite being stdlib-only. The config and protocol
commands (validate/scaffold/bootstrap/doctor/standup/decision/lint/digest/
archive/status) run on Linux, macOS, and Windows. The gateway lifecycle
(up/down/restart/logs/service) is POSIX-only and refuses to run on Windows,
where the Docker path supervises instead — see require_posix_lifecycle().

Subcommands:
  validate    check company.discord.json against the schema + filesystem
  scaffold    create ~/.hermes/profiles/<name>/ from the roles in the JSON
  bootstrap   create Discord roles/categories/channels from the JSON (idempotent)
  doctor      health-check profiles, tokens, and config for drift
  standup     post (or preview) the daily standup message to #standup
  decision    parse a meeting close block -> normalized JSON / Paperclip issues
  lint        scan text for secrets/PII before OpenCrab ingest
  digest      render a weekly brief from the decision log
  archive     export a meeting thread to sanitized local minutes
  status      one-screen summary of profiles/map/decisions
  up          start every profile's Hermes gateway (detached)
  down        stop the gateways started by `up`
  restart     down + up
  logs        show a gateway's log
  service     emit systemd/launchd units for real auto-restart supervision

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
import re
import shutil
import signal
import subprocess
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
EXIT_CANNOT_RUN = 2  # see README "Machine-readable output" for the code contract


def die(msg: str) -> "NoReturn":  # noqa: F821 - annotation only
    """Abort with the documented 'could not run' code. SystemExit(str) would
    print the message but exit 1, which collides with 'ran and found something'."""
    print(msg, file=sys.stderr)
    raise SystemExit(EXIT_CANNOT_RUN)


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


def load_map(hermes_home: Path) -> dict | None:
    """Read the channel map, or None if absent. Clean error on corrupt JSON."""
    mp = map_path(hermes_home)
    if not mp.is_file():
        return None
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        die(f"ERROR: corrupt channel map at {mp} — re-run `companyctl bootstrap`.")


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
                    if not isinstance(a, str):
                        err(f"{where}.access", "entries must be strings")
                    elif a not in allowed_access:
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
        die(f"ERROR: config not found: {config_path}")
    except json.JSONDecodeError as exc:
        die(f"ERROR: invalid JSON in {config_path}: {exc}")
    errors = validate(config, REPO_ROOT)
    if errors:
        lines = "\n".join(f"  - {e}" for e in errors)
        die(f"ERROR: {config_path} is invalid — run `companyctl validate`:\n{lines}")
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
    role_count = len(config.get("roles", []))
    chan_count = len(config.get("discord", {}).get("channels", []))
    if getattr(args, "json", False):
        print(json.dumps({"ok": not errors, "config": str(config_path), "errors": errors,
                          "roles": role_count, "channels": chan_count},
                         ensure_ascii=False, indent=2))
        return 1 if errors else 0
    if errors:
        print(f"FAIL: {config_path} ({len(errors)} error(s))")
        for e in errors:
            print(f"  - {e}")
        return 1
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
DISCORD_TIMEOUT = 15.0  # seconds; without it an unreachable host hangs forever


def discord_request(method: str, path: str, token: str, payload=None, _retries=3,
                    timeout: float = DISCORD_TIMEOUT):
    url = DISCORD_API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bot {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "companyctl (ai-company-discord)")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and _retries > 0:
            retry_after = float(exc.headers.get("Retry-After", "1"))
            time.sleep(min(retry_after, 10))
            return discord_request(method, path, token, payload, _retries - 1, timeout)
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise DiscordError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DiscordError(f"{method} {path} -> {exc.reason}") from exc
    except TimeoutError as exc:
        raise DiscordError(f"{method} {path} -> timed out after {timeout}s") from exc


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


def top_level_yaml_keys(text: str) -> set[str]:
    """Top-level (column-0) mapping keys in a YAML text. Comments ignored."""
    keys = set()
    for line in text.splitlines():
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            m = re.match(r"([A-Za-z_][\w-]*):", line)
            if m:
                keys.add(m.group(1))
    return keys


def template_config_keys() -> set[str]:
    template = REPO_ROOT / "templates" / "config.yaml"
    if not template.is_file():
        return set()
    return top_level_yaml_keys(template.read_text(encoding="utf-8"))


def doctor_offline(config: dict, hermes_home: Path) -> list[tuple[str, str]]:
    """Return (level, message) rows. level in {PASS, WARN, FAIL}."""
    rows: list[tuple[str, str]] = []
    profiles_dir = hermes_home / "profiles"
    token_owners: dict[str, list[str]] = {}
    tmpl_keys = template_config_keys()

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
            cfg_text = cfg_file.read_text(encoding="utf-8")
            if count_top_level_key(cfg_text, "discord") > 1:
                rows.append(("FAIL", f"{profile}: duplicate top-level `discord:` key in config.yaml"))
            if re.search(r"(?m)^\s*require_mention:\s*false\b", cfg_text):
                rows.append(("FAIL", f"{profile}: require_mention is false (shared channels answer without @mention)"))
            missing = tmpl_keys - top_level_yaml_keys(cfg_text)
            if missing:
                rows.append(("WARN", f"{profile}: config.yaml missing template key(s): {', '.join(sorted(missing))}"))

        token = read_env_value(pdir / ".env", "DISCORD_BOT_TOKEN")
        if not token:
            rows.append(("WARN", f"{profile}: DISCORD_BOT_TOKEN is empty"))
        else:
            digest = hashlib.sha256(token.encode()).hexdigest()
            token_owners.setdefault(digest, []).append(profile)

    for owners in token_owners.values():
        distinct = sorted(set(owners))
        if len(distinct) > 1:
            rows.append(
                ("FAIL", f"shared DISCORD_BOT_TOKEN across profiles: {', '.join(distinct)}")
            )

    for role in config["roles"]:
        if not role.get("modelHint"):
            rows.append(("WARN", f"{role['id']}: no modelHint (cost visibility — see COSTS.md)"))

    rows.append(
        ("WARN", "Message Content Intent cannot be verified via API — confirm it is ON in the Developer Portal")
    )
    return rows


def doctor_online(config: dict, hermes_home: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    profiles_dir = hermes_home / "profiles"
    data = load_map(hermes_home) or {}
    guild_id = data.get("guildId")

    for role in config["roles"]:
        profile = role["hermesProfile"]
        token = read_env_value(profiles_dir / profile / ".env", "DISCORD_BOT_TOKEN")
        if not token:
            continue
        try:
            me = discord_request("GET", "/users/@me", token)
            rows.append(("PASS", f"{profile}: token valid (bot {me.get('username')})"))
            if guild_id:
                guilds = discord_request("GET", "/users/@me/guilds", token) or []
                if not any(str(g.get("id")) == str(guild_id) for g in guilds):
                    rows.append(("FAIL", f"{profile}: bot has not joined guild {guild_id}"))
        except DiscordError as exc:
            rows.append(("FAIL", f"{profile}: token check failed — {exc}"))

    setup_token = os.environ.get("DISCORD_SETUP_TOKEN")
    if setup_token and guild_id:
        try:
            live = discord_request("GET", f"/guilds/{guild_id}/channels", setup_token)
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

    worst = 1 if any(l == "FAIL" for l, _ in rows) else 0
    if args.json:
        print(json.dumps(
            {"ok": not worst,
             "findings": [{"level": l, "message": m} for l, m in rows],
             "fail": sum(1 for l, _ in rows if l == "FAIL"),
             "warn": sum(1 for l, _ in rows if l == "WARN")},
            ensure_ascii=False, indent=2))
        return worst
    for level, msg in rows:
        print(f"  {level:4} {msg}")
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

    data = load_map(hermes_home)
    if data is None:
        print("ERROR: no channel map — run `companyctl bootstrap` first.", file=sys.stderr)
        return 2
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
    state_dir(hermes_home).mkdir(parents=True, exist_ok=True)
    (state_dir(hermes_home) / "last_standup.txt").write_text(today, encoding="utf-8")
    print(f"Posted standup to #standup ({channel_id}).")
    return 0


# --------------------------------------------------------------------------- #
# Decision block parser (PROTOCOL v1 — see PROTOCOLS.md)
# --------------------------------------------------------------------------- #
DECISION_HEADERS = ("DECISION", "OPEN", "ACTIONS", "OWNER", "DUE", "PAPERCLIP")
DUE_SUFFIX_RE = re.compile(r"\(DUE:\s*([^)]+)\)\s*$", re.IGNORECASE)


def build_role_map(config: dict) -> dict:
    """Map owner tokens (id / @ID / Title) to canonical role ids. board -> board."""
    role_map = {"board": "board", "BOARD": "board", "Board": "board"}
    for role in config.get("roles", []):
        rid = role["id"]
        role_map[rid] = rid
        role_map[rid.upper()] = rid
        title = role.get("title", "")
        if title:
            role_map[title.lower()] = rid
    return role_map


def resolve_owner(raw: str, role_map: dict, warnings: list) -> str | None:
    key = raw.lstrip("@").strip()
    for cand in (key, key.lower(), key.upper()):
        if cand in role_map:
            return role_map[cand]
    warnings.append(f"unresolved owner: {raw.strip()}")
    return key.lower() or None


def parse_action(item: str, role_map: dict, warnings: list) -> dict:
    due = None
    m = DUE_SUFFIX_RE.search(item)
    if m:
        due = m.group(1).strip()
        item = item[: m.start()].strip()
    owner_raw, sep, task = item.partition(":")
    if not sep:
        warnings.append(f"action without an owner (missing ':'): {item}")
        return {"owner": None, "task": item.strip(), "due": due}
    return {"owner": resolve_owner(owner_raw, role_map, warnings), "task": task.strip(), "due": due}


def parse_decision_block(text: str, role_map: dict) -> dict:
    """Pure. Parse a meeting close block (MEETINGS.md) or the compact
    OWNER/DUE form (ROUTING.md) into normalized lists."""
    decisions: list[str] = []
    open_items: list[str] = []
    actions: list[dict] = []
    warnings: list[str] = []
    current = None
    owner_field = None
    due_field = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        header = None
        after = ""
        up = line.upper()
        for h in DECISION_HEADERS:
            if up.startswith(h + ":"):
                header = h
                after = line[len(h) + 1:].strip()
                break
        if header:
            if header == "DECISION":
                current = "decision"
                if after:
                    decisions.append(after)
            elif header == "OPEN":
                current = "open"
                if after:
                    open_items.append(after)
            elif header == "ACTIONS":
                current = "actions"
                if after:
                    actions.append(parse_action(after, role_map, warnings))
            elif header == "OWNER":
                owner_field = after
            elif header == "DUE":
                due_field = after
            # PAPERCLIP: directive is ignored by the parser.
            continue

        item = line[1:].strip() if line.startswith("-") else line
        if current == "decision":
            decisions.append(item)
        elif current == "open":
            open_items.append(item)
        elif current == "actions":
            actions.append(parse_action(item, role_map, warnings))
        else:
            warnings.append(f"line outside any section ignored: {item}")

    if owner_field and not actions and decisions:
        actions.append(
            {"owner": resolve_owner(owner_field, role_map, warnings),
             "task": decisions[-1], "due": due_field}
        )

    return {"decisions": decisions, "open": open_items, "actions": actions, "warnings": warnings}


def read_text_input(args: argparse.Namespace) -> str:
    if getattr(args, "file", None):
        try:
            return Path(args.file).read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, IsADirectoryError, UnicodeDecodeError) as exc:
            die(f"ERROR: cannot read {args.file}: {exc}")
    return sys.stdin.read()


def append_decision_log(hermes_home: Path, entry: dict) -> Path:
    d = state_dir(hermes_home)
    d.mkdir(parents=True, exist_ok=True)
    log = d / "decisions.ndjson"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return log


def http_post_json(url: str, payload: dict, timeout: float = 5.0):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return json.loads(body) if body else None


def build_paperclip_issues(entry: dict) -> list[dict]:
    """Pure. One issue payload per ACTION that carries a task."""
    return [
        {"title": a["task"][:80], "body": a["task"], "owner": a.get("owner"), "due": a.get("due")}
        for a in entry["actions"]
        if a.get("task")
    ]


def emit_paperclip(entry: dict, base_url: str) -> dict:
    """Create an issue per ACTION. Returns a result the caller renders — the
    degraded payload is returned, not printed, so a GUI can offer a copy button."""
    issues = build_paperclip_issues(entry)
    if not issues:
        return {"status": "no-actions", "issues": []}
    try:
        for iss in issues:
            http_post_json(base_url.rstrip("/") + "/issues", iss)
        return {"status": "created", "count": len(issues), "url": base_url, "issues": issues}
    except (urllib.error.URLError, OSError) as exc:
        return {"status": "unreachable", "error": str(exc), "issues": issues}


def render_paperclip_result(result: dict) -> str:
    if result["status"] == "no-actions":
        return "(no ACTIONS to turn into Paperclip issues)"
    if result["status"] == "created":
        return f"Created {result['count']} Paperclip issue(s) at {result['url']}."
    return (
        f"Paperclip not reachable ({result['error']}); emitting issue payloads instead:\n"
        + json.dumps(result["issues"], ensure_ascii=False, indent=2)
    )


def cmd_decision(args: argparse.Namespace) -> int:
    config = load_valid_config(Path(args.config))
    role_map = build_role_map(config)
    parsed = parse_decision_block(read_text_input(args), role_map)

    for w in parsed["warnings"]:
        print(f"warn: {w}", file=sys.stderr)
    if not parsed["decisions"] and not parsed["actions"]:
        print("ERROR: no DECISION/ACTIONS found — check the format (see PROTOCOLS.md).", file=sys.stderr)
        return 2

    entry = {
        "date": datetime.date.today().isoformat(),
        "decisions": parsed["decisions"],
        "open": parsed["open"],
        "actions": parsed["actions"],
    }
    if args.to_paperclip:
        print(render_paperclip_result(emit_paperclip(entry, args.paperclip_url)))
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    if not args.dry_run:
        log = append_decision_log(resolve_hermes_home(args), entry)
        print(f"\nLogged to {log}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# Sanitize lint (pre-OpenCrab-ingest gate)
# --------------------------------------------------------------------------- #
SENSITIVE_RULES = [
    ("discord-token", re.compile(r"\b[A-Za-z0-9_-]{24,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}\b"), "FAIL"),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"), "FAIL"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "FAIL"),
    ("slack-webhook", re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]+"), "FAIL"),
    ("api-key",
     re.compile(r"(sk-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|"
                r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{35})"), "FAIL"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "FAIL"),
    ("snowflake-id", re.compile(r"\b\d{17,20}\b"), "WARN"),
]


def scan_for_sensitive(text: str) -> list[tuple[str, int, str]]:
    """Pure. Return (severity, line_no, kind). Never returns the secret value."""
    findings: list[tuple[str, int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        for kind, pattern, sev in SENSITIVE_RULES:
            if pattern.search(line):
                findings.append((sev, i, kind))
    mentions = len(re.findall(r"@\w+", text))
    times = len(re.findall(r"\b\d{1,2}:\d{2}\b", text))
    if mentions >= 3 and times >= 2:
        findings.append(("WARN", 0, "meeting-transcript-shape (summarize before ingest)"))
    return findings


def cmd_lint(args: argparse.Namespace) -> int:
    findings = scan_for_sensitive(read_text_input(args))
    if getattr(args, "json", False):
        print(json.dumps(
            {"ok": not findings,
             "findings": [{"severity": s_, "line": ln, "kind": k} for s_, ln, k in findings]},
            ensure_ascii=False, indent=2))
        return 1 if findings else 0
    if not findings:
        print("OK: no sensitive patterns found — safe to stage for OpenCrab ingest")
        return 0
    print(f"BLOCK: {len(findings)} finding(s) — sanitize before ingest:")
    for sev, line_no, kind in findings:
        where = f"line {line_no}" if line_no else "document"
        print(f"  {sev:4} {where}: {kind}")
    return 1


# --------------------------------------------------------------------------- #
# Weekly digest (from the decision log)
# --------------------------------------------------------------------------- #
def read_decision_log(hermes_home: Path, start_iso: str, end_iso: str) -> list[dict]:
    log = state_dir(hermes_home) / "decisions.ndjson"
    if not log.is_file():
        return []
    entries = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if start_iso <= e.get("date", "") <= end_iso:
            entries.append(e)
    return entries


def render_digest(entries: list[dict], start_iso: str, end_iso: str) -> str:
    decisions: list[str] = []
    opens: list[str] = []
    by_owner: dict[str, list[dict]] = {}
    for e in entries:
        decisions += e.get("decisions", [])
        opens += e.get("open", [])
        for a in e.get("actions", []):
            by_owner.setdefault(a.get("owner") or "unassigned", []).append(a)

    lines = [f"# 주간 브리핑 — {start_iso} ~ {end_iso}", ""]
    lines.append(f"## 결정 ({len(decisions)})")
    lines += [f"- {d}" for d in decisions] or ["- (없음)"]
    lines += ["", f"## 미결 (Open) ({len(opens)})"]
    lines += [f"- {o}" for o in opens] or ["- (없음)"]
    lines += ["", "## 액션 (담당별)"]
    if by_owner:
        for owner in sorted(by_owner):
            lines.append(f"### @{owner}")
            for a in by_owner[owner]:
                due = f" (DUE: {a['due']})" if a.get("due") else ""
                lines.append(f"- {a.get('task', '')}{due}")
    else:
        lines.append("- (없음)")
    return "\n".join(lines) + "\n"


def cmd_digest(args: argparse.Namespace) -> int:
    today = datetime.date.today()
    if args.since:
        start = args.since
    else:
        start = (today - datetime.timedelta(days=args.days)).isoformat()
    end = args.until or today.isoformat()

    entries = read_decision_log(resolve_hermes_home(args), start, end)
    print(render_digest(entries, start, end))
    return 0


# --------------------------------------------------------------------------- #
# Archive (meeting thread -> sanitized minutes)
# --------------------------------------------------------------------------- #
def render_minutes(thread_name: str, messages: list[dict]) -> str:
    """Pure. Render Discord messages (chronological) into markdown minutes."""
    lines = [f"# 회의록 — {thread_name}", ""]
    for m in messages:
        author = (m.get("author") or {}).get("username", "unknown")
        content = (m.get("content") or "").strip()
        if content:
            lines.append(f"- **{author}**: {content}")
    return "\n".join(lines) + "\n"


def chunk_text(text: str, size: int = 1900) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "thread"


def fetch_thread(thread_id: str, token: str) -> tuple[str, list[dict]]:
    info = discord_request("GET", f"/channels/{thread_id}", token)
    name = (info or {}).get("name", str(thread_id))
    messages: list[dict] = []
    before = None
    while True:
        path = f"/channels/{thread_id}/messages?limit=100"
        if before:
            path += f"&before={before}"
        batch = discord_request("GET", path, token)
        if not batch:
            break
        messages.extend(batch)
        if len(batch) < 100:
            break
        before = batch[-1]["id"]
    messages.reverse()  # Discord returns newest-first
    return name, messages


def cmd_archive(args: argparse.Namespace) -> int:
    hermes_home = resolve_hermes_home(args)
    token = os.environ.get("DISCORD_SETUP_TOKEN") or read_env_value(
        hermes_home / "profiles" / "ceo" / ".env", "DISCORD_BOT_TOKEN"
    )
    if not token:
        print("ERROR: no token (set DISCORD_SETUP_TOKEN or fill ceo/.env).", file=sys.stderr)
        return 2
    try:
        name, messages = fetch_thread(args.thread, token)
    except DiscordError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    minutes = render_minutes(name, messages)
    findings = scan_for_sensitive(minutes)
    if findings:
        print(f"BLOCK: minutes contain {len(findings)} sensitive pattern(s) — not saved or posted:")
        for sev, line_no, kind in findings:
            where = f"line {line_no}" if line_no else "document"
            print(f"  {sev:4} {where}: {kind}")
        return 1

    out_dir = state_dir(hermes_home) / "minutes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{datetime.date.today().isoformat()}-{slugify(name)}.md"
    out_file.write_text(minutes, encoding="utf-8")
    print(f"Saved minutes: {out_file} ({len(messages)} messages)")

    if args.post_briefs:
        data = load_map(hermes_home)
        if not data:
            print("WARN: no channel map — skipping --post-briefs.", file=sys.stderr)
            return 0
        channel_id = data.get("channels", {}).get("briefs")
        if not channel_id:
            print("WARN: #briefs not in channel map — skipping post.", file=sys.stderr)
            return 0
        try:
            for chunk in chunk_text(minutes):
                discord_request("POST", f"/channels/{channel_id}/messages", token, {"content": chunk})
            print(f"Posted minutes to #briefs ({channel_id}).")
        except DiscordError as exc:
            print(f"ERROR posting to #briefs: {exc}", file=sys.stderr)
            return 2
    return 0


# --------------------------------------------------------------------------- #
# Status (one-screen operational summary)
# --------------------------------------------------------------------------- #
def read_all_decisions(hermes_home: Path) -> list[dict]:
    log = state_dir(hermes_home) / "decisions.ndjson"
    if not log.is_file():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def status_report(config: dict, hermes_home: Path) -> dict:
    """Everything `status` knows, as data. The renderer below is the only part
    that prints, so a script or UI can consume this directly."""
    profiles_dir = hermes_home / "profiles"
    scaffolded = [r["hermesProfile"] for r in config["roles"]
                  if (profiles_dir / r["hermesProfile"]).is_dir()]
    data = load_map(hermes_home)
    decisions = read_all_decisions(hermes_home)
    marker = state_dir(hermes_home) / "last_standup.txt"

    report = {
        "profiles": {
            "scaffolded": scaffolded,
            "total": len(config["roles"]),
        },
        "discordMap": None if not data else {
            "guildId": data.get("guildId"),
            "channelCount": len(data.get("channels", {})),
        },
        "decisions": {
            "count": len(decisions),
            "last": decisions[-1].get("date") if decisions else None,
            "recent": [
                {"date": d.get("date"), "first": (d.get("decisions") or [None])[0]}
                for d in decisions[-3:]
            ],
        },
        "lastStandup": marker.read_text(encoding="utf-8").strip() if marker.is_file() else None,
    }

    if IS_WINDOWS:
        report["gateways"] = {"supported": False, "reason": "native lifecycle is POSIX-only"}
    else:
        gws = load_gateways(hermes_home)
        alive = sorted(p for p, r in gws.items() if pid_alive(r.get("pid", -1)))
        report["gateways"] = {
            "supported": True,
            "tracked": len(gws),
            "up": alive,
            "down": sorted(p for p in gws if p not in alive),
        }
    return report


def render_status(r: dict) -> str:
    p = r["profiles"]
    lines = [f"profiles   : {len(p['scaffolded'])}/{p['total']} scaffolded "
             f"({', '.join(p['scaffolded']) or 'none'})"]

    m = r["discordMap"]
    lines.append(f"discord map: guild {m['guildId'] or '?'}, {m['channelCount']} channels"
                 if m else "discord map: none (run `companyctl bootstrap`)")

    d = r["decisions"]
    if d["count"]:
        lines.append(f"decisions  : {d['count']} logged, last {d['last'] or '?'}")
        lines += [f"             · {x['date'] or '?'}: {x['first'] or '(none)'}" for x in d["recent"]]
    else:
        lines.append("decisions  : none logged")

    lines.append(f"last standup: {r['lastStandup'] or 'never'}")

    g = r["gateways"]
    if not g["supported"]:
        lines.append("gateways   : native lifecycle is POSIX-only — use `docker compose ps`")
    elif g["tracked"]:
        lines.append(f"gateways   : {len(g['up'])}/{g['tracked']} up"
                     + (f" (up: {', '.join(g['up'])})" if g["up"] else "")
                     + (f" — DOWN: {', '.join(g['down'])}" if g["down"] else ""))
    else:
        lines.append("gateways   : none started via `companyctl up`")
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    config = load_valid_config(Path(args.config))
    report = status_report(config, resolve_hermes_home(args))
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_status(report))
    return 0


# --------------------------------------------------------------------------- #
# Gateway lifecycle (native install path; the Docker path uses compose)
#
# `up` launches detached gateways and records their pids. It deliberately does
# NOT act as a supervisor — a CLI cannot restart anything after it exits.
# For real auto-restart, `service` emits systemd/launchd units; the Docker path
# gets it from `restart: unless-stopped`.
# --------------------------------------------------------------------------- #
IS_WINDOWS = os.name == "nt"

# Why the native lifecycle is POSIX-only, deliberately:
#   os.kill(pid, 0) — the liveness probe — is documented on Windows as
#   "unconditionally killed by the TerminateProcess API", so a status refresh
#   would kill the very gateways it inspects. signal.SIGKILL does not exist
#   there, start_new_session is ignored, `tail -f` is absent, and there is no
#   Windows unit for `service` to emit. Rather than ship a half-working
#   supervisor with a destructive probe, Windows is routed to the Docker path
#   (docker compose up -d), which supervises properly via restart policies.
WINDOWS_LIFECYCLE_MSG = (
    "ERROR: the native gateway lifecycle is POSIX-only (macOS/Linux).\n"
    "       On Windows use the Docker path instead:  docker compose up -d\n"
    "       See ORCHESTRATION.md §A."
)


def require_posix_lifecycle() -> None:
    if IS_WINDOWS:
        die(WINDOWS_LIFECYCLE_MSG)


def hermes_bin() -> str:
    return os.environ.get("HERMES_BIN", "hermes")


def gateways_path(hermes_home: Path) -> Path:
    return state_dir(hermes_home) / "gateways.json"


def log_path(hermes_home: Path, profile: str) -> Path:
    return state_dir(hermes_home) / "logs" / f"{profile}.log"


def load_gateways(hermes_home: Path) -> dict:
    p = gateways_path(hermes_home)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        die(f"ERROR: corrupt gateway state at {p} — delete it and re-run `up`.")


def save_gateways(hermes_home: Path, data: dict) -> None:
    state_dir(hermes_home).mkdir(parents=True, exist_ok=True)
    gateways_path(hermes_home).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_zombie(pid: int) -> bool:
    """A gateway whose parent (this CLI) already exited stays as an unreaped
    zombie in containers without a reaping init. os.kill(pid, 0) succeeds on a
    zombie, so liveness must exclude it explicitly."""
    stat = Path(f"/proc/{pid}/stat")
    if stat.is_file():  # Linux
        try:
            # state is the field after the (possibly space-containing) comm
            return stat.read_text(encoding="utf-8").rpartition(")")[2].split()[0] == "Z"
        except (OSError, IndexError):
            return False
    try:  # macOS / BSD
        out = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip().startswith("Z")
    except (OSError, subprocess.SubprocessError):
        return False


def pid_alive(pid: int) -> bool:
    if pid is None or pid < 1:
        return False
    if IS_WINDOWS:
        # NEVER os.kill(pid, 0) here — on Windows that terminates the target.
        # The native lifecycle is unsupported on Windows anyway; report not-alive
        # rather than probing destructively.
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _is_zombie(pid)


def selected_profiles(config: dict, only: str | None) -> list[str]:
    profiles = [r["hermesProfile"] for r in config["roles"]]
    if only is None:
        return profiles
    if only not in profiles:
        die(f"ERROR: unknown profile '{only}' (have: {', '.join(profiles)})")
    return [only]


def start_gateway(hermes_home: Path, profile: str) -> int:
    """Spawn a detached gateway, returning its pid. Output goes to a log file.

    Uses `gateway run`, NOT `gateway start`. Verified against hermes-agent
    0.19.0, whose own help distinguishes them:
        run    Run gateway in foreground (recommended for WSL, Docker, Termux)
        start  Start the installed systemd/launchd background service
    `start` is a service-control verb — it needs `gateway install` to have run
    first and returns immediately, so the pid we captured would be a control
    client, not the gateway. `run` is the process we can actually track."""
    log = log_path(hermes_home, profile)
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("a", encoding="utf-8")
    handle.write(f"\n==== companyctl up {datetime.datetime.now().isoformat(timespec='seconds')} ====\n")
    handle.flush()
    env = dict(os.environ, HERMES_HOME=str(hermes_home))
    proc = subprocess.Popen(
        [hermes_bin(), "-p", profile, "gateway", "run"],
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # survives this CLI exiting
        env=env,
    )
    handle.close()
    return proc.pid


def cmd_up(args: argparse.Namespace) -> int:
    require_posix_lifecycle()
    config = load_valid_config(Path(args.config))
    hermes_home = resolve_hermes_home(args)
    if shutil.which(hermes_bin()) is None:
        print(f"ERROR: '{hermes_bin()}' not found on PATH. Install Hermes, or set HERMES_BIN.",
              file=sys.stderr)
        return 2

    state = load_gateways(hermes_home)
    started, kept = [], []
    for profile in selected_profiles(config, args.profile):
        rec = state.get(profile)
        if rec and pid_alive(rec.get("pid", -1)):
            kept.append(profile)
            continue
        pid = start_gateway(hermes_home, profile)
        state[profile] = {
            "pid": pid,
            "started": datetime.datetime.now().isoformat(timespec="seconds"),
            "log": str(log_path(hermes_home, profile)),
        }
        started.append(f"{profile}({pid})")
    save_gateways(hermes_home, state)

    if started:
        print(f"started : {', '.join(started)}")
    if kept:
        print(f"running : {', '.join(kept)} (already up)")
    print(f"logs    : {state_dir(hermes_home) / 'logs'}")
    print("note    : `up` is not a supervisor — see `companyctl service` for auto-restart.")
    return 0


def stop_pid(pid: int, timeout: float = 10.0) -> str:
    """SIGTERM, then SIGKILL if it lingers. Returns what happened."""
    if not pid_alive(pid):
        return "already stopped"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "already stopped"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return "stopped"
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "stopped"
    return "killed (did not exit on SIGTERM)"


def cmd_down(args: argparse.Namespace) -> int:
    require_posix_lifecycle()
    config = load_valid_config(Path(args.config))
    hermes_home = resolve_hermes_home(args)
    state = load_gateways(hermes_home)
    if not state:
        print("no gateways recorded (nothing started by `companyctl up`).")
        return 0

    for profile in selected_profiles(config, args.profile):
        rec = state.get(profile)
        if not rec:
            print(f"  {profile}: not recorded")
            continue
        print(f"  {profile}: {stop_pid(rec['pid'])}")
        state.pop(profile, None)
    save_gateways(hermes_home, state)
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    require_posix_lifecycle()
    rc = cmd_down(args)
    if rc != 0:
        return rc
    return cmd_up(args)


def cmd_logs(args: argparse.Namespace) -> int:
    require_posix_lifecycle()
    config = load_valid_config(Path(args.config))
    hermes_home = resolve_hermes_home(args)
    profiles = selected_profiles(config, args.profile)
    if len(profiles) > 1:
        print(f"ERROR: pick one profile with --profile (have: {', '.join(profiles)})", file=sys.stderr)
        return 2
    log = log_path(hermes_home, profiles[0])
    if not log.is_file():
        print(f"ERROR: no log at {log} — has `companyctl up` run?", file=sys.stderr)
        return 2
    if args.follow:
        try:
            subprocess.run(["tail", "-f", "-n", str(args.lines), str(log)], check=False)
        except KeyboardInterrupt:
            pass
        return 0
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-args.lines:]))
    return 0


def cmd_service(args: argparse.Namespace) -> int:
    """Register each profile's gateway as a real OS service.

    This delegates to `hermes gateway install`, which upstream already provides
    per profile — it writes the systemd unit / launchd plist itself, with
    --start-on-login for boot survival. An earlier version of this command
    hand-wrote competing units running `gateway start`; that was wrong twice
    over (it duplicated upstream, and `start` only drives an already-installed
    service). All this adds is the fan-out across the five profiles."""
    require_posix_lifecycle()
    config = load_valid_config(Path(args.config))
    hermes_home = resolve_hermes_home(args)
    profiles = selected_profiles(config, args.profile)
    if shutil.which(hermes_bin()) is None:
        die(f"ERROR: '{hermes_bin()}' not found on PATH. Install Hermes, or set HERMES_BIN.")

    env = dict(os.environ, HERMES_HOME=str(hermes_home))
    cmds = [
        [hermes_bin(), "-p", p, "gateway", "install"]
        + (["--start-now"] if args.start_now else ["--no-start-now"])
        + (["--start-on-login"] if args.start_on_login else [])
        for p in profiles
    ]

    if not args.apply:
        print("(dry-run) would run, one per profile:\n")
        for c in cmds:
            print("  " + " ".join(c))
        print("\nRe-run with --apply to install. Uninstall with:")
        print(f"  {hermes_bin()} -p <profile> gateway uninstall")
        return 0

    failed = []
    for profile, cmd in zip(profiles, cmds):
        print(f"-- {profile}: {' '.join(cmd)}")
        try:
            rc = subprocess.run(cmd, env=env, timeout=180).returncode
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"   ERROR: {exc}", file=sys.stderr)
            failed.append(profile)
            continue
        if rc != 0:
            failed.append(profile)
    if failed:
        print(f"\nFAILED for: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"\nInstalled {len(profiles)} gateway service(s). Check with:")
    print(f"  {hermes_bin()} gateway list")
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

    p_val = sub.add_parser("validate", help="check company.discord.json")
    p_val.add_argument("--json", action="store_true", help="machine-readable output")
    p_val.set_defaults(func=cmd_validate)

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
    p_doc.add_argument("--json", action="store_true", help="machine-readable output")
    _add_hermes_home(p_doc)
    p_doc.set_defaults(func=cmd_doctor)

    p_stand = sub.add_parser("standup", help="post or preview the daily standup message")
    p_stand.add_argument("action", choices=["post"], help="what to do")
    p_stand.add_argument("--dry-run", action="store_true", help="print the message instead of posting")
    _add_hermes_home(p_stand)
    p_stand.set_defaults(func=cmd_standup)

    p_dec = sub.add_parser("decision", help="parse a meeting close block -> normalized JSON / Paperclip")
    p_dec.add_argument("--file", help="read the block from a file (default: stdin)")
    p_dec.add_argument("--to-paperclip", action="store_true", help="create a Paperclip issue per ACTION")
    p_dec.add_argument("--paperclip-url", default="http://127.0.0.1:3100", help="Paperclip base URL")
    p_dec.add_argument("--dry-run", action="store_true", help="parse only; do not append to the decision log")
    _add_hermes_home(p_dec)
    p_dec.set_defaults(func=cmd_decision)

    p_lint = sub.add_parser("lint", help="scan text for secrets/PII before OpenCrab ingest")
    p_lint.add_argument("--file", help="read text from a file (default: stdin)")
    p_lint.add_argument("--json", action="store_true", help="machine-readable output")
    p_lint.set_defaults(func=cmd_lint)

    p_dig = sub.add_parser("digest", help="render a weekly brief from the decision log")
    p_dig.add_argument("--days", type=int, default=7, help="window size in days (default: 7)")
    p_dig.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    p_dig.add_argument("--until", help="end date YYYY-MM-DD (default: today)")
    _add_hermes_home(p_dig)
    p_dig.set_defaults(func=cmd_digest)

    p_arch = sub.add_parser("archive", help="export a meeting thread to sanitized local minutes")
    p_arch.add_argument("--thread", required=True, help="Discord thread (channel) id to export")
    p_arch.add_argument("--post-briefs", action="store_true", help="also post the minutes to #briefs")
    _add_hermes_home(p_arch)
    p_arch.set_defaults(func=cmd_archive)

    p_stat = sub.add_parser("status", help="one-screen summary of profiles/map/decisions")
    p_stat.add_argument("--json", action="store_true", help="machine-readable output")
    _add_hermes_home(p_stat)
    p_stat.set_defaults(func=cmd_status)

    p_up = sub.add_parser("up", help="start every profile's Hermes gateway (detached)")
    p_up.add_argument("--profile", help="only this profile (default: all)")
    _add_hermes_home(p_up)
    p_up.set_defaults(func=cmd_up)

    p_down = sub.add_parser("down", help="stop the gateways started by `up`")
    p_down.add_argument("--profile", help="only this profile (default: all)")
    _add_hermes_home(p_down)
    p_down.set_defaults(func=cmd_down)

    p_re = sub.add_parser("restart", help="down + up")
    p_re.add_argument("--profile", help="only this profile (default: all)")
    _add_hermes_home(p_re)
    p_re.set_defaults(func=cmd_restart)

    p_log = sub.add_parser("logs", help="show a gateway's log")
    p_log.add_argument("--profile", required=True, help="which profile's log")
    p_log.add_argument("-n", "--lines", type=int, default=40, help="lines to show (default: 40)")
    p_log.add_argument("-f", "--follow", action="store_true", help="follow the log")
    _add_hermes_home(p_log)
    p_log.set_defaults(func=cmd_logs)

    p_svc = sub.add_parser("service",
                           help="register each profile's gateway via `hermes gateway install`")
    p_svc.add_argument("--profile", help="only this profile (default: all)")
    p_svc.add_argument("--apply", action="store_true", help="actually install (default: dry-run)")
    p_svc.add_argument("--start-now", action="store_true", help="start each service after installing")
    p_svc.add_argument("--start-on-login", action="store_true", help="survive reboot")
    _add_hermes_home(p_svc)
    p_svc.set_defaults(func=cmd_service)

    return parser


def _force_utf8_output() -> None:
    """Korean output must not crash on a non-UTF-8 console (e.g. Windows cp1252
    when stdout is redirected/piped)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
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
