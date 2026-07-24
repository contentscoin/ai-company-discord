# Discord + Hermes 설치 체크리스트

토큰·시크릿은 이 레포에 넣지 마세요. 모두 로컬 `~/.hermes/profiles/<name>/.env`에만 저장합니다.

## 0. 사전 요구

- [ ] Hermes Agent 설치 (`hermes --version`)
- [ ] Discord 계정 + 서버 생성 권한
- [ ] (선택) Paperclip 로컬 `http://127.0.0.1:3100`
- [ ] (선택) OpenCrab MCP endpoint
- [ ] GJC 또는 Cursor/Codex/Claude 중 개발 스택 준비

## 1. Discord 서버

1. Discord에서 서버 생성: 이름 예) `AI Company`
2. [CHANNELS.md](./CHANNELS.md) 카테고리·채널을 그대로 생성
3. 본인 계정에 `Board` 역할 부여

## 2. 봇 5개 생성 (1 프로필 = 1 봇)

[Discord Developer Portal](https://discord.com/developers/applications)에서 앱을 **5개** 만듭니다.

| 앱 이름 | Hermes profile | Intent |
|---------|----------------|--------|
| AI-CEO | `ceo` | Message Content, Server Members (선택) |
| AI-CTO | `cto` | 동일 |
| AI-Loop | `loop` | 동일 |
| AI-Growth | `growth` | 동일 |
| AI-Critic | `critic` | 동일 |

각 앱에서:

1. **Bot** → Add Bot → Reset Token → 토큰 복사 (한 번만 표시)
2. **Privileged Gateway Intents** → Message Content Intent ON
3. **OAuth2 → URL Generator**
   - Scopes: `bot`, `applications.commands`
   - Permissions: View Channels, Send Messages, Create Public Threads, Send Messages in Threads, Read Message History, Add Reactions, Manage Messages(선택)
4. 생성 URL로 서버에 초대

> 같은 토큰을 두 프로필에 넣으면 Hermes gateway가 충돌로 기동을 막습니다. **토큰은 절대 공유하지 마세요.**

## 3. Hermes 프로필 스캐폴드

```bash
./scripts/scaffold-profiles.sh
```

생성 위치:

```text
~/.hermes/profiles/
  ceo/     SOUL.md  config.yaml  .env
  cto/
  loop/
  growth/
  critic/
```

각 `.env`에 Discord 토큰만 채웁니다:

```bash
DISCORD_BOT_TOKEN=...   # 해당 프로필 전용
# 선택: TELEGRAM_BOT_TOKEN=...  # DM 핫라인만. 회의용 금지
```

## 4. 게이트웨이 기동

프로필마다 별도 gateway (권장 — soul/세션 완전 격리):

```bash
hermes -p ceo gateway start
hermes -p cto gateway start
hermes -p loop gateway start
hermes -p growth gateway start
hermes -p critic gateway start
```

또는 launchd/systemd로 상시 기동. 멀티 프로필 운영은 Hermes [multi-profile gateways](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways) 문서를 따릅니다.

## 5. Discord 설정 확인

각 `config.yaml`에 기본값:

```yaml
discord:
  require_mention: true
  auto_thread: true
  history_backfill: true
  history_backfill_limit: 50
  reactions: true

platform_toolsets:
  discord: [hermes-discord]
```

공유 채널에서는 **멘션 필수**. DM에서는 멘션 없이 1:1.

## 6. 스모크 테스트

1. `#board-you`에서 `@CEO 안녕. 너는 누구야?` → CEO만 응답, 자기 역할 언급
2. `#exec-meeting`에서 `@CEO @CTO @Growth 주간회의 테스트` → 멘션된 봇만 응답
3. CTO DM에서 `너는 Growth야?` → `아니요, CTO` 응답
4. Growth DM에서 CTO 대화 내용 모름 → 메모리 격리 OK

실패 시:

- 토큰 중복 → gateway 로그의 conflict 메시지
- 멘션 없이 전원 응답 → `require_mention: true` 확인
- 히스토리 무시 → `history_backfill` / Message Content Intent
- 그 외 증상은 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) 참고

## 7. Paperclip / OpenCrab (선택)

- Paperclip: 에이전트 adapter를 Hermes profile과 1:1 매핑
- OpenCrab: project명 = profile명, ingest는 `workmate-opencrab-ingest`만

## 8. GJC 번들 (개발 본체)

개발 세션 기본은 GJC `daily` (또는 Cursor 중심이면 Cursor를 primary, Codex/Claude를 satellite).

```bash
# GJC 쓰는 경우
curl -fsSL https://raw.githubusercontent.com/project820/gjc-multivendor-setup-guide/main/install.sh | bash
gjc --mpreset daily
```

역할 위임 규칙은 [ROUTING.md](./ROUTING.md)를 따릅니다.
