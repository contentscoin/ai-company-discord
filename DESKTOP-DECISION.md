# 데스크톱 전략 단일화 — Board 결정 자료 (Phase 6.4)

> **결정됨 (2026-07-25): Board가 B안(신규 Control Room 앱)을 채택했습니다.** 권고는 A안이었으나
> CRITICAL dissent가 아닌 권고는 Board 결정을 구속하지 않습니다 — 이 게이트의 목적 그대로입니다.
> 결과와 후속 백로그는 §7. 이하 §0~§6은 결정 당시의 자료 원문(기록)입니다.

[ALIGNMENT.md](./ALIGNMENT.md) §4 6.4의 Board 게이트 산출물입니다. **코드보다 결정이 먼저**인 항목이라
이 문서는 결정에 필요한 증거·비교·권고·마감 블록까지만 담고, 어느 쪽으로든 구현은 결정 후에 시작합니다.

## 0. 결정할 것

조직에 데스크톱 기획이 **둘 병존**합니다. [DESKTOP.md](./DESKTOP.md)(신규 Control Room 앱 설계)는
`hermes-ceo-console-installer`(이미 존재하는 Electron 설치 파일)를 **모른 채** 작성됐습니다
(ALIGNMENT §2 격차 ②). 질문은 셋입니다:

| # | 질문 | 권고 |
|---|------|------|
| Q1 | 데스크톱 산출물을 **하나로** 줄이는가? | **예** — 설치 파일 2개 병존은 1인 조직이 감당할 유지비가 아님 |
| Q2 | 그 하나는 **A(installer 확장)** 인가 **B(신규 앱)** 인가? | **A안** (§3) |
| Q3 | 탈락한 기획서의 지위는? | A 채택 시 DESKTOP.md는 **설계 검증 기록 + 이식 체크리스트**로 강등 (폐기 아님 — §4) |

## 1. 두 자산의 실체

**증거의 한계**: installer 실측은 2026-07-25 오전 감사 시점 기록입니다(ALIGNMENT §2 — 레포를 열어
확인). 이 저장소 세션의 현재 스코프에는 installer 레포가 없어 재검증하지 못했으며, 결정 시점에
릴리스가 더 나아갔을 수 있습니다. **알파 품질의 실제 동작(설치→5봇 기동 왕복)은 아직 아무도 실측하지
않았습니다** — 코드·릴리스 감사만 있었습니다.

| | A. hermes-ceo-console-installer | B. DESKTOP.md Control Room |
|---|---|---|
| 상태 | **실물 존재** — v0.1.0-alpha.27, 51커밋, Windows EXE(WSL2)/macOS DMG 산출물 | **기획서만** — 코드 0줄, 다만 5개 가정 검증(4개 반증)을 거친 설계 |
| 스택 | Electron + 커스텀 WebUI(`:8788`) | Python + pywebview + PyInstaller, 60MB 미만 목표 |
| 번들 | Hermes Agent + Paperclip(`:3100`) + 선택(Telegram/Codex/OpenCrab/Neo4j) | 업스트림 미번들 — 첫 실행 시 핀된 ref에서 확보 (BREAK 1 회피 설계) |
| Windows 전제 | WSL2 | Docker Desktop (네이티브 생명주기는 의도적 드롭 — BREAK 3) |
| 배포 파이프라인 | **절반 이상 존재** (알파 27회 릴리스 경험) | 없음 — Phase 5에서 신규 (서명 현실: EV 즉시 평판 없음) |
| 라이선스 부채 | **BREAK 1이 오늘 이미 적용** — Paperclip 번들 = embedded-postgres(PostgreSQL 18.4 + 제3자 라이브러리 8종) 고지 의무 | 번들 안 하므로 원천 회피 |

## 2. 판단 기준별 비교

