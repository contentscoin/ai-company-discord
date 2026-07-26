# 데스크톱 앱 고도화 기획 — 설치 파일까지

> **지위 (Phase 6.4 — 결정됨)**: Board가 2026-07-25 **이 문서를 유효한 로드맵으로 채택**했습니다
> (B안 — [DESKTOP-DECISION.md](./DESKTOP-DECISION.md) §7). 기존 `hermes-ceo-console-installer`는
> 이 기획과 무관한 **독립 프로젝트로 존속**합니다 (2026-07-26 개정 — 제3자 라이선스 NOTICE 의무만
> 그 레포에 별도 적용). 채택은 이 문서의 규율까지 포함합니다:
> **Phase 0(런타임 계약 실측) 전에는 GUI 코드를 한 줄도 쓰지 않습니다.** 후속 순서는
> DESKTOP-DECISION.md §7의 B-경로 백로그를 따릅니다.

최종 산출물을 **데스크톱 설치 파일**(.dmg / .exe / .AppImage)로 잡았을 때의 아키텍처와 로드맵입니다.
14개 에이전트 감사·설계·심사·적대적 검증을 거쳤고, **검증한 5개 가정 중 4개가 깨졌습니다.** 그 4개가 이 문서의 뼈대입니다.

## 0. 결론 먼저

| | |
|---|---|
| **채택 아키텍처** | Control Room — 얇은 셸(Python + pywebview + PyInstaller), 3개 렌즈 합산 23/30 (2위 16, 3위 13) |
| **설치 파일 크기** | 60MB 미만 (macOS 20–40MB · Windows 16–22MB · Linux 26–35MB) |
| **앱이 감시자가 되지 않음** | 게이트웨이 감시는 Docker `restart` 정책 / launchd / systemd가 담당. 창을 닫아도 회사는 돈다 |
| **업스트림은 설치 파일에 안 들어감** | Hermes·Paperclip은 첫 실행 시 핀된 ref에서 확보 |
| **선행 조건(차단)** | Phase 0 — Hermes 런타임 계약 실측. **이게 끝나기 전엔 GUI 한 줄도 쓰지 않는다** |
| **연간 고정비** | 1년차 $99(Apple) / 2년차 $99 + 코드서명 |

## 1. 지금 자산 (감사 결과)

데스크톱 앱의 백엔드가 될 로직은 **이미 대부분 있습니다.**

- `companyctl.py` **1555줄 · 15개 서브커맨드 · 44개 테스트 통과**
- **약 20개 함수가 이미 순수 함수** — `validate` `compute_bootstrap_plan` `doctor_offline` `parse_decision_block` `scan_for_sensitive` `render_digest` `render_minutes` 등. 인자 받고 값 반환, 출력 없음 → **재작성 없이 앱 백엔드로 import 가능**
- 테스트가 이미 그렇게 호출하고 있음(`importlib`로 모듈 로드 후 순수 함수 직접 호출)
- SSoT(`company.discord.json`) + 스키마 → UI의 채널 그리드·역할 카드·OAuth 권한셋을 **하드코딩 없이 생성 가능**

즉 이 프로젝트는 **화면을 붙이는 일**이지 새로 만드는 일이 아닙니다.

## 2. 깨진 가정 4개 — 계획을 규정하는 것들

### ❌ BREAK 1 — "MIT니까 번들해도 된다"

Hermes(MIT © 2025 Nous Research)·Paperclip(MIT © 2026 Paperclip Labs) 라이선스는 **맞습니다.** 그런데 Paperclip은 `embedded-postgres`에 의존하고, 그 npm 패키지의 `license: "MIT"`는 **래퍼 저자의 것**입니다. 실제 페이로드는 **PostgreSQL 18.4 배포판 + 제3자 공유 라이브러리 8종**(OpenSSL·ICU 등, 일부는 GPL)입니다.

> 업스트림의 MIT는 그 프로젝트가 저작한 코드만 규율합니다. 함께 실려 오는 별도 라이선스 바이너리에 대해서는 아무 권한도 주지 않습니다.

**결론: 설치 파일에 Paperclip을 번들하지 않습니다.** 저작권 침해는 무과실 책임이고 "npm이 MIT라고 했다"는 항변이 되지 않습니다.

### ❌ BREAK 2 — "앱이 게이트웨이 5개를 자식 프로세스로 감시할 수 있다"

**이 발견이 PR #2에 만든 생명주기 계층까지 흔듭니다.**

검증 결과: `hermes gateway start`는 **프로세스 실행이 아니라 서비스 제어 명령일 가능성**이 제기됐습니다(업스트림이 `gateway install`로 launchd plist·systemd unit·schtasks를 등록하고, `start`는 그 서비스 매니저에게 요청 후 즉시 반환). 사실이라면:

