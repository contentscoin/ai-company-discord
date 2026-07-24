# 고도화 로드맵 (Enhancement Roadmap)

v0.1.0(문서 + 최소 스캐폴드)을 **실제 운영 가능한 컨트롤룸**으로 끌어올리는 단계별 기획서입니다.
버전 목표: Phase 1 = `0.2.0` → Phase 2 = `0.3.0` → Phase 3 = `0.4.0` → Phase 4 = `0.5.0`.

## 1. 현황 진단

| # | 격차 | 현재 상태 |
|---|------|-----------|
| 1 | 수동 운영 | 채널·역할 생성 손 클릭, standup cron 미제공, DECISION→Paperclip 수동, ingest 스테이징 수동 |
| 2 | 단일 진실원천(SSoT) 부재 | `templates/company.discord.json`을 아무것도 소비하지 않음 — scaffold는 프로필 목록 하드코딩, 채널은 [CHANNELS.md](./CHANNELS.md) 산문 보고 수작업 |
| 3 | 검증·헬스 도구 부재 | 토큰 충돌·권한·설정 드리프트를 확인할 수단 없음 |
| 4 | 관측성 부재 | 회의 아카이브·결정 로그 미러·비용 가시성 없음 |
| 5 | 프로토콜 산문 전용 | DECISION 블록·Critic verdict·standup 포맷이 기계 파싱 불가능한 서술로만 존재 |
| 6 | Windows 패리티 격차 | scaffold가 bash 전용 |
| 7 | 온보딩 마찰 | Discord 앱 5개 수작업 생성, 권한 체크리스트 수작업 |

## 2. 설계 원칙

1. **경량 패키지 유지** — docs + templates + scripts. 상주 서비스·봇 리스너를 이 레포에 추가하지 않음
2. **업스트림은 통합만** — Hermes·Paperclip·OpenCrab·GJC를 포크하거나 재구현하지 않음 (→ §3 업스트림 경계)
3. **`company.discord.json` = SSoT** — 역할·채널·회의 정의는 이 파일 하나에서. 스크립트·문서가 이를 소비
4. **시크릿·채널 ID는 레포 밖** — 토큰은 `.env`, 런타임 상태(채널 map·결정 로그)는 `~/.hermes/ai-company/` 이하
5. **평면 분리 유지** — Discord = 회의, Paperclip = 실행 진실원천, OpenCrab = 정제 지식만
6. **스크립트 런타임 Python 3 (stdlib 전용)** — `pip install` 0개, 크로스플랫폼이라 Windows 패리티를 구조적으로 해결. bash/ps1은 3줄 래퍼만
7. **단일 CLI** — 느슨한 스크립트 9개 대신 `scripts/companyctl.py` 하나에 서브커맨드(`validate` `scaffold` `bootstrap` `doctor` `standup` `decision` `lint` `digest` `archive`)를 단계별 추가. 멀티 컴퍼니는 `--config <path>` 플래그로 처음부터 흡수

## 3. 업스트림 경계 — 무엇을 위임하고 무엇을 직접 만드나

이 레포는 Hermes(직원 런타임)·Paperclip(회사 거버넌스)과 경쟁하지 않습니다.
그 둘 위에 얹는 **조직 설계 + 회의 규범 + 배치도** 계층입니다.

| 관심사 | Hermes | Paperclip | 이 레포 |
|--------|--------|-----------|---------|
| 에이전트 구동 (프로필·SOUL·메모리·게이트웨이) | ✅ | — | 위임 |
| 멀티플랫폼 (Discord/TG/Slack) | ✅ | — | 위임 + Discord를 회의 평면으로 지정 |
| cron·스케줄링 | ✅ 내장 스케줄러 | ✅ Routine/heartbeat | 위임 (템플릿만 제공) |
| 태스크·이슈·차단 의존성 | — | ✅ | 위임 (실행 진실원천) |
| 조직도·역할·보고라인 | — | ✅ | **구체화** — 5역할 프리셋 + SOUL 콘텐츠 |
| 예산·비용 추적 | — | ✅ 에이전트/모델별 | 위임 |
| 승인 게이트·감사 로그 | — | ✅ | 위임 + `#approvals` 채널로 표면화 |
| 회의 오케스트레이션 (Council·War Room·standup 프로토콜) | — | — | ✅ **고유 가치** |
| 멘션·cascade 규칙, cross-family Critic 관례 | — | — | ✅ **고유 가치** |
| 역할↔모델 라우팅 규범 (GJC 매핑) | 모델 스위칭만 | 비용 추적만 | ✅ **고유 가치** |
| 지식 정제 파이프라인 (OpenCrab ingest 규범) | — | — | ✅ **고유 가치** |