| 기준 | A. installer 확장 | B. 신규 앱 |
|------|-------------------|------------|
| 사용자가 무언가를 설치하기까지 | **가까움** — 이미 설치됨(알파) | 멂 — Phase 0(차단) → 1 → 2 → 5 |
| 유지비 | Electron(90–120MB급) + WSL2 지원 | Python 단일, 얇음 — 단 **레포 하나를 더** 태어나게 함 |
| 조직 자산 | 51커밋·릴리스 27회의 학습 재사용 | 그 학습을 버리고 재시작 |
| 라이선스 | 고지 의무를 **지금 갚아야 함** (어차피 갚아야 할 빚 — §4 ①) | 회피 설계이나, A를 폐기해도 A의 빚이 사라지진 않음 |
| DESKTOP.md의 검증 자산 | **이식 가능** (§4 ②— 감시자 금지·신원 체크·시크릿 규칙은 스택 무관) | 원안 그대로 |
| 리스크 | 알파 품질 미실측 — 첫 실측에서 대수술이 나올 수 있음 | 런타임 계약(Phase 0) 미실측은 **양쪽 공통** 차단 요인 |

## 3. 권고 — A안, 조건부

**A안(installer 확장)을 권고합니다.** 결정적 근거는 두 가지입니다:

1. **1인 조직의 병목은 유지비입니다.** 설치 파일 2개(Electron + PyInstaller)를 병존시키면 서명·공증·
   릴리스·문서가 전부 2배가 됩니다. B의 "얇음"은 매력적이지만 **새 레포 하나의 탄생 비용**이 얇음의
   이득을 상쇄합니다.
2. **배포는 코드보다 비쌉니다.** alpha.27이라는 숫자는 품질 보증이 아니라 **배포 파이프라인을 27번
   돌려봤다는 증거**이고, 그게 이 결정에서 가장 비싼 자산입니다 (BREAK 4 — 서명·평판은 처음부터
   쌓아야 하는 종류의 비용).

**조건**: A 채택은 아래 §4의 즉시 조치 ①(라이선스)·③(Phase 0 실측)을 전제로 합니다. 특히 첫 실측에서
installer가 "설치는 되지만 5-프로필 회사가 뜨지 않는" 상태로 판명되면 — 그 수리 비용이 B의 Phase 0~2
비용을 넘는 경우에 한해 — 이 결정은 Board로 **재상정**합니다.

*(B안을 택할 경우: DESKTOP.md 로드맵을 그대로 집행하되, installer 레포는 아카이브하고 그 라이선스
부채(§4 ①)만은 아카이브 전에 갚아야 합니다 — 공개 릴리스가 존재했던 기간의 의무는 소급 소멸하지
않습니다.)*

## 4. 어느 쪽이든 즉시 적용되는 조치 (결정 무관)

1. **installer 레포에 제3자 라이선스 고지 추가** — Paperclip을 번들하므로 embedded-postgres의
   PostgreSQL 18.4 + 라이브러리 8종(OpenSSL·ICU 등) 고지 의무가 **오늘 이미** 그 레포에 적용됩니다
   (DESKTOP.md BREAK 1). A/B와 무관한 기존 부채입니다.
2. **DESKTOP.md의 스택 무관 자산은 어느 쪽에도 이식** — ⑴ 앱은 감시자가 아님(감시는 Docker
   restart/OS init), ⑵ 건강 체크는 프로세스 생존이 아니라 **봇 신원 5종의 상이함**(`GET /users/@me`
   대조), ⑶ 시크릿은 레포 밖 + 앱 디렉터리 밖(`~/.hermes/ai-company/`, 0600), ⑷ 봇 5개 수동 생성
   25단계를 첫 화면에서 정직하게 고지, ⑸ 상주 리스너 금지.