- 앱이 잡은 PID는 게이트웨이가 아니라 **제어 클라이언트**입니다. 1초 만에 죽고 → 감시자가 "크래시"로 오판 → 재기동 → **중복 실행 루프**
- 프로필마다 봇 토큰이 다르고 업스트림은 토큰 중복 폴링을 막으므로, 증상은 "봇이 안 뜬다" 또는 "메시지를 두 번 쓴다"로 나타납니다

**저는 이것을 확인하지 못했습니다.** Hermes docs 사이트는 403, raw 문서 경로는 404였습니다. README에서 확인된 건 `gateway setup`과 `gateway start`뿐이고 `gateway install`은 확인도 반증도 못 했습니다.

**→ 그래서 Phase 0이 존재하고, 모든 것을 차단합니다.**

### ❌ BREAK 3 — "companyctl을 통째로 백엔드로 재사용한다"

**재사용 가능(1~1160줄)**: validate·scaffold·bootstrap·doctor·standup·decision·lint·digest·archive·status — 진짜 stdlib 전용, 44/44 통과.

**재사용 불가(1160~1424줄, 생명주기)**: Windows에서 단순히 동작 안 하는 게 아니라 **파괴적**입니다.

| 코드 | Windows에서 벌어지는 일 |
|------|------------------------|
| `pid_alive()` → `os.kill(pid, 0)` | CPython 문서: *"Any other value for sig will cause the process to be unconditionally killed by the TerminateProcess API"* → **생존 확인이 그 게이트웨이를 죽입니다.** GUI의 "새로고침" 버튼이 봇 5개를 조용히 종료 |
| `stop_pid()` → `signal.SIGKILL` | Windows에 없음 → AttributeError |
| `start_gateway()` → `start_new_session=True` | POSIX 전용, Windows에선 무시됨 → 분리 보장 없음 |
| `logs --follow` → `tail -f` | Windows 기본 미탑재 |
| `service` | systemd/launchd만. **Windows 자동 시작 경로 없음** |

게다가 **CI가 `ubuntu-latest` 단독**이라 이 중 무엇도 드러나지 않았습니다. `test_pid_alive_true_for_self`는 Windows에서 **자기 테스트 러너를 죽입니다.**

> ROADMAP §2.6의 *"크로스플랫폼이라 Windows 패리티를 구조적으로 해결"* 은 **사실이 아닙니다.** 원칙 안에 버그가 숨어 있었습니다.

### ❌ BREAK 4 — "EV 인증서를 사면 SmartScreen이 사라진다"

- **macOS는 성립**: Apple Developer $99/년 + 공증 필수, 우회로는 닫히는 중(Sequoia가 Control-click 우회 제거)
- **Windows는 틀림**: 2024년 8월 MS가 신뢰 루트에서 **EV 코드서명 OID를 전부 제거**했습니다. EV도 즉시 평판을 주지 않습니다. 릴리스마다 해시가 바뀌어 평판은 매번 처음부터 쌓입니다
- **CI 함정**: 상용 인증서는 보통 **USB 하드웨어 토큰**으로 옵니다 → GitHub 호스티드 러너에 꽂을 수 없습니다. 클라우드 HSM(Azure Trusted Signing 등)이 아니면 파이프라인이 마지막 단계에서 막힙니다

**성공 기준을 바꿔야 합니다**: "경고 없음"이 아니라 *"서명됨 + UAC에 게시자 이름 표시 + 평판 축적 중"*.

## 3. 채택 아키텍처 — Control Room

**한 줄**: 기존 companyctl 로직을 그대로 in-process로 쓰는 Python 앱이, 루프백 JSON API를 띄우고, 네이티브 웹뷰에 화면 6개를 그린다. **감시는 하지 않는다.**

### 스택

| | 선택 | 이유 |
|---|---|---|
| 언어 | Python 3.12 **단일** | 재사용 로직 100%가 Python. 새 언어 0개 |
| UI | 순수 HTML/CSS/JS (npm·빌드 스텝 없음) | 프레임워크 유지비 0 |
| 창 | pywebview (WKWebView/WebView2/WebKitGTK) | **유일한 신규 런타임 의존성** |
| 번들러 | PyInstaller (onedir) | onefile은 Defender 오탐 유발 |
| 설치 | create-dmg / Inno Setup(per-user, UAC 없음) / AppImage | |