이에 따른 로드맵 조정 (재발명 방지):

- **Standup cron (Phase 2.3)**: Hermes **내장 cron 스케줄러가 1급 경로** — 이 레포는 프롬프트·설정 템플릿만 제공. `companyctl standup post`(REST 게시)는 Hermes cron을 쓸 수 없는 환경의 fallback으로만
- **결정 로그 (Phase 3.4)**: 감사 추적의 진실원천은 Paperclip. 로컬 `decisions.ndjson`은 **Paperclip 미가동/오프라인에서도 `#briefs` 다이제스트를 뽑기 위한 경량 미러**로만 정당화
- **비용 (Phase 4.2)**: Paperclip 예산·비용 추적이 정답. `COSTS.md`는 **Paperclip 미사용자를 위한 최소 안내**로 한정 — 자체 추적 로직을 만들지 않음

## 4. 아키텍처

```mermaid
flowchart LR
    B["Board (사람)"] -->|"의제 · 승인 · 결정"| DC

    subgraph DC["Discord — 회의 평면"]
        CH1["#board-you · #approvals"]
        CH2["#exec-meeting · #standup · #war-room"]
        CH3["#dev · #loop · #growth"]
        CH4["#ingest-review · #briefs"]
    end

    subgraph HP["Hermes 프로필 x5 (봇 토큰 격리)"]
        CEO["CEO - 오케스트레이션"]
        CTO["CTO - 구현 (Cursor 중심)"]
        LOOP["Loop - DoD 검증"]
        GROWTH["Growth - SNS/콘텐츠"]
        CRITIC["Critic - 교차벤더 비평"]
    end

    DC <-->|"@멘션"| HP
    CEO -->|"DECISION → 이슈"| PC["Paperclip - 실행 진실원천 (태스크·예산·감사)"]
    CEO -->|"정제 요약만"| OC["OpenCrab - 지식 (Graph RAG)"]
    CTO --- CUR["Cursor + Codex/Claude 위성"]
```

## 5. 단계별 로드맵

노력 척도: **S** ≤ 반나절 · **M** = 1–3일 · **L** = 1주+

### Phase 1 — 기반 정비: SSoT 전환 + 문서 정비 (총 M) — ✅ 구현됨

목표: `company.discord.json`이 실제 진실원천이 되고, 문서만으로 막히던 온보딩 지점을 제거.

> 이 단계는 구현되어 이 PR에 포함되었습니다. 아래 표는 실제 산출물입니다.

| # | 산출물 | 파일 | 노력 |
|---|--------|------|------|
| 1.1 | JSON v0.2 확장 — `channels`를 객체 배열 `{name, category, purpose, access[], freeResponse?}`로, `meetings{standupCron, execMeetingCron}` · `protocolVersion` 필드 추가 | `templates/company.discord.json` | S |
| 1.2 | JSON Schema + `companyctl validate` — 스키마 검증 + 교차 검증(role의 `hermesProfile` ↔ `profiles/<id>/SOUL.md` 존재, 채널 `access` role-id·category 참조 유효) | `templates/company.schema.json` · `scripts/companyctl.py` | M |
| 1.3 | scaffold를 JSON 소비로 재작성 — 하드코딩 프로필 목록 제거. `scaffold-profiles.sh`는 호환 래퍼로 축소, `companyctl.ps1` 래퍼 추가 (Windows 패리티 1차 해소) | `scripts/companyctl.py` · `scripts/scaffold-profiles.sh` · `scripts/companyctl.ps1` | S |
| 1.4 | CI — `companyctl validate` + shellcheck + 마크다운 링크 체크 (SSoT를 CI가 보호) | `.github/workflows/ci.yml` | S |
| 1.5 | WINDOWS.md를 1회성 "발행 절차"에서 "Windows에서 운영하기"(py 런처·래퍼 사용법)로 재작성, publish 스크립트 deprecated 표기 | `WINDOWS.md` | S |

의존성: 없음 (시작점).
**DoD**: `validate`가 배포 템플릿에서 exit 0, 필드 훼손 픽스처에서 exit≠0 + 위치 지목 · JSON에 프로필을 추가하면 **스크립트 수정 없이** 스캐폴드 확장 · CI green.

### Phase 2 — 자동화: 부트스트랩 + doctor + cron 템플릿 (총 L)

목표: JSON → 라이브 Discord 서버 상태를 스크립트가 만들고 검증. 수동 채널 생성 종료.