3. **Phase 0 런타임 계약 실측은 여전히 차단 선행조건** — A를 골라도 installer가 5-프로필 회사를
   실제로 띄우는지 아무도 모릅니다. 도구는 이미 있습니다: `companyctl verify-runtime` (PR #5) +
   `doctor --online`(신원 상이함 증명). 실측 1회가 결정의 §3 조건을 판정합니다.
4. **GUI가 소비할 API는 이미 출하됨** — `companyctl`의 `--json` + 종료 코드 계약(PR #4). A의 WebUI가
   이걸 호출하면 B 설계의 백엔드 계층을 그대로 얻습니다.

## 5. 결정 마감 블록 (붙여넣기용)

Board가 결정하면 아래 블록을 `#board-you`(또는 `#exec-meeting` 스레드)에 남기고
`companyctl decision`으로 마감합니다 — 기존 파서가 그대로 처리합니다 ([PROTOCOLS.md](./PROTOCOLS.md) §2).

```text
DECISION: 데스크톱 산출물은 hermes-ceo-console-installer 확장으로 단일화 (A안)
OWNER: cto
DUE: 2026-08-08
PAPERCLIP: create-issue
```

*(B안이면 첫 줄을 "DESKTOP.md Control Room 신규 앱으로 단일화 (B안)"으로. 어느 쪽이든 §4의
①·③은 별도 ACTIONS로 함께 마감할 것을 권합니다.)*

## 6. A안 채택 시 후속 백로그 (기록 — 채택되지 않음)

1. §4 ① 라이선스 NOTICE → installer 레포
2. §4 ③ 실측: 실기기에서 installer 설치 → `verify-runtime` → `doctor --online` 신원 5종 확인 → 결과에 따라 §3 조건 판정
3. 5-프로필 Discord 온보딩(Setup Wizard의 25단계 정직 버전)을 installer WebUI에 이식
4. WebUI가 `companyctl --json`을 소비하도록 연결 (Dashboard·Doctor 화면)
5. DESKTOP.md 상단에 "설계 검증 기록" 지위 명시

## 7. 결정 결과 — B안 (2026-07-25)

**Board 결정: DESKTOP.md Control Room 신규 앱으로 단일화.** [DESKTOP.md](./DESKTOP.md)가 유효한
로드맵으로 승격되고, 그 문서의 규율도 그대로 승격됩니다 — **Phase 0(런타임 계약 실측) 전에는 GUI
코드를 한 줄도 쓰지 않습니다.**

마감 블록 (Discord에 남긴 뒤 `companyctl decision`으로 적재):

```text
DECISION:
- 데스크톱 산출물은 DESKTOP.md Control Room 신규 앱으로 단일화 (B안, DESKTOP-DECISION.md §7)
ACTIONS:
- @board : hermes-ceo-console-installer에 제3자 라이선스 NOTICE 추가 후 아카이브 (DUE: 2026-08-08)
- @CTO : Phase 0 런타임 계약 실측 — 실기기에서 verify-runtime + doctor --online (DUE: 2026-08-15)
```

### B-경로 백로그 (순서 고정)

| # | 일 | 어디서 | 차단 관계 |
|---|----|--------|-----------|
| 1 | installer 레포에 embedded-postgres 제3자 고지(NOTICE) 추가 → **그 다음** 아카이브 | installer 레포 (Board) | §3 말미 — 공개 릴리스가 존재했던 기간의 고지 의무는 아카이브로 소멸하지 않음. **아카이브가 NOTICE보다 먼저 오면 안 됨** |
| 2 | **Phase 0 실측**: 실기기 + 버려도 되는 길드에서 `companyctl verify-runtime` → `RUNTIME-CONTRACT.md`, `doctor --online`으로 봇 신원 5종 상이함 증명, `HERMES_REF` 커밋 핀 | 사용자 로컬 | **이후 전부를 차단** (DESKTOP.md Phase 0) |
| 3 | 앱 레포 `ai-company-desktop` 생성 — companyctl을 버전 고정 라이브러리로 소비 (DESKTOP.md §5.1: 이 레포에 앱 코드를 넣지 않음) | 신규 레포 | 2 이후 |
| 4 | DESKTOP.md Phase 1 잔여분(패키지 분리, `REPO_ROOT` frozen-aware)을 앱 레포 쪽에서 | 앱 레포 | 3 이후 |
| 5 | Phase 2~5 (셸 → 마법사 → 콘솔 → 패키징·서명) | 앱 레포 | 4 이후 |

이 레포(ai-company-discord)의 몫은 끝났습니다: `--json` + 종료 코드 계약(PR #4)과
`verify-runtime`(PR #5)이 앱이 소비할 표면이고, 추가 코드는 Phase 0 결과가 나와야 값을 합니다.
