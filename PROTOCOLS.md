# 프로토콜 스펙 (PROTOCOL v1)

회의·리뷰에서 쓰던 산문 포맷을 기계가 읽을 수 있는 스펙으로 승격한 문서입니다.
`company.discord.json`의 `protocolVersion`이 이 문서의 버전을 가리킵니다.
`scripts/companyctl.py`의 `decision` 서브커맨드가 아래 DECISION 블록을 파싱합니다.

## 1. 회의 마감 블록 (DECISION / OPEN / ACTIONS)

CEO가 [MEETINGS.md](./MEETINGS.md) §A.4에서 쓰는 마감 블록의 정식 문법입니다.

### 문법 (EBNF)

```ebnf
close-block  = decision-sec , [ open-sec ] , [ actions-sec ] ;
decision-sec = "DECISION:" , NL , 1*bullet ;
open-sec     = "OPEN:"     , NL , *bullet ;
actions-sec  = "ACTIONS:"  , NL , *action ;
bullet       = "-" , SP , text , NL ;
action       = "-" , SP , owner , SP , ":" , SP , text , [ due ] , NL ;
owner        = "@" , role-name | role-id ;   (* @CTO, @Growth, cto, growth *)
due          = "(DUE:" , SP , date , ")" ;
```

- `owner`는 `company.discord.json`의 role id(`cto`) / 대문자(`@CTO`) / title(`CTO`)로 쓰며, `board`(사람)도 허용
- 파서가 owner를 canonical role id로 정규화 (`@Growth` → `growth`)
- 알 수 없는 owner는 경고 후 원문 소문자로 보존 (데이터 유실 없음)

### 예시

```text
DECISION:
- MRR 목표를 8월 말까지 3천으로 상향
- 신규 채용 보류
OPEN:
- 가격 정책 재검토 필요
ACTIONS:
- @CTO : 결제 파이프라인 버그 수정 (DUE: 2026-08-01)
- @Growth : 8월 캠페인 초안
```

### 사용

```bash
# 붙여넣기 → 정규화 JSON (+ 결정 로그 append)
pbpaste | python3 scripts/companyctl.py decision              # macOS
python3 scripts/companyctl.py decision --file block.txt       # 파일

# ACTIONS를 Paperclip 이슈로 (부재 시 이슈 JSON으로 강등)
python3 scripts/companyctl.py decision --to-paperclip --file block.txt

# 파싱만, 로그 안 남김
python3 scripts/companyctl.py decision --dry-run --file block.txt
```

입력은 **사람이 복사해 넣은 텍스트만** 받습니다 — Discord 상주 리스너 없음(회의/실행 평면 분리 유지). 진실원천은 Paperclip이고, 로컬 `~/.hermes/ai-company/decisions.ndjson`은 오프라인에서도 주간 브리핑을 뽑기 위한 경량 미러입니다.

## 2. 컴팩트 결정 (OWNER / DUE / PAPERCLIP)

[ROUTING.md](./ROUTING.md) §5의 단건 결정 지시 형식도 같은 파서가 받습니다.

```text
DECISION: OpenCrab 스키마 확정
OWNER: loop
DUE: 2026-07-31
PAPERCLIP: create-issue
```

`OWNER`(+`DUE`)만 있고 `ACTIONS` 섹션이 없으면, 마지막 `DECISION`을 담당·기한과 묶어 액션 1건으로 합성합니다. `PAPERCLIP:` 지시는 파서가 무시하고, 실제 이슈화는 `--to-paperclip`이 담당합니다.

## 3. Critic 판정 (VERDICT)

[profiles/critic/SOUL.md](./profiles/critic/SOUL.md)의 판정 포맷입니다. CEO는 이 원문을 요약·은폐하지 않습니다(GJC council 계약).

```text
VERDICT: CLEAR | WATCH | BLOCK
BLOCKERS:
- path:line — ...
WATCH:
- ...
NO-FINDING RATIONALE: (해당 시)
```

- `BLOCK`이면 최소 1건의 `path:line`(또는 재현 절차) 근거 필수
- `CLEAR`인데 근거 없는 LGTM 금지 → `NO-FINDING RATIONALE` 명시

## 4. Loop DoD 리포트 (PASS / FAIL)

[profiles/loop/SOUL.md](./profiles/loop/SOUL.md)의 리포트 포맷입니다.

```text
PASS | FAIL
- 실패 항목: ...
- 다음 액션 1개: ...
```

insane-loop 규칙: 모든 VALIDATION pass + blocking assumption 0 → PASS. 같은 항목 2회 실패 → 접근 변경, 3회 연속 → Board 게이트 질문 1개.

## 버전

`PROTOCOL v1`. 포맷을 바꾸면 이 문서와 `company.discord.json`의 `protocolVersion`, 그리고 `companyctl` 파서를 함께 올립니다.
