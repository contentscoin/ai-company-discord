# 트러블슈팅

증상 → 원인 → 해결 순서로 정리했습니다. 셋업 절차는 [SETUP.md](./SETUP.md), 채널·멘션 규칙은 [CHANNELS.md](./CHANNELS.md) 참고.

## 게이트웨이 · 토큰

| 증상 | 원인 | 해결 |
|------|------|------|
| 게이트웨이 기동 실패, 로그에 conflict | 두 프로필 `.env`에 **같은 봇 토큰** | 프로필당 전용 토큰인지 확인. Developer Portal에서 봇 5개가 각각 존재하는지 확인 |
| 봇이 온라인인데 아무 반응 없음 | Message Content Intent OFF | Developer Portal → Bot → Privileged Gateway Intents → **Message Content Intent ON** 후 게이트웨이 재시작 |
| 토큰 재발급 후에도 인증 실패 | `.env`에 예전 토큰 잔존 (토큰은 Reset 시 1회만 표시) | `~/.hermes/profiles/<name>/.env`의 `DISCORD_BOT_TOKEN` 갱신 |

## 채널 · 권한

| 증상 | 원인 | 해결 |
|------|------|------|
| 봇이 채널을 못 보거나 발언 못 함 | **Exec Role 미부착** — OAuth 초대만으로는 Role이 안 붙을 수 있음 | 서버 설정 → 멤버에서 각 봇에 Role 수동 부여 ([CHANNELS.md](./CHANNELS.md) 역할 표) |
| 스레드에서 봇이 응답 안 함 | Create/Send Messages in Threads 권한 누락 | OAuth URL 권한 재확인 후 재초대, 또는 채널 권한 overwrite 확인 |
| 과거 대화 맥락을 무시 | `history_backfill` OFF 또는 Intent 문제 | `config.yaml`의 `history_backfill: true` · `history_backfill_limit` 확인 |

## 멘션 · 응답 동작

| 증상 | 원인 | 해결 |
|------|------|------|
| 멘션 안 했는데 전원이 응답 | `require_mention: false`로 변경됨 | 각 프로필 `config.yaml`에서 `require_mention: true` 복구 |
| 봇끼리 서로 @멘션하며 핑퐁 (cascade) | SOUL의 "다른 봇을 이유 없이 @하지 않음" 규칙 훼손 | `profiles/*/SOUL.md` 금지 조항 확인·복구. 회의 규칙은 [MEETINGS.md](./MEETINGS.md) |
| 멘션된 봇 중 일부만 응답 | 미응답 봇의 게이트웨이 다운 또는 Role/권한 문제 | `hermes -p <name> gateway` 상태와 위 권한 표 확인 |

## config.yaml

| 증상 | 원인 | 해결 |
|------|------|------|
| CEO 프로필에서 YAML 파싱 오류 또는 `free_response_channels` 무시 | scaffold가 CEO `config.yaml` 말미에 붙인 **주석 예시 블록을 그대로 주석 해제** → 파일에 `discord:` 키가 두 번 존재 | 말미 블록을 지우고, **기존 상단 `discord:` 블록 안에** `free_response_channels: "<#standup 채널 ID>"` 한 줄만 추가 |
| standup 자동 포스트가 안 옴 | `free_response_channels` 미설정 또는 cron 미구성 | CEO config에 `#standup` 채널 ID 설정 ([CHANNELS.md](./CHANNELS.md) 예시). cron은 로드맵 Phase 2.3 참고 ([ROADMAP.md](./ROADMAP.md)) |

## 격리 검증

| 증상 | 원인 | 해결 |
|------|------|------|
| 한 봇이 다른 봇의 대화 내용을 앎 | 프로필 간 메모리 공유 — 같은 프로필로 두 봇 기동 의심 | 프로필당 별도 gateway인지, `~/.hermes/profiles/`에 5개가 각각 있는지 확인. [SETUP.md](./SETUP.md) §6 스모크 테스트 재실행 |
