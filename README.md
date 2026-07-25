# AI Company Discord

**Discord-first control room for a one-person AI company.**

Each executive (CEO, CTO, Loop, Growth, Critic) runs as an isolated [Hermes](https://github.com/NousResearch/hermes-agent) profile with its own `SOUL.md`, memory, and **Discord bot token**. You sit on the Board; agents meet in Discord threads, ship work through [Paperclip](https://github.com/paperclipai/paperclip), and store sanitized knowledge in [OpenCrab](https://opencrab.sh) via [workmate-opencrab-ingest](https://github.com/contentscoin/workmate-opencrab-ingest-skill).

Telegram is optional **DM hotline only**. Multi-agent meetings default to Discord (history + per-bot identity).

Role routing follows the spirit of [GJC multivendor setup](https://github.com/project820/gjc-multivendor-setup-guide): strong orchestrator + signal-based delegation + cross-family critic.

## Stack

| Layer | Tool |
|-------|------|
| Meeting / souls | Discord + Hermes profiles |
| Org / tasks / budgets | Paperclip |
| Dev center | **Cursor** (+ Codex / Claude satellites) |
| Product framework (optional) | [akanjs](https://github.com/akan-team/akanjs) — full-stack TS, candidate |
| Knowledge | OpenCrab + Workmate ingest |
| Model routing (optional) | GJC `daily` / `coding-sprint` / `cyber-cop` |

> **Dev center vs product framework** — Cursor/Codex/Claude are the coding *agents*; a product framework is what they build *in*. If the company ships full-stack TypeScript, [akanjs](https://github.com/akan-team/akanjs) (Bun+React+SQLite, schema-as-source-of-truth codegen, AI-agent guideline generation) is a candidate. Not mandated — the stack choice is a CEO/Board decision.

## Architecture

```mermaid
flowchart LR
    B["Board (human)"] -->|"agenda · approvals · decisions"| DC

    subgraph DC["Discord — meeting plane"]
        CH1["#board-you · #approvals"]
        CH2["#exec-meeting · #standup · #war-room"]
        CH3["#dev · #loop · #growth"]
        CH4["#ingest-review · #briefs"]
    end

    subgraph HP["Hermes profiles x5 (isolated bot tokens)"]
        CEO["CEO - orchestration"]
        CTO["CTO - implementation (Cursor primary)"]
        LOOP["Loop - DoD verification"]
        GROWTH["Growth - SNS/content"]
        CRITIC["Critic - cross-family review"]
    end

    DC <-->|"@mention"| HP
    CEO -->|"DECISION → issue"| PC["Paperclip - execution source of truth"]
    CEO -->|"sanitized summaries only"| OC["OpenCrab - knowledge (Graph RAG)"]
    CTO --- CUR["Cursor + Codex/Claude satellites"]
```

## Quick start

```bash
git clone https://github.com/contentscoin/ai-company-discord.git
cd ai-company-discord
python3 scripts/companyctl.py validate   # check the company definition
./scripts/scaffold-profiles.sh           # = companyctl scaffold
```

1. Create **five** Discord applications (one bot per soul) — see [SETUP.md](./SETUP.md)
2. Put each `DISCORD_BOT_TOKEN` in `~/.hermes/profiles/<name>/.env`
3. Create roles/categories/channels from the company definition (dry-run first):

```bash
export DISCORD_SETUP_TOKEN=...   # setup bot token, env only
python3 scripts/companyctl.py bootstrap --guild <server-id>           # preview
python3 scripts/companyctl.py bootstrap --guild <server-id> --apply   # create
```

4. Bring the company up — Docker, or natively (see [ORCHESTRATION.md](./ORCHESTRATION.md)):

```bash
docker compose up -d                     # 5 gateways + Paperclip, auto-restarting
# or, on a native Hermes install:
python3 scripts/companyctl.py up         # starts every profile's gateway
```

5. Health-check, then smoke-test in `#exec-meeting`: `@CEO @CTO 주간회의 테스트`

```bash
python3 scripts/companyctl.py doctor
```

> Windows: use `.\scripts\companyctl.ps1 <subcommand>` — see [WINDOWS.md](./WINDOWS.md).

## companyctl

One dependency-free CLI (Python 3 stdlib) driven by `templates/company.discord.json`, the single source of truth.

| Command | What it does |
|---------|--------------|
| `validate` | Check the company definition against the schema + filesystem |
| `scaffold` | Create `~/.hermes/profiles/<name>/` from the roles in the JSON |
| `bootstrap` | Create Discord roles/categories/channels (idempotent, dry-run by default, never deletes) |
| `doctor` | Health-check profiles, tokens, and config drift (`--online` adds live checks) |
| `standup post` | Post/preview the daily standup (Hermes' own cron is the preferred path) |
| `decision` | Parse a meeting close block → normalized JSON / Paperclip issues |
| `lint` | Scan text for secrets/PII before OpenCrab ingest |
| `digest` | Render a weekly brief from the decision log |
| `archive` | Export a meeting thread to sanitized local minutes |
| `status` | One-screen summary of profiles, channel map, decisions, and live gateways |
| `up` / `down` / `restart` | Start, stop, and restart every profile's Hermes gateway |
| `logs` | Show a gateway's log (`--profile ceo -f`) |
| `service` | Emit systemd/launchd units so the init system handles auto-restart |

Secrets are read only from the environment or `.env` and are never printed. Runtime state lives under `~/.hermes/ai-company/`, never in this repo.

## Docs

| Doc | Contents |
|-----|----------|
| [SETUP.md](./SETUP.md) | Discord apps, Hermes, smoke tests |
| [CHANNELS.md](./CHANNELS.md) | Categories, permissions, mention rules |
| [ROUTING.md](./ROUTING.md) | GJC roles ↔ executives ↔ Cursor |
| [MEETINGS.md](./MEETINGS.md) | Exec meeting / standup protocols |
| [PROTOCOLS.md](./PROTOCOLS.md) | Machine-readable DECISION / VERDICT / PASS-FAIL specs (PROTOCOL v1) |
| [ORCHESTRATION.md](./ORCHESTRATION.md) | Bring the company up: Docker Compose or native lifecycle |
| [DESKTOP.md](./DESKTOP.md) | Plan for the desktop app and installer (architecture, phases, what breaks) |
| [ROADMAP.md](./ROADMAP.md) | Enhancement roadmap (phases 1–5, upstream boundaries) |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | Symptom → cause → fix tables |
| [COSTS.md](./COSTS.md) | Cost visibility for non-Paperclip users (modelHint) |
| `profiles/*/SOUL.md` | Independent souls |
| `templates/company.discord.json` | Machine-readable company template |

## Why not Telegram for meetings?

Same bot token looks like one person; Bot API has no channel history; bot↔bot chat is fragile. Profiles alone do not create independent group conversations. Use Discord for the room, Telegram DM only if you want a pocket pager.

## License

MIT — see [LICENSE](./LICENSE).

Upstream projects keep their own licenses (Hermes, Paperclip, GJC guide, OpenCrab, etc.).
