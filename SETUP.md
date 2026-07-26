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
2. 카테고리·채널은 손으로 만들지 말고 **`companyctl bootstrap`으로 생성**합니다 (아래 §5.5). 설계 근거는 [CHANNELS.md](./CHANNELS.md) 참고
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

프로필 목록은 `templates/company.discord.json`(단일 진실원천)에서 읽습니다. 먼저 설정을 검증한 뒤 스캐폴드하세요:

```bash
python3 scripts/companyctl.py validate     # 설정 검증 (SOUL.md·채널·access 교차 확인)
./scripts/scaffold-profiles.sh             # = python3 scripts/companyctl.py scaffold
```

> Windows는 `.\scripts\companyctl.ps1 scaffold` — [WINDOWS.md](./WINDOWS.md) 참고.

생성 위치:

```text
~/.hermes/profiles/
  ceo/     SOUL.md  config.yaml  .env
  cto/
  loop/
  growth/
  critic/
```

각 `.env`에 Discord 토큰을 채우고, **두뇌(LLM)는 둘 중 한 방식**으로 연결합니다:

```bash
DISCORD_BOT_TOKEN=...    # 해당 프로필 전용
# 방식 A(구독 OAuth — API 키 불요, 권장): 아래 hermes auth add 참조
# 방식 B(API 키): ANTHROPIC_API_KEY=... 또는 OPENAI_API_KEY / OPENROUTER_API_KEY / XAI_API_KEY
# 선택: TELEGRAM_BOT_TOKEN=...  # DM 핫라인만. 회의용 금지
```

**방식 A — 구독 OAuth** (0.19.0 실측: `anthropic`·`openai-codex`·`xai-oauth`·`nous` 등 지원):

```bash
hermes auth add anthropic --type oauth       # Claude 구독 — 브라우저 승인
hermes auth add openai-codex --type oauth    # ChatGPT/Codex 구독
```

> **Discord 토큰은 접속만 시켜줍니다.** 두뇌(키 또는 OAuth + 모델) 없이 기동하면 봇이 온라인인데
> 침묵하는, Intent 문제와 헷갈리기 쉬운 증상이 됩니다 (라이브에서 실측). 구독 OAuth 경로 덕에
> 원질문의 "종량 API 없이 구독으로" 의도는 대화 축에서도 충족됩니다 ([ALIGNMENT.md](./ALIGNMENT.md) §1 정정).

**모델 선택 (필수, 프로필마다 1회)** — 위저드가 해당 프로필 config에 프로바이더·모델을 정확한
문법으로 써 줍니다 (0.19.0의 `model:`은 평평한 문자열 — 손으로 쓸 필요 없음):

```bash
hermes -p ceo model      # cto, loop, growth, critic 반복
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

## 5.5 채널 부트스트랩 + 헬스체크

카테고리·채널·역할은 `company.discord.json`(단일 진실원천)에서 자동 생성합니다. 손으로 만들 필요 없음.

```bash
export DISCORD_SETUP_TOKEN=...        # 셋업용 봇 토큰 (인자로 넘기지 않음)
python3 scripts/companyctl.py bootstrap --guild <서버ID>            # dry-run: 무엇을 만들지 출력
python3 scripts/companyctl.py bootstrap --guild <서버ID> --apply    # 실제 생성
```

- **멱등** — 이름으로 매칭, 이미 있으면 건너뜀, **삭제는 절대 안 함**. 재실행하면 "0 changes"
- 생성된 채널 ID는 `~/.hermes/ai-company/discord.map.json`에 기록 (레포 밖)
- `bootstrap`은 서버 역할(Board/Exec/Observer)·카테고리·채널과 카테고리 단위 권한을 만듭니다. 특정 봇만 보는 좁은 채널(예: `#dev`)은 봇 합류 후 멤버 단위로 좁히라는 안내를 함께 출력합니다

> `bootstrap`은 Manage Channels/Roles 권한이 필요합니다. 셋업용 봇에 임시로 부여했다가 완료 후 회수하세요. 토큰은 `DISCORD_SETUP_TOKEN` 환경변수로만 전달합니다.

설정 상태 점검:

```bash
python3 scripts/companyctl.py doctor            # 오프라인: 프로필 파일·토큰 중복·config 드리프트
python3 scripts/companyctl.py doctor --online   # + 토큰 유효성·채널 드리프트 (네트워크)
```

`doctor`는 토큰 값을 절대 출력하지 않고 SHA-256 해시로만 중복을 검사합니다. Windows는 `.\scripts\companyctl.ps1 doctor`.

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

- Paperclip: `npx -y paperclipai onboard --yes` → `hermes_local` 어댑터로 에이전트를 만들어 Hermes profile과 1:1 매핑. 어댑터는 배포판에 **내장**되어 있어 별도 설치가 필요 없습니다. 이슈 자동 등록까지 붙이려면 [PAPERCLIP.md](./PAPERCLIP.md) (실측 계약: 엔드포인트·스키마·함정)
- OpenCrab: project명 = profile명, ingest는 `workmate-opencrab-ingest`만

## 8. GJC 번들 (개발 본체)

개발 세션 기본은 GJC `daily` (또는 Cursor 중심이면 Cursor를 primary, Codex/Claude를 satellite).

```bash
# GJC 쓰는 경우
curl -fsSL https://raw.githubusercontent.com/project820/gjc-multivendor-setup-guide/main/install.sh | bash
gjc --mpreset daily
```

역할 위임 규칙은 [ROUTING.md](./ROUTING.md)를 따릅니다.
