# 역할 라우팅 — GJC × AI Company × Discord

GJC [routing-rules.md](https://github.com/project820/gjc-multivendor-setup-guide/blob/main/routing-rules.md)의 5역할을 **회사 본부장**에 매핑합니다.

## 1. 역할 매핑

| GJC 역할 | 무엇을 하나 | AI Company 주체 | Discord | 모델 힌트 (daily 번들) |
|----------|-------------|-----------------|---------|------------------------|
| `default` | 오케스트·정직성·집계 | **CEO** | `@CEO` | Anthropic Opus (또는 Cursor 보드 요약은 사람) |
| `executor` | 실제 구현 | **CTO** | `@CTO` | **Cursor 중심** + Codex satellite |
| `planner` | 설계·순서·수용기준 | CEO가 위임하거나 CTO 내부 | `#exec-meeting` / `#dev` | GPT Sol 계열 |
| `architect` | 대형 리뷰·구조 | **Loop** | `@Loop` | Gemini / Opus 장문 |
| `critic` | 독립 비평 | **Critic** | `@Critic` | **cross-family** (본체와 다른 벤더) |

Growth는 GJC 코딩 5역할 밖이지만 동등한 **본부**입니다 (SNS/콘텐츠).

## 2. Cursor 중심 개발부

```text
Board(사람)
  └─ CEO (Hermes) ──위임──▶ CTO (Cursor primary)
                               ├─ Codex (병렬 구현)
                               ├─ Claude (교차 리뷰 / Critic 좌석)
                               └─ Loop (DoD까지 verify)
```

규칙:

1. **이슈 owner는 Cursor(CTO)** — Codex/Claude는 subtask·comment만
2. 단순 1~2파일 → CTO 단독 (위임 과다 금지) — GJC와 동일
3. "구현해줘" 덩어리 → Codex satellite 가능
4. 머지 직전·고위험 → `@Critic` (+ cyber-cop / escalation 모드)
5. 매 쿼리 프로필 스왑 금지 — 모드 경계에서만 (`daily` ↔ `coding-sprint` ↔ `cyber-cop`)

## 3. Discord에서의 위임 신호

사람이 쓰는 트리거 문장 → 멘션 대상:

| 신호 | 멘션 |
|------|------|
| 전략·우선순위·정리 | `@CEO` |
| 구현·PR·레포 | `@CTO` |
| DoD·검증·루프 | `@Loop` |
| SNS·콘텐츠·캘린더 | `@Growth` |
| 머지·보안·확실해? | `@Critic` |
| 임원 전체 회의 | `@CEO @CTO @Loop @Growth` (+ 필요 시 `@Critic`) |

## 4. Council / Escalation (GJC 계약 이식)

### Exec Council (`#exec-meeting`)

1. Board가 의제 제시 + 관련 봇 멘션
2. 각 봇 **독립 발언** (다른 봇 답변을 베끼지 않음 — SOUL)
3. CEO가 raw 요점 보존하며 집계 (`DECISION:` / `OPEN:`)
4. CRITICAL dissent 1건은 다수결로 기각 불가 → Board gate

### War Room (`#war-room`)

GJC `escalation` 번들 대응:

1. 동일 과제 2회 실패 / Critic BLOCK / 비가역 작업
2. `@CEO @CTO @Critic` 소집
3. Critic raw verdict 요약 금지·원문 노출
4. 통과 못 하면 **사람(Board)만** 닫음

## 5. Paperclip 연동

Discord 결정은 곧바로 Paperclip 이슈로:

```text
DECISION: ...
OWNER: cto
DUE: ...
PAPERCLIP: create-issue
```

CEO(또는 Paperclip notifier)가 이슈 생성. Discord는 회의록, Paperclip은 실행 진실원천.

## 6. OpenCrab

회의 **원문** 금지. CEO가 정제 요약만 Workmate pending → safety → pack (`workflow` / `paperclip-company-context` / `qa`).

스테이징 전 **새니타이즈 린트 통과 필수**:

```bash
python3 scripts/companyctl.py lint --file summary.md   # 토큰·API키·이메일·스노우플레이크·원문 지표 검출
```

`BLOCK`(exit 1)이면 인제스트 금지 — 지목된 라인을 정제한 뒤 재실행. 통과해야 Workmate pending으로 넘깁니다. 린트는 시크릿 값을 출력하지 않고 종류·라인만 보고합니다.

## 7. 프로토콜

회의 마감 블록(DECISION/OPEN/ACTIONS)·Critic VERDICT·Loop PASS/FAIL의 정식 문법은 [PROTOCOLS.md](./PROTOCOLS.md). 마감 블록은 `companyctl decision`이 파싱해 정규화 JSON·Paperclip 이슈·주간 다이제스트로 흘려보냅니다.
