# Discord 채널 설계

서버명 예: `AI Company`

## 역할 (Discord Roles)

| Role | 부여 대상 | 권한 |
|------|-----------|------|
| Board | 사람(창업자) | 전체 채널 읽기/쓰기, 관리 |
| Exec | CEO·CTO·Loop·Growth·Critic 봇 | 업무·회의 채널 |
| Observer | (선택) 게스트 | 읽기 전용 |

봇 계정에도 위 Role을 수동 부여하세요 (Developer Portal 초대만으로는 Role이 안 붙을 수 있음).

## 카테고리 · 채널

### 📌 board

| 채널 | 용도 | 참석 |
|------|------|------|
| `#board-you` | 당신 ↔ CEO 전략 1:1에 가까운 공개 보드 | Board + CEO |
| `#approvals` | 예산·채용·배포·발행 승인 | Board + CEO (+ 해당 본부장) |

### 🗣 meetings

| 채널 | 용도 | 참석 |
|------|------|------|
| `#exec-meeting` | 주간/임시 임원 회의 (스레드=안건) | Board + 전 Exec |
| `#standup` | 매일 비동기 스탠드업 | 전 Exec |
| `#war-room` | 장애·위기·비가역 결정 | Board + CEO + CTO + Critic |

### 🛠 work

| 채널 | 용도 | 참석 |
|------|------|------|
| `#dev` | 구현·PR·Cursor/Codex 알림 | CTO + Loop + Critic |
| `#loop` | DoD·VALIDATION·리뷰 루프 | Loop + CTO + Critic |
| `#growth` | SNS·캘린더·콘텐츠 | Growth (+ CEO) |
| `#paperclip-feed` | Paperclip 이슈 알림 미러 (선택) | Exec |

### 🧠 knowledge

| 채널 | 용도 | 참석 |
|------|------|------|
| `#ingest-review` | OpenCrab manual-review 후보 논의 | Board + CEO |
| `#briefs` | 주간 CEO 브리핑 아카이브 | Board + Exec |

### 🔒 private (선택 카테고리)

DM으로 충분하면 생략. 필요 시 `#dm-ceo-bridge` 등 만들지 말고 **봇 DM**을 씁니다.

## 멘션 · cascade 규칙

1. 공유 채널: **반드시 `@봇` 멘션**으로만 응답 (`require_mention: true`)
2. 한 메시지에 여러 봇을 멘션하면 **멘션된 봇만** 응답
3. 봇은 다른 봇을 **이유 없이 @하지 않음** (SOUL에 명시)
4. 회의 스레드에서는 발언 순서: CEO 정리 → 본부장 → Critic(필요 시) → Board 결정
5. `#standup`만 예외로 cron 자동 포스트 허용 (free_response는 standup 채널 ID만)

```yaml
# ceo/config.yaml 예시 — standup만 자유 응답
discord:
  require_mention: true
  free_response_channels: "123456789012345678"  # #standup 채널 ID
```

## 스레드 사용법

- `#exec-meeting`에서 안건마다 **스레드** 생성: `2026-W30 · MRR 점검`
- `auto_thread: true`면 @멘션 시 자동 스레드
- 결정 사항은 스레드 마지막에 CEO가 `DECISION:` 블록으로 요약 → Paperclip 이슈화

## 텔레그램 정책

| 허용 | 금지 |
|------|------|
| 각 봇 ↔ 당신 DM | 그룹에서 다자 회의 |
| 긴급 ping | 프로필 공유 토큰 |
| 일일 요약 푸시 | OpenCrab 원문 덤프 |

회의·협업의 **기본 채널은 Discord**입니다.
