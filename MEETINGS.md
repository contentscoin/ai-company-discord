# 회의 프로토콜

## A. 주간 Exec Meeting (동기)

**채널:** `#exec-meeting`  
**주기:** 주 1회 (예: 월 10:00 KST)  
**참석:** Board + `@CEO` `@CTO` `@Loop` `@Growth` (+ 이슈 있으면 `@Critic`)

### 진행

1. Board가 스레드 생성  
   `YYYY-Www · 안건 제목`
2. 첫 메시지 템플릿:

```text
@CEO @CTO @Loop @Growth
안건:
1) ...
2) ...
제약: 예산/마감/...
규칙: 멘션된 사람만 발언. 한 턴에 핵심 3줄. 다른 봇 이유 없이 @ 금지.
```

3. 발언 순서 권장  
   CTO(실행 현황) → Loop(품질/리스크) → Growth(성장) → CEO(종합) → Board(결정)
4. CEO 마감 블록:

```text
DECISION:
- ...
OPEN:
- ...
ACTIONS:
- @CTO : ...
- @Growth : ...
→ Paperclip 이슈로 이관
```

5. 지식: CEO가 결정 요약만 OpenCrab ingest 후보로 스테이징

## B. 데일리 Standup (비동기)

**채널:** `#standup`  
**방식:** cron → CEO 또는 전용 notifier가 질문 포스트

```text
Daily standup — YYYY-MM-DD
각 본부장: 어제 / 오늘 / 블로커 (각 1줄)
@CTO @Loop @Growth
```

`#standup`만 `free_response_channels`에 넣을 수 있음. 그 외 채널은 멘션 필수.

## C. Dev Sync

**채널:** `#dev`  
Cursor/Codex PR 링크 + `@Loop` 리뷰 요청 + 필요 시 `@Critic`.

## D. Growth Review

**채널:** `#growth`  
콘텐츠 초안 → Board 승인(`#approvals`) 후에만 발행.

## E. 당신과 1:1

봇 **DM** 사용. Discord 서버 공개 채널에 민감 전략을 장문 남기지 말 것.  
요약만 `#board-you`에 올리는 습관.

## F. 금지

- 텔레그램 그룹에서 임원 전원 소집
- 봇끼리 멘션 핑퐁 (cascade)
- 회의 원문 통째 OpenCrab 인제스트
- 한 봇 토큰으로 여러 프로필 기동