| # | 산출물 | 파일 | 노력 |
|---|--------|------|------|
| 2.1 | `companyctl bootstrap` — Discord REST로 역할(Board/Exec/Observer)·카테고리·채널·권한 overwrite 생성. **멱등**(이름 매칭·삭제 절대 안 함), 기본 `--dry-run`, 변경은 `--apply` 명시. 토큰은 `DISCORD_SETUP_TOKEN` env로만, 채널 스노우플레이크는 `~/.hermes/ai-company/discord.map.json`에 기록 | `scripts/companyctl.py` | M |
| 2.2 | `companyctl doctor` — PASS/WARN/FAIL: 프로필 파일 존재, 토큰 채움 + **중복 검사(SHA-256 비교, 값 미출력)**, `--online` 시 토큰 유효성·길드 가입, JSON ↔ 실제 채널 드리프트, config.yaml ↔ 템플릿 키 드리프트, 중복 YAML 키. Message Content Intent는 API로 확인 불가 → best-effort WARN 명시 | `scripts/companyctl.py` | M |
| 2.3 | standup·회의 스케줄 템플릿 — **1급 경로는 Hermes 내장 cron**(프로필 설정 예시 제공). fallback: `companyctl standup post`(CEO 토큰으로 [MEETINGS.md](./MEETINGS.md) §B 템플릿을 REST 게시) + `templates/cron/crontab.example`. MEETINGS.md에 사용법 절 추가 | `scripts/companyctl.py` · `templates/cron/crontab.example` · `MEETINGS.md` | S |
| 2.4 | SETUP.md 절차 단축 — "채널을 손으로 만드세요" → `bootstrap`/`doctor` 흐름 | `SETUP.md` | S |

의존성: Phase 1 (채널 `access[]`·category 메타데이터, map 파일 규약).
**DoD**: 테스트 길드에서 bootstrap 2회 실행 → 2회차 "0 changes" · 채널 하나 삭제 후 재실행 → 그 채널만 재생성 · doctor가 토큰 중복 픽스처·`require_mention` 변조를 FAIL로 검출.

### Phase 3 — 프로토콜 기계화: DECISION 문법 + 연동 (총 M, Phase 2와 병행 가능)

목표: 산문 프로토콜을 버전 있는 스펙으로 승격, 결정→이슈·요약→ingest 경로에 도구를 부착.

| # | 산출물 | 파일 | 노력 |
|---|--------|------|------|
| 3.1 | `PROTOCOLS.md` (PROTOCOL v1) — DECISION/OPEN/ACTIONS 블록 문법(EBNF + 예시), Critic `VERDICT: CLEAR\|WATCH\|BLOCK`, Loop PASS/FAIL 리포트. **기존 [MEETINGS.md](./MEETINGS.md)·[ROUTING.md](./ROUTING.md)·SOUL 예시를 그대로 형식화** (souls 수정 최소화 — 인라인 포맷 재정의를 스펙 참조로 dedup) | `PROTOCOLS.md` · `profiles/*/SOUL.md` | S |
| 3.2 | `companyctl decision` — 붙여넣은 마감 블록 → 정규화 JSON(OWNER를 role-id로 매핑). `--to-paperclip` 시 로컬 API에 ACTIONS별 이슈 생성, Paperclip 부재 시 이슈 JSON 출력으로 우아한 강등. **입력은 사람이 복사한 텍스트만** — Discord 상주 리스너 없음 | `scripts/companyctl.py` | M |
| 3.3 | `companyctl lint` — OpenCrab ingest 전 새니타이즈 린트: Discord 토큰·API 키 프리픽스·이메일·스노우플레이크·회의 원문 지표 검출 시 exit≠0 + 위치 보고. ROUTING.md §6에 "lint 통과 후 staging" 삽입 | `scripts/companyctl.py` · `ROUTING.md` | S |
| 3.4 | 결정 로그 미러 + 다이제스트 — 파싱 성공 시 `~/.hermes/ai-company/decisions.ndjson` append(진실원천은 Paperclip, §3 참조), `companyctl digest`가 주간 마크다운(결정/미결/담당별 액션)을 `#briefs` 붙여넣기용으로 렌더 | `scripts/companyctl.py` | S |
| 3.5 | 파서·린트 골든 픽스처 테스트 (`python -m unittest`) CI 편입 | `tests/` | S |

의존성: Phase 1 (role-id 매핑). Phase 2와 독립.
**DoD**: MEETINGS.md §A.4 예시 블록이 골든 JSON과 round-trip · 형식 위반 → exit≠0 + 오류 라인 · 린트가 심어둔 시크릿 픽스처 전부 검출 + 정제 요약 샘플 통과 · digest가 샘플 ndjson을 정확히 렌더.

### Phase 4 — 운영 관측성 (선택, 총 M~L)

목표: 회의 이력·비용 가시성. 한계효용이 낮아 명시적 후순위.

