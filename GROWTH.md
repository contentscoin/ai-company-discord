# Growth 실행 계층 — social-ai-team-custom 연동 규약

Phase 6.3 ([ALIGNMENT.md](./ALIGNMENT.md) §4)의 산출물입니다. Growth 본부의 실행 계층으로
[social-ai-team-custom](https://github.com/contentscoin/social-ai-team-custom)을 연결하는 **규약 문서**입니다.

원칙은 다른 실행 축과 동일합니다: **스킬 스택은 저쪽 레포가 소유하고, 이 레포는 회의·승인 평면의
규약만 소유합니다** (재발명 금지 — 이 연동에 이 레포의 코드 추가는 0줄입니다). 아래 내용은
저쪽 레포의 팀 매뉴얼(`TEAM.md`)·OpenCrab 상수(`opencrab/opencrab.constants.yaml`)·pumasi
설정(`pumasi.config.yaml`)을 클론해 직접 읽고 쓴 것입니다.

## 1. 소유권 경계

| 평면 | 소유 | 실체 |
|------|------|------|
| 회의·승인 (Discord) | **이 레포** | `#growth`·`#approvals` 채널, [Growth SOUL](./profiles/growth/SOUL.md), 이 규약 |
| 콘텐츠 실행 | **social-ai-team-custom** | Claude Code 스킬 22종, `/content-director`(메인 스레드 디렉터) + 서브에이전트 4종(copywriter·creative-designer·video-producer·compliance-reviewer), pumasi 병렬 오케스트레이션, 렌더 레인(Nano Banana → ima2 → Codex), 데스크톱 앱 |
| 지식 (공유) | **OpenCrab** | 양쪽이 같은 SSOT를 씁니다 — social 쪽 `opencrab.constants.yaml`이 프로젝트/워크플로/팩 id를 고정 (§5) |
| 발행 | **Blotato** (+ 네이버 수동) | `/publisher`가 Blotato MCP로 스케줄링. 미연결 시 **하드스톱은 설계**이며 우회하지 않습니다. 네이버 블로그는 수동 발행(스택 로드맵에 명시) |

**실행 주체 주의**: 스킬 스택은 Hermes가 아니라 **Claude Code 세션**(클라이언트 작업 폴더 또는
저쪽 데스크톱 앱)에서 돕니다. Growth 봇(Hermes)은 실행하지 않습니다 — Discord 쪽 규약(요청
정형화 → 승인 상정 → 발행 기록)만 담당합니다. Discord와 작업 세션 사이의 전달은 사람(Board)이
합니다. `companyctl decision` 파이프라인과 같은 설계 선택입니다: **상주 리스너 없음, 회의/실행
평면 분리** ([PROTOCOLS.md](./PROTOCOLS.md) §1).

## 2. 왕복 흐름

```text
#growth (Discord)                 클라이언트 작업 폴더 (Claude Code)        #approvals (Discord)
─────────────────                 ─────────────────────────────────        ───────────────────
Board: "@Growth 8월 캠페인"
Growth: GROWTH BRIEF: 블록   ──▶  사람이 붙여넣기 → /content-director
                                  캘린더 → 카피 팬아웃 → 비주얼/릴스
                                  (스택 내부 게이트 1~6, 한국어)
                                  /kr-guardrail-check 판정표
                                  PASS/WARN/BLOCK              ──▶  Growth: READY TO PUBLISH: 블록
                                                                    Board: 승인 (= WARN 사인오프)
                                                                    CEO/Growth: DECISION 블록 마감
                                  /publisher → Blotato 제출   ◀──  (승인 후에만)
Growth: PUBLISHED: 기록      ◀──  (네이버는 수동 발행 체크리스트)
```

- 승인 마감은 **기존 DECISION 블록을 재사용**합니다 — `companyctl decision`이 그대로 파싱해
  결정 로그·Paperclip 이슈로 흘려보냅니다. 이 연동을 위한 새 파서는 없습니다.
- 스택 산출물(`outputs/…`)·컨텍스트(`context/*.md`)는 클라이언트 폴더에 남습니다. Discord에는
  **요약과 경로만** 올립니다 (원문 덤프 금지 — §5의 lint 게이트와 같은 이유).

## 3. 블록 규약 (사람이 읽는 텍스트 계약)

세 블록은 Growth SOUL의 `DRAFT:` / `READY TO PUBLISH:` 표기를 정식화한 것입니다.
기계 파싱 대상이 아니므로 (승인 마감의 DECISION 블록만 파싱됨) 필드는 규약이지 문법이 아닙니다.

### GROWTH BRIEF — `#growth`에서 요청 정형화

```text
GROWTH BRIEF: <클라이언트> <기간>
CHANNELS: threads 3, naver 1        ← 채널 × 건수
FORMAT: single image 2, reel 1      ← 스택 캘린더의 Format 값 그대로
NOTES: <훅·시즌·금지사항 등 자유 서술>
```

`CHANNELS`/`FORMAT` 값은 스택의 영어 계약 필드를 그대로 씁니다 — 스택 팀 모토
**"한국어로 말하고, 영어로 계약한다"** 를 이쪽에서도 존중합니다 (필드명·상태값·폴더 규약을
번역·재발명하지 않음).

### READY TO PUBLISH — `#approvals` 상정

```text
READY TO PUBLISH: <클라이언트> <월>
- 채널/건수: threads 3, naver 1
- 산출물: outputs/threads/*.md, outputs/naver/*.md   ← 클라이언트 폴더 상대경로
- 컴플라이언스: PASS 3 / WARN 1 (사유 요약) / BLOCK 0
- 스케줄: Blotato <제출 예정 시각> · naver 수동
```

상정 규칙:

- `/kr-guardrail-check` 판정표 **없이 상정 금지** — 컴플라이언스 줄은 필수입니다
- `BLOCK`이 1건이라도 있으면 상정 불가 (스택 규약대로 재작업 후 재검사)
- `WARN`은 사유를 블록 안에 요약해야 하며, Board의 `#approvals` 승인이 곧 **WARN 사인오프**입니다

### PUBLISHED — 발행 기록 회신

```text
PUBLISHED: <클라이언트> <월>
- Blotato: <스케줄 id 또는 확인 링크>
- 수동: naver 1건 (발행 URL)
```

발행 후 `#growth` 스레드에 회신합니다. 이 기록이 있어야 월말 `/social-performance-review`
결과와 대조할 수 있습니다.

## 4. 승인 게이트 정합 — 이중 승인 방지

스택은 자체적으로 **인간 승인 게이트 8개**를 메인 스레드에서 한국어로 묻습니다(팀 매뉴얼 §4).
운영자가 곧 Board(같은 사람)이므로 이를 Discord로 복제하면 같은 질문을 두 번 받게 됩니다.
경계는 다음과 같습니다:

| 스택 게이트 | 처리 위치 | 근거 |
|-------------|-----------|------|
| 1 캘린더 · 2 카피 · 3 제작 배정 · 4 브리프 · 5 비주얼/영상 · 6 컴플라이언스(판정 수령) | **작업 세션 내부** (스택이 묻는 그대로) | 제작 중간 판단 — 회의 평면으로 승격할 가치보다 왕복 비용이 큼 |
| **7 발행 스케줄 확정** | **Discord `#approvals`** (READY TO PUBLISH) | Growth SOUL의 "Board 승인 없이 외부 발행 금지"의 실체화 — 외부로 나가는 유일한 게이트 |
| 8 리뷰 → 다음 달 | 작업 세션 내부, 요약만 `#growth` | 차기 계획 입력 |

- 게이트 7을 `#approvals`로 승격했으므로, 작업 세션의 `/publisher`는 **Discord 승인이 난 뒤에만**
  실행합니다. 스택 입장에서는 게이트 7의 답이 "예"로 이미 정해진 상태로 도달하는 것뿐이며,
  스택 수정은 없습니다.
- Blotato 미연결 하드스톱(스택의 영어 원문 메시지)은 그대로 존중합니다. 이때의 대안(수동 발행
  핸드오프)도 READY TO PUBLISH 블록의 `스케줄:` 줄에 "수동"으로 명시해 승인받습니다.

## 5. OpenCrab 접점 (공유 SSOT)

양쪽이 이미 같은 지식 평면을 씁니다 — 이것이 이 연동의 마찰이 낮은 이유입니다
([ALIGNMENT.md](./ALIGNMENT.md) §2 격차 ③).

- social 쪽 `opencrab/opencrab.constants.yaml`이 프로젝트(`threads_top_exposure_research_ko`),
  워크플로(Threads Evidence Writing), 팩 4종(golf/development/it/naver-seo), 비주얼 자산
  카테고리(`master_sheet`/`character_sheet`/`content_base`)의 **id를 고정**합니다.
  이 상수 파일의 소유는 저쪽이며, 이 레포는 참조만 합니다.
- 이 레포의 인제스트 규칙이 Growth 산출물에도 그대로 적용됩니다: 회의·고객 **원문 금지**,
  재사용 레슨 요약만, 스테이징 전 `companyctl lint` 통과 필수 ([ROUTING.md](./ROUTING.md) §6).
- 스택의 `opencrab_ingest`(pumasi route → MCP)는 클라이언트 비주얼 자산을 팩으로 올리는
  **저쪽 평면의 일**입니다. 이 레포의 lint는 Discord를 거치는 요약에만 관여합니다.

## 6. pumasi ↔ GJC 동형성 (관측 기록)

스택의 pumasi 오케스트레이션은 이 레포의 GJC 위성 구조와 동형입니다 — 별도 통합 작업이
필요 없다는 근거로 기록합니다:

| | 개발부 (GJC/[ROUTING.md](./ROUTING.md)) | Growth (pumasi, 실측) |
|---|---|---|
| 지휘자 | CEO/CTO (메인) | `/content-director` (메인 스레드) |
| 위성 라우팅 | Codex/Claude satellites | route별 엔진 우선순위: `calendar:[claude]`, `copy_threads:[claude,codex]`, `visual_render:[codex,ima2]` … |
| 게이트 | DoD·Critic VERDICT | 단계별 `gates`(산출물 존재 검사) + 인간 게이트 8개 |
| 지식 | OpenCrab (lint 게이트) | OpenCrab (`opencrab_ingest` route → MCP) |

## 7. 비용 경로

[COSTS.md](./COSTS.md)의 이원 구조에 Growth 실행 축이 추가됩니다. CTO의 커서 구독 경로와
동형으로, **구독/OAuth 계열이 기본**입니다:

| 노동 | 과금 주체 |
|------|-----------|
| 콘텐츠 제작 실행 (스킬 스택) | Claude Code 구독 (+ pumasi가 쓰면 Codex CLI) |
| 이미지 렌더 | 1순위 Nano Banana(MCP) → 2순위 ima2(ChatGPT/Grok OAuth, **API 키 불요**) → 3순위 Codex 렌더(`OPENAI_API_KEY` — 이 경로만 API 과금) |
| 영상 실행 | ima2 + Grok video (OAuth) |
| 발행 | Blotato 구독 |
| Growth 봇의 Discord 대화 | LLM API 키 (기존 프로필 구조 그대로) |

## 8. 하지 않는 것

- 스킬·SOP·서브에이전트 **벤더링/포크 금지** — 스택 갱신은 저쪽 레포에서 일어나고, 이 문서는
  계약 표면(블록·게이트·SSOT id)만 참조합니다
- Growth 봇이 스킬을 직접 실행하는 브리지 **만들지 않음** — 평면 분리 유지
- 스택의 영어 계약 필드(`VISUAL DIRECTION`, `BLOTATO FLAG`, `PASS`/`WARN`/`BLOCK`,
  `outputs/*` 규약) **번역·변형 금지**
- Blotato 하드스톱 우회 금지, 네이버 자동 발행 시도 금지 (스택 로드맵의 전제가 충족될 때까지)
- 고객 원문·개인정보를 Discord·OpenCrab에 올리지 않음 (lint 게이트 선행)

## 9. 첫 왕복 체크리스트 (Phase 6.3 DoD)

콘텐츠 1건이 요청 → 발행 기록까지 왕복하면 완료입니다. 스킬 스택 설치 환경(사용자 로컬)이
필요하므로 이 저장소의 CI로는 검증할 수 없고, 체크리스트로 남깁니다:

1. `#growth`에서 `@Growth` 멘션으로 요청 → **GROWTH BRIEF** 블록 회신 확인
2. 클라이언트 폴더에서 `/content-director` 실행, 브리프 반영 (스택 설치: 저쪽 `install.sh`)
3. 게이트 1~6 통과, `/kr-guardrail-check` 판정표 확보
4. `#approvals`에 **READY TO PUBLISH** 상정 (컴플라이언스 줄 포함)
5. Board 승인 → **DECISION 블록** 마감 → `companyctl decision`으로 로그 적재 확인
6. `/publisher` 실행(또는 수동 발행) → `#growth`에 **PUBLISHED** 기록
7. (선택) 재사용 레슨 요약 → `companyctl lint` 통과 → OpenCrab 스테이징