**Electron 탈락**: Chromium 90–120MB를 더하고도 **여전히 PyInstaller 파이썬 사이드카가 필요**합니다. **Tauri 탈락**: 바이너리는 작지만 Rust·cargo·크로스컴파일이 추가되고 역시 사이드카가 필요하며, `externalBin` 추가 시 **macOS 공증이 깨지는 미해결 이슈**(tauri#11992)가 있습니다.

### 화면 6개

Setup Wizard · Company Dashboard · Logs · Meeting Console · Doctor · Settings

### 앱이 감시자가 아닌 이유가 핵심 설계

ROADMAP §5.3이 이미 *"자체 supervisor를 만들지 않고 OS init에 위임"* 이라고 못박아 둔 덕분에, 앱은 **트레이 데몬·IPC·재기동 루프·graceful shutdown 안무**가 전부 필요 없습니다. 필요한 건 spawn-and-forget, 상태 폴링, 로그 tail, HTTP — 단일 프로세스 파이썬 앱이 스레드풀로 다 합니다.

### 런타임 2종, 어댑터 1개

```
GatewayRuntime.status() / .up() / .down() / .logs()
   ├─ DockerRuntime  ← 기본값, Windows의 유일한 지원 경로
   └─ NativeRuntime  ← macOS·Linux 전용
```

**Windows 네이티브 경로는 의도적으로 드롭합니다.** BREAK 3의 세 버그를 Job Object/CTRL_BREAK_EVENT 계층을 새로 짜서 막는 대신, **문서화된 범위 경계 하나**로 바꿉니다. 신규 코드 0줄.

### 반드시 고쳐야 할 기존 결함

현재 `ORCHESTRATION.md`는 사용자에게 **레포 안 `secrets/*.env`에 실제 봇 토큰을 붙여넣으라**고 안내합니다. 설치된 앱에서 그 디렉터리는 **읽기 전용**(.app / Program Files)이라 Docker 경로가 아예 동작하지 않고, ROADMAP §2.4(시크릿은 레포 밖) 위반이기도 합니다. → compose 정의와 시크릿을 `~/.hermes/ai-company/compose/`로 **물질화**(0600)합니다.

## 4. 로드맵

### Phase 0 — 런타임 계약 실측 **(차단, 최우선)**

**GUI 코드는 이 단계 전에 한 줄도 쓰지 않습니다.**

| # | 할 일 | DoD |
|---|------|-----|
| 0.1 | 실제 하드웨어 + 버려도 되는 Discord 길드에서 compose 스택 기동 | 컨테이너가 **프로필을 어떻게 선택하는지** 확정 (`HERMES_PROFILE`? CLI 인자? config?) |
| 0.2 | `hermes gateway` **전체 서브커맨드 실측** | `install` 존재 여부, `start`가 블로킹인지 즉시 반환인지 확정 |
| 0.3 | 결과를 `RUNTIME-CONTRACT.md`로 고정, `HERMES_REF`를 **그 커밋으로 핀** | `main`이 아닌 정확한 ref |
| 0.4 | CI에 `windows-latest` + `macos-latest` 추가 (기존 44개 테스트) | "크로스플랫폼"이 문서상 주장에서 **사실 또는 버그 목록**으로 전환 |

> 0.2 결과에 따라 **PR #2의 생명주기 계층을 수정해야 할 수 있습니다.** `start`가 서비스 제어 명령이면 `up`/`status`의 PID 추적 전제가 무너집니다.

### Phase 1 — 라이브러리화 (M)

- `companyctl.py` → `companyctl_core/` 패키지. **순수 함수 20개는 그대로**, `status()` `apply_bootstrap_plan()`을 프린터에서 추출
- 남은 10개 서브커맨드에 **`--json` 추가 + 종료 코드 계약 고정** ← 이게 GUI의 실제 API
- `discord_request()`에 **timeout 추가**(현재 없음 → GUI 메인 스레드에서 영구 행). `emit_paperclip()`은 출력 대신 **반환**
- PyInstaller 대비 `REPO_ROOT`를 frozen-aware로(`sys._MEIPASS`)
- **생명주기 5개 커맨드는 사이드카 API에서 제외** — Windows 지뢰를 배포하지 않음

DoD: 44개 테스트 유지 + Windows/macOS CI 통과 + `--json` 계약 문서화

### Phase 2 — 앱 셸 + Doctor/Dashboard (M)

읽기 전용 화면부터. 루프백 API(에페메랄 포트 + per-launch 베어러 토큰), pywebview 창, `--browser` 폴백.

**Dashboard 건강 체크는 "프로세스가 살아있음"이 아니라 "봇 5개의 신원이 서로 다름"을 확인합니다** — 토큰별 `GET /users/@me`를 `discord.map.json`과 대조. *초록인데 틀린 상태*가 이 프로젝트가 감당할 수 없는 실패이기 때문입니다.

### Phase 3 — Setup Wizard (L, 제품의 핵심)

**Discord 봇 5개 수동 생성은 제거 불가**입니다 — 검증 결과 **HOLDS**: Discord는 애플리케이션/봇 생성 공개 API가 없습니다(약 25회 브라우저 조작).

앱이 할 수 있는 것: 페이지별 딥링크, `company.discord.json`에서 **OAuth 초대 URL 생성**, 토큰 붙여넣기 박스(한 번 붙여넣으면 `~/.hermes/profiles/<p>/.env`와 compose secrets **양쪽에 기록**), 단계별 즉시 검증.

**첫 화면에서 "이 25단계는 없앨 수 없습니다"라고 말합니다.** 숨기지 않습니다.

### Phase 4 — Meeting Console · Logs · Settings (M)

`parse_decision_block` 즉시 미리보기, `lint` 게이트, `digest`. **라이브 피드는 만들지 않습니다** — ROADMAP §7의 "Discord 상주 리스너 금지"는 앱에도 적용되며, 이건 미구현이 아니라 **설계상 금지**입니다.

### Phase 5 — 패키징·서명·배포 (L)

3-러너 매트릭스. **macOS는 내부 .so/.dylib를 안쪽부터 개별 서명**(`--deep` 금지 — frozen 파이썬 번들을 잘못 서명함) 후 공증·스테이플.

**Windows는 v0.1을 미서명으로 냅니다.** SHA-256을 릴리스 페이지에 게시하고 SmartScreen 경고 스크린샷과 클릭 방법을 README에 넣습니다. 아무도 앱을 안 써본 시점에 인증서 조달로 한 달을 쓰지 않습니다. → v0.3에서 SignPath Foundation(무료, OSS 대상) 신청, 거절 시 Azure Trusted Signing.

**자동 업데이트는 만들지 않습니다.** GitHub Releases API 1회 호출 → 새 버전이면 배너. 약 50줄, 인프라 0, 오프라인에서 조용히 실패.

## 5. 바꿔야 할 원칙

| 원칙 | 처리 |
|------|------|
| §2.1 경량 패키지 (상주 서비스 금지) | **분리** — 앱은 **별도 레포**(`ai-company-desktop`)에서 companyctl을 버전 고정 라이브러리로 소비. 이 레포는 docs+templates+scripts로 유지. 앱 자체도 상주가 아님(창 닫으면 종료, 감시는 init) |
| §2.6 Python stdlib 전용 | **분리 + 정정** — `companyctl.py`는 계속 stdlib 전용(CI가 강제). 앱 레포만 pywebview·PyInstaller 2개 예외. **그리고 "Windows 패리티 구조적 해결"은 삭제** — 사실이 아님 |
| §2.4 시크릿은 레포 밖 | **강화** — 레포 밖이자 **앱 디렉터리 밖**. compose 시크릿을 `~/.hermes/ai-company/compose/secrets/`(0600)로 |
| §3.1 벤더링 금지 | **유지 + 명시** — 설치 파일이어도 마찬가지. *"소스는 안 복사했고 이미지만 담았다"* 는 이 원칙이 막으려는 바로 그 합리화 |
| §5.3 supervisor 금지 | **확장** — 앱도 supervisor가 아니다. 등록·관측·조작만 |
| §7 상주 리스너 금지 | **재확인** — Meeting Console은 라이브 피드가 아님 |

## 6. 비목표

자동 업데이트 프레임워크 · 트레이 데몬 · 라이브 Discord 피드 · Paperclip 번들(BREAK 1) · Windows 네이티브 생명주기(BREAK 3) · 자체 비용 대시보드 · 봇 자동 생성(불가)

## 7. 최대 리스크

**앱 아래 런타임 계층 전체가 미검증인데, 앱의 대표 약속("버튼 하나로 회사 기동")이 거기 직결돼 있습니다.**

지금까지 검증된 것은 `docker compose config` 파싱과 **스텁 게이트웨이** 대상 네이티브 경로뿐입니다. 진짜 Hermes 컨테이너도, 진짜 Hermes 바이너리도 한 번도 돌려보지 않았습니다.

가장 무서운 실패 모드는 **조용한 실패**입니다 — 컨테이너 5개가 전부 같은 기본 프로필로 뜨면, `docker compose ps`는 초록이고 Dashboard 타일 5개도 초록인데 **봇 5개가 한 인격으로 대답합니다.** 그래서 Dashboard가 프로세스 생존이 아니라 **신원 5종의 상이함**을 확인해야 합니다.

CLI 사용자는 잘못된 호출을 만나면 한 줄 고치고 넘어갑니다. 설치 파일 사용자는 **서명된 바이너리 안에서, 터미널 없이, 첫 실행 마법사에서** 그것을 만납니다.