| # | 산출물 | 파일 | 노력 |
|---|--------|------|------|
| 4.1 | `companyctl archive` — 회의 스레드 REST export → **새니타이즈 린트 통과한** 회의록만 `~/.hermes/ai-company/minutes/` 저장, `--post-briefs`로 게시 | `scripts/companyctl.py` | M |
| 4.2 | 비용 가시성 — role별 `modelHint` 필드 + doctor WARN + `COSTS.md`(Paperclip 미사용자용 프로바이더별 사용량 확인 경로 안내). 자체 추적 로직 없음 (§3 참조) | `templates/company.discord.json` · `COSTS.md` | S |
| 4.3 | `companyctl status` — 게이트웨이 프로세스·map·최근 결정·마지막 standup 한 화면 요약 | `scripts/companyctl.py` | S |

의존성: Phase 2 (REST 유틸·map), Phase 3 (린트·결정 로그).
**DoD**: 토큰 포함 스레드는 게시 거부 · status가 5 프로필 상태를 오류 없이 요약.

## 6. 이 PR에 포함된 것

**기획 + 문서 퀵윈**

1. 본 기획서 (`ROADMAP.md`)
2. [SETUP.md](./SETUP.md) §3 경로 버그 수정 — `./docs/ai-company/scripts/…`(모노레포 추출 전 잔재) → `./scripts/scaffold-profiles.sh`
3. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — 증상→원인→해결 표 (CEO config 중복 `discord:` 키 함정 포함)
4. [README.md](./README.md) 아키텍처 다이어그램 + Docs 표 갱신

**Phase 1 구현 (SSoT 전환)**

5. `templates/company.discord.json` v0.2 — 채널 객체화(category/access/freeResponse), `meetings` cron·`protocolVersion` 필드
6. `templates/company.schema.json` — 편집기용 JSON Schema 계약
7. `scripts/companyctl.py` — 단일 CLI. `validate`(스키마 + 파일시스템 교차 검증), `scaffold`(JSON 기반, 멱등). 후속 Phase의 서브커맨드가 여기 붙습니다
8. `scripts/scaffold-profiles.sh` → `companyctl.py scaffold` 호환 래퍼로 축소 + `scripts/companyctl.ps1`(Windows). scaffold의 CEO config 중복 `discord:` 키 함정 제거
9. `scripts/check_links.py` + `.github/workflows/ci.yml` — CI가 validate·링크·shellcheck로 SSoT 보호
10. `WINDOWS.md` 재작성(운영 관점) + publish 스크립트 deprecated 표기

## 7. 비목표 (Non-goals)

| 항목 | 사유 |
|------|------|
| Discord 상주 리스너로 DECISION 실시간 캡처 | 상주 서비스는 경량 원칙 위반 + 회의/실행 평면 분리 훼손. 붙여넣기 파서가 가치의 90% |
| OpenCrab 자동 ingest | `#ingest-review` human-review 게이트가 설계 핵심. 린트 보조까지만 |
| 자체 cron·스케줄러 구현 | Hermes 내장 cron + Paperclip Routine 위임 (§3) |
| 자체 비용 추적·대시보드 | Paperclip 본업 (§3) |
| Telegram 도구화 | 명시적 옵션 채널(DM 핫라인). 투자 가치 없음 |
| Hermes/GJC 패치·포크 | 업스트림 원칙 위반 |
| 멀티 컴퍼니 별도 지원 | `companyctl --config <path>`로 0원 처리 |

## 8. 리스크 · 오픈 퀘스천

| # | 리스크 | 대응 |
|---|--------|------|
| 1 | Hermes cron의 설정 표면(포맷·채널 타게팅) 미검증 | Phase 2.3 착수 시 실측 후 템플릿 확정. REST fallback이 안전망 |
| 2 | bootstrap에 Manage Channels/Roles 필요 — CEO 봇 상시 부여는 과권한 | 셋업 시 임시 role 부여 → 회수 절차를 문서화. 토큰은 env로만 |
| 3 | Message Content Intent는 타 앱 API로 검증 불가 | doctor는 best-effort WARN임을 명시 (과신 방지) |
| 4 | Paperclip API 표면 변동 가능 | `decision`은 항상 JSON 출력으로 강등 가능, 버전 고정 금지 |
| 5 | JSON 구조 변경(문자열→객체)은 breaking | 현재 소비자 0 — 지금이 최저비용. `version` 필드로 표기 |
| 6 | 시크릿 유출 벡터 (새 스크립트 전부) | 토큰은 env/.env만, 인자·로그 금지, doctor는 해시 비교, 스노우플레이크도 레포 밖 |
| 7 | Windows python3 부재 가능 | 래퍼에 `py -3` 런처 fallback 내장 (Phase 1.5) |
| 8 | 문서 언어 혼재 | 정책 유지: README 영어, 운영 문서·본 기획서 한국어 |
