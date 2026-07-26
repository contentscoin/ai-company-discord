# 원질문 정합성 감사 + Phase 6 고도화 기획

이 프로젝트의 출발점은 다음 질문이었습니다:

> Cursor의 API를 이용해서 Hermes/Paperclip에 연결하여 **커서 요금제를 통해 프로필이 작동**하도록 할 수 있어?
> (레포 8개 분석 →) Hermes와 Paperclip을 활용한 AI company building 프로젝트를 기획해봐.
> **개발 + SNS 운용 + Loop 엔지니어링을 총체적으로 활용해 1인 사업을 하게 해주는 툴.** GJC 가이드 참고, Discord 기본 세팅.

현재 산출물(PR #1~#5)을 이 원질문에 대조해 감사한 결과입니다. 원질문의 레포 8개를 전부 실제로 열어 확인했습니다(1개는 비공개라 세션에 추가 후 클론).

## 1. 원질문의 핵심 답 — 커서 요금제로 프로필이 돌아가는가

**전 프로필은 불가, CTO의 개발 노동은 가능합니다.** 두 갈래로 갈립니다.

| 갈래 | 가능 여부 | 근거 |
|------|-----------|------|
| Hermes 프로필 5개의 **대화/오케스트레이션**(회의 발언, DECISION 집계 등)을 커서 요금제로 | ❌ | Cursor는 범용 chat-completions LLM API를 공식 제공하지 않습니다. OpenAI 호환 Cloud API는 Cursor 포럼의 **피처 리퀘스트 상태**입니다. Hermes 프로필은 LLM API 키(Anthropic/OpenAI/OpenRouter)가 필요하고 이 비용은 커서 플랜으로 대체되지 않습니다 |
| CTO의 **코딩 실행**(이슈 → 구현 → PR)을 커서 요금제로 | ✅ | Cursor **Cloud/Background Agents API**가 존재하며, 그 사용량은 별도 상품이 아니라 **플랜의 크레딧 풀에 과금**됩니다(예: Pro의 월 $20 크레딧, 소진 시 API 단가 초과분). 저장소를 지정해 에이전트를 띄우고 PR을 만들게 하는 프로그래매틱 위임이 가능합니다 |

비공식 우회(예: Cursor Composer를 OpenAI 호환으로 감싸는 `standardagents/composer-api` 프록시)는 존재하지만 **ToS 리스크로 비권장**합니다.

**현재 프로젝트와의 정합**: [ROUTING.md](./ROUTING.md)는 처음부터 "이슈 owner는 Cursor(CTO), Codex/Claude는 위성"으로 설계돼 있어 **구조는 원질문의 정답 방향이었습니다.** 빠져 있는 것은 그 관례를 실제 API 호출로 실체화하는 계층입니다(→ Phase 6.2).

*(주의: cursor.com/docs는 이 환경의 프록시에서 403이라 1차 문서를 직접 읽지 못했고, 위 판정은 2026년 커뮤니티·요금제 문서 기준입니다. 6.2 착수 시 API 키 발급과 함께 실측이 첫 단계입니다.)*

## 2. 원질문 레포 8개 감사

| 레포 | 실체 (전부 실제 확인) | 현재 반영 | 판정 |
|------|----------------------|-----------|------|
| `paperclipai/paperclip` | 실행 진실원천. `paperclipai@2026.722.0` | ✅ compose 서비스, DECISION 파이프라인 | 반영됨 |
| `NousResearch/hermes-agent` | 직원 런타임. 0.19.0 실측 완료 | ✅ 핵심 — [RUNTIME-CONTRACT.md](./RUNTIME-CONTRACT.md) | 반영됨 |
| `project820/gjc-multivendor-setup-guide` | 역할↔모델 라우팅 규범 | ✅ ROUTING.md 5역할 매핑 | 반영됨 |
| `akan-team/akanjs` | 풀스택 TS 프레임워크 | ✅ devCenter 후보 (status: candidate) | 반영됨 |
| `NousResearch/hermes-paperclip-adapter` | **공식 브리지** — Paperclip **플러그인**(`adapterType: "hermes_local"`). Paperclip 태스크 배정 → Hermes CLI 스폰·실행 → 비용/세션/구조화 출력 회수. 코멘트 웨이크·`--resume` 세션 지속. MIT | ❌ | **격차 ①** — 우리 `decision --to-paperclip`은 회의록→이슈 방향뿐. 이슈→실행 루프는 공식 어댑터가 이미 존재하는데 미채택 |
| `contentscoin/hermes-ceo-console-installer` | **이미 존재하는 데스크톱 설치 파일** — Electron, v0.1.0-alpha.27(51커밋), Windows EXE(WSL2)/macOS DMG. Hermes Agent + 커스텀 WebUI(`:8788`) + Paperclip(`:3100`) + Telegram/Codex/OpenCrab/Neo4j 선택 번들 | ❌ | **격차 ②(기획 충돌)** — [DESKTOP.md](./DESKTOP.md)가 이 자산을 모른 채 신규 앱을 설계함 |
| `contentscoin/social-ai-team-custom` | **SNS 실행 스택** — Claude Code 스킬 22종(네이버 블로그/클립·카카오·Threads·X·LinkedIn·릴스), 한국어 팀 모드(/content-director + 4 서브에이전트), pumasi 병렬 오케스트레이션(Codex/Claude CLI 라우팅), Electron 컨트롤 타워, **OpenCrab SSOT 바인딩** | ❌ | **격차 ③** — 현재 Growth는 SOUL+채널뿐, 실행 계층 미연동. 이미 OpenCrab을 공유하므로 통합 마찰이 낮음 |
| `garrytan/gbrain` | **Hermes용으로 설계된** 지식·기억 계층(27K★). 하이브리드 검색+지식그래프+에이전트 메모리, MCP 30+ 도구 | ❌ | 의도적 대체 — 지식 평면으로 OpenCrab을 선택. 결정은 타당하나 **후보로 기록**해야 함 |
| `janfoeh/paperclip-optimizer` | **동명이인** — Rails Paperclip(파일 첨부 젬)용 이미지 최적화. 2021년 아카이브 | — | 제외가 정답. AI Paperclip과 무관 |

## 3. 기획 건전성 판정

**구조는 건전합니다.** Discord 회의 평면, 5역할 SOUL, GJC 라우팅, SSoT, 평면 분리(회의/실행/지식), Cursor-CTO 관례 — 전부 원질문의 뼈대와 일치하고, PR #1~#5에서 검증 도구까지 갖췄습니다.

**그러나 원질문의 3대 실행 축 대비 현재는 "회의실만 지어진 상태"입니다:**

| 원질문 축 | 현재 상태 | 빠진 것 |
|-----------|-----------|---------|
| 개발 (Cursor 중심) | 관례만 (ROUTING.md 문장) | Cloud Agents API 연동 — 위임이 실제 PR로 이어지는 루프 |
| SNS 운용 | SOUL + `#growth` 채널만 | social-ai-team-custom 실행 스택 연동 |
| Loop 엔지니어링 | ✅ SOUL + DoD 규약 + PROTOCOLS.md | (충족) |
| 실행 진실원천 | 이슈 **생성**까지만 | 이슈 → Hermes **실행** 루프 (공식 어댑터 미채택) |
| "툴"(설치 파일) | DESKTOP.md 기획 | **기존 installer와의 통합 결정** |

## 4. Phase 6 — 실행 계층 연결 (고도화 기획)

원칙은 지금까지와 동일합니다: 재발명 금지, 위임 우선, 실측 우선.

### 6.1 실행 루프 완성 — hermes_local 어댑터 채택 (M) — **실측 완료, 코드 반영됨**

실제로 `paperclipai@2026.722.0`을 기동해 측정한 결과 ([PAPERCLIP.md](./PAPERCLIP.md)):

- **어댑터 등록 절차는 불필요** — `hermes_local`/`hermes_gateway`는 npx 배포판에 **내장** (`GET /api/adapters` 실측: 14종 전부 builtin·loaded). hermes-paperclip-adapter README의 `registry.ts` 편집은 소스 체크아웃 전용
- `companyctl decision --to-paperclip`이 가짜 API(`POST /issues` + `body/owner/due` 필드)를 쓰고 있었음을 실측으로 확인 — 실제 경로 `POST /api/companies/{id}/issues`로 수정, 페이로드를 측정된 스키마(`title/description/priority/assigneeAgentId`)로 교체. 스키마가 비엄격이라 옛 페이로드는 **조용히 본문이 유실**되는 빈 이슈를 만들었음
- `roles[].paperclipAgentId`(선택)로 ACTION owner → 이슈 assignee 매핑. 라이브 왕복: 한국어 DECISION 블록 → `AIC-5`에 hermes_local 에이전트 uuid가 assignee로 기록됨
- **부수 실측**: Paperclip에 `cursor`(모델 39종)·`cursor_cloud` 어댑터도 내장 — 6.2의 경로 후보가 하나 더 생김 (아래)
- 남은 DoD: 이슈 배정 → Hermes가 **실행**하고 결과·비용이 이슈로 돌아오는 왕복 (게이트웨이 + LLM 키가 있는 환경에서 1회 실측 필요)
- 역할 분담(유지): **회의록→이슈는 이 레포**(`companyctl decision`), **이슈→실행→결과 회수는 Paperclip 내장 어댑터**. 우리가 실행 루프를 자체 구현하지 않음

### 6.2 Cursor Cloud Agents 연동 — CTO 위임의 실체화 (M)

- 1단계(실측): Cursor 대시보드에서 API 키 발급 → 에이전트 생성/상태 조회/과금 단위를 실측해 `CURSOR-CONTRACT.md`로 기록 (verify-runtime과 같은 방법론 — 문서가 403이므로 측정이 곧 문서)
- 2단계: `companyctl delegate --repo <r> --task "<이슈>"` → Cloud Agent 생성 → PR 링크를 `#dev`에 회신하는 최소 루프
- 비용 규약: 이 경로의 과금은 **커서 플랜 크레딧**(원질문의 의도 충족). 프로필 대화는 여전히 LLM 키 — [COSTS.md](./COSTS.md)에 이원 구조 명시
- DoD: 위임 1건이 실제 PR로 돌아오는 왕복 실측
- **진행 상황**: 도구는 구현됨 — `companyctl verify-cursor`(표면 실측→`CURSOR-CONTRACT.md`)와 `companyctl delegate`(기본 dry-run, `--apply`시에만 크레딧 소모·브랜치 푸시). 단 **이 샌드박스의 이그레스 정책이 `api.cursor.com`을 차단**해 실측은 미완 — 환경 네트워크 정책에서 `api.cursor.com`을 허용하거나 로컬에서 `CURSOR_API_KEY=... companyctl verify-cursor --out CURSOR-CONTRACT.md` 1회 실행 필요
- **6.1 실측이 연 새 경로 → 측정 완료**: Paperclip 내장 `cursor` 어댑터의 과금 로직을 dist에서 직접 확인 ([PAPERCLIP.md](./PAPERCLIP.md) §5.1) — `CURSOR_API_KEY` 없이 `agent login`(Cursor CLI)만으로 인증하면 `billingType: "subscription"`, biller `"cursor"`. **즉 원질문의 "커서 요금제로 작동"은 CTO 실행 축에서 API 키 없이 성립합니다.** `cursor_cloud`는 반대로 `CURSOR_API_KEY` 필수(실측). 권장 구도: CTO 에이전트 = `adapterType: "cursor"` + `agent login` (구독 과금), `companyctl delegate` = 원격/보조 경로 (API 과금, `api.cursor.com` 필요). 남은 검증은 사용자 환경에서 실행 왕복 1회 — 이 샌드박스에는 `agent` CLI가 없음

### 6.3 Growth 실행 계층 — social-ai-team-custom 연동 (M) — **규약 완성, 왕복만 사용자 몫**

- Growth SOUL에 위임 규약 추가: `#growth`의 요청 → social-ai-team 스킬 실행(캘린더/카피/비주얼) → 산출물 요약을 `#approvals`로 → 승인 후 publisher
- 접점은 이미 있음: **양쪽 다 OpenCrab을 SSOT로 사용** (social 쪽 `opencrab.constants.yaml` 확인). pumasi가 Codex/Claude CLI를 라우팅하므로 GJC 위성 구조와도 동형
- 이 레포에는 규약·채널 흐름만 추가 — 스킬 스택 자체는 저쪽 레포가 소유 (재발명 금지)
- DoD: 콘텐츠 1건이 `#growth` 요청 → 초안 → `#approvals` 승인 → 발행 기록까지 왕복
- **진행 상황**: [GROWTH.md](./GROWTH.md) 작성 완료 — 저쪽 레포의 팀 매뉴얼·OpenCrab 상수·pumasi 설정을 클론에서 직접 읽고 규약을 그 실체에 맞춤. 블록 3종(GROWTH BRIEF / READY TO PUBLISH / PUBLISHED)은 텍스트 규약이고 승인 마감은 기존 DECISION 파서 재사용(새 코드 0줄). 스택의 인간 게이트 8개 중 **게이트 7(발행)만 `#approvals`로 승격**해 이중 승인을 피함. `company.discord.json`에 `growthCenter` 기록(스키마 반영). 남은 것은 DoD 왕복 1회 — 스킬 스택 설치 환경(사용자 로컬)이 필요해 CI로는 불가, GROWTH.md §9 체크리스트로 남김

### 6.4 데스크톱 전략 단일화 — **결정 완료: B안** (Board, 2026-07-25)

**진행 상황**: Board 결정 자료 [DESKTOP-DECISION.md](./DESKTOP-DECISION.md) 작성(질문 3개, 자산 실체 비교, A안 조건부 권고, 결정 무관 즉시 조치 4건) → **Board가 B안(신규 Control Room 앱) 채택**. 권고(A)와 결정(B)이 갈렸고, 둘 다 기록에 남김 — 이 게이트의 정상 동작. DESKTOP.md가 유효 로드맵으로 승격(규율 포함: Phase 0 실측 전 GUI 코드 금지). **2026-07-26 개정: installer는 아카이브하지 않고 독립 프로젝트로 존속**. 같은 날 실측 정정: NOTICE "부채"는 반증됨(위 §6.4 정정 인용구 — 번들이 아니라 소스 설치). installer 쪽 반영은 그 프로젝트 자율 — 참고 레포에는 PR을 넣지 않는다는 작업 경계 확정([CLAUDE.md](./CLAUDE.md)). 후속은 DESKTOP-DECISION.md §7 B-경로 백로그(Phase 0 실측 → 앱 레포 신설 → Phase 1~5). 이 레포의 몫(--json 계약, verify-runtime)은 이미 출하됨.

[DESKTOP.md](./DESKTOP.md)는 `hermes-ceo-console-installer`(Electron, alpha.27, 이미 Win/mac 산출물 존재)를 모른 채 신규 Python+pywebview 앱을 설계했습니다. 두 자산의 관계를 정해야 합니다:

| 선택지 | 장점 | 단점 |
|--------|------|------|
| **A. 기존 installer 확장** (권고) — 5-프로필 Discord 온보딩·Control Room 화면을 installer의 WebUI에 추가 | 이미 서명·배포 파이프라인의 절반을 넘음(alpha.27), Hermes+Paperclip 번들 경험 보유, 조직 자산 재사용 | Electron+WSL2 유지비, DESKTOP.md의 "60MB 얇은 셸" 목표 포기 |
| B. DESKTOP.md 신규 앱 강행 | 얇음, Python 단일 | 조직에 설치 파일 2개 병존, alpha.27의 학습을 버림 |

**어느 쪽이든 즉시 적용되는 발견**: 기존 installer는 Paperclip을 번들하므로 [DESKTOP.md](./DESKTOP.md) BREAK 1의 `embedded-postgres` 제3자 라이선스 리스크(PostgreSQL 18.4 + 라이브러리 8종 고지 의무)가 **그 레포에 오늘 이미 적용**됩니다. 선택과 무관하게 통지 필요.

> **2026-07-26 실측 정정**: 위 문장은 반증됐습니다. installer 레포를 클론해 확인한 결과 릴리스 자산은 FMG 통합 계층+Electron 셸뿐(팩 zip 26파일 313KB)이고, Paperclip은 `mode: "local-fmg-source-install"`로 **첫 실행 시 핀 커밋에서 소스 설치**됩니다 — embedded-postgres 페이로드는 사용자의 패키지 매니저가 받는 것이지 이 레포가 재배포하지 않습니다. 즉 installer는 처음부터 B안이 처방한 "업스트림 미번들 + 첫 실행 확보" 패턴이었고, **고지 부채는 현 배포 형태에 존재하지 않습니다**. 배포 경계를 NOTICE에 명문화하자는 제안은 installer#1로 올렸다가 **Board의 작업 경계 지시(참고 레포에 PR 금지 — [CLAUDE.md](./CLAUDE.md))에 따라 닫았습니다** — 제안 텍스트는 닫힌 PR에 남아 있고, 반영 여부는 그 프로젝트 자율입니다.

### 6.5 gbrain 포지션 기록 (S) — **완료**

지식 평면은 OpenCrab 유지(이미 social 스택과 공유). gbrain은 **Hermes 프로필의 장기 기억 후보**로 `company.discord.json` references에 기록만 — 채택 결정은 OpenCrab으로 부족해질 때.

**진행 상황**: `knowledge.candidates`에 구조화 기록 완료 (devCenter.frameworks의 candidate 패턴과 동형, 스키마 반영). references에는 이미 있었고, 이제 "왜 안 쓰는지·언제 재검토하는지"가 SSoT에 남음.

### 제외 확정

`janfoeh/paperclip-optimizer` — Rails 이미지 젬(동명이인, 아카이브됨). 원질문 목록에 있었으나 무관함을 확인했습니다.

## 5. 우선순위 제안

**6.1 → 6.2 → 6.3 → 6.4(결정만 먼저) → 6.5.**
근거: 6.1이 "회사가 실제로 일하는" 최소 루프(이슈→실행→회수)를 완성하고, 6.2가 원질문의 커서 요금제 의도를 실현하며, 6.3이 SNS 축을 붙입니다. 6.4는 코드보다 결정이 먼저라 Board 게이트로 분리합니다.

## 6. 남은 실측 체크리스트 — 사용자 환경 (2026-07-26 기준)

Phase 6의 측정 가능분은 전부 완료·머지됐습니다(PR #1~#14). 남은 것은 이 샌드박스에서 할 수 없는
것들뿐이며, 각각 독립적으로 실행 가능합니다:

| # | 검증 | 방법 | 근거 문서 |
|---|------|------|-----------|
| 1 | **데스크톱 Phase 0 잔여** — 컨테이너 프로필 선택 방식 + 봇 신원 5종 상이함 | 실기기+버려도 되는 길드에서 compose 기동 → `companyctl doctor --online`. `.env.example`의 `HERMES_REF=main`을 실측 버전(0.19.0)에 대응하는 ref로 핀 | [DESKTOP.md](./DESKTOP.md) Phase 0 표 (0.2·0.4는 완료) |
| 2 | **이슈→실행 왕복** (6.1 DoD) | Paperclip 이슈를 hermes_local 에이전트에 배정 → 실행 결과·비용이 이슈로 돌아오는지 (게이트웨이+LLM 키 필요) | [PAPERCLIP.md](./PAPERCLIP.md) |
| 3 | **커서 구독 과금 왕복** (6.2 DoD) | Cursor CLI `agent login` 상태에서 `adapterType: "cursor"` 에이전트로 태스크 1건 실행 — 키를 넣지 않아야 구독 과금 유지 | [PAPERCLIP.md](./PAPERCLIP.md) §5.1 · [COSTS.md](./COSTS.md) |
| 4 | **Growth 콘텐츠 왕복** (6.3 DoD) | `#growth` 요청 → `/content-director` → `#approvals` 승인 → 발행 기록 | [GROWTH.md](./GROWTH.md) §9 |
| 5 | **시크릿 위생** | 테스트 중 채팅에 노출된 Cursor API 키 로테이션 (아직이라면) | — |

이 표의 결과가 나오면 해당 문서에 실측 기록을 병기하는 것이 다음 세션의 첫 작업입니다.
