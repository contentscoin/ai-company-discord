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
import re
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
        return Path(args.file).read_text(encoding="utf-8")
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


def emit_paperclip(entry: dict, base_url: str) -> None:
    issues = [
        {"title": a["task"][:80], "body": a["task"], "owner": a.get("owner"), "due": a.get("due")}
        for a in entry["actions"]
        if a.get("task")
    ]
    if not issues:
        print("(no ACTIONS to turn into Paperclip issues)")
        return
    try:
        for iss in issues:
            http_post_json(base_url.rstrip("/") + "/issues", iss)
        print(f"Created {len(issues)} Paperclip issue(s) at {base_url}.")
    except (urllib.error.URLError, OSError) as exc:
        print(f"Paperclip not reachable ({exc}); emitting issue payloads instead:")
        print(json.dumps(issues, ensure_ascii=False, indent=2))


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
        emit_paperclip(entry, args.paperclip_url)
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
    ("api-key",
     re.compile(r"\b(sk-[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|"
                r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{35})\b"), "FAIL"),
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

    p_dec = sub.add_parser("decision", help="parse a meeting close block -> normalized JSON / Paperclip")
    p_dec.add_argument("--file", help="read the block from a file (default: stdin)")
    p_dec.add_argument("--to-paperclip", action="store_true", help="create a Paperclip issue per ACTION")
    p_dec.add_argument("--paperclip-url", default="http://127.0.0.1:3100", help="Paperclip base URL")
    p_dec.add_argument("--dry-run", action="store_true", help="parse only; do not append to the decision log")
    _add_hermes_home(p_dec)
    p_dec.set_defaults(func=cmd_decision)

    p_lint = sub.add_parser("lint", help="scan text for secrets/PII before OpenCrab ingest")
    p_lint.add_argument("--file", help="read text from a file (default: stdin)")
    p_lint.set_defaults(func=cmd_lint)

    p_dig = sub.add_parser("digest", help="render a weekly brief from the decision log")
    p_dig.add_argument("--days", type=int, default=7, help="window size in days (default: 7)")
    p_dig.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    p_dig.add_argument("--until", help="end date YYYY-MM-DD (default: today)")
    _add_hermes_home(p_dig)
    p_dig.set_defaults(func=cmd_digest)

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
