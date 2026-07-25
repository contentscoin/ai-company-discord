# RUNTIME CONTRACT

실제 Hermes를 설치해 측정한 결과입니다. 이전까지 `ORCHESTRATION.md §D`에 "미확인"으로 남아 있던 가정들을 대체합니다.

- 측정일: 2026-07-25
- 대상: **hermes-agent 0.19.0 (2026.7.20)**, PyPI(`uv pip install hermes-agent`)
- 플랫폼: Linux (systemd 없는 컨테이너)

## 1. `hermes gateway` 서브커맨드 — 실측

```
{run,start,stop,restart,status,install,uninstall,list,setup,migrate-legacy,enroll}
```

| 커맨드 | 업스트림 설명 (원문) |
|--------|---------------------|
| `run` | *Run gateway in foreground (recommended for WSL, Docker, Termux)* |
| `start` | *Start the **installed** systemd/launchd background service* |
| `install` | *Install gateway as a systemd/launchd background service* |
| `list` | *List all profiles and their gateway status* |
| `status` `stop` `restart` `uninstall` | 서비스 제어 |

`gateway run`의 플래그: `--replace`, `--force`, `--no-supervise`, `--external-supervisor`
`gateway install`의 플래그: `--system`, `--start-now`, `--start-on-login`, `--run-as-user`

## 2. 판정: `start`는 포그라운드 프로세스가 **아니다**

**초기 설계는 틀렸습니다.** `companyctl up`은 `gateway start`를 호출했는데, 이는 *이미 설치된* 서비스를 기동시키는 명령입니다. systemd가 없는 환경에서 실행하니 이렇게 실패했습니다:

```
✗ User systemd not reachable:
  loginctl enable-linger was denied: System has not been booted with systemd as init system (PID 1).
```

**올바른 명령은 `gateway run`입니다.** 8초 관찰 결과 계속 살아 있었고(SIGTERM으로 종료), 실제 게이트웨이 배너와 로그를 냈습니다.

### 교차 검증 — PID 일치

`companyctl up`(수정 후)이 기록한 PID와 **Hermes 자신의 `gateway list`가 보고한 PID가 동일**합니다:

```
companyctl:  started : ceo(13620), cto(13621), loop(13622), growth(13623), critic(13624)

hermes gateway list:
  ✓ ceo     — PID 13620      ✓ cto     — PID 13621
  ✓ loop    — PID 13622      ✓ growth  — PID 13623
  ✓ critic  — PID 13624
```

업스트림이 그 PID를 게이트웨이로 인정합니다. PID 추적은 **`run`을 쓸 때만** 유효합니다.

## 3. Hermes는 멀티 프로필 생명주기를 이미 갖고 있다

`gateway list`가 스캐폴드한 5개 프로필을 전부 인식합니다. `gateway install`은 프로필별로 systemd 유닛/launchd plist를 **직접 작성**하며 `--start-on-login`으로 재부팅 생존까지 제공합니다.

> **따라서 `companyctl service`가 자체 유닛을 쓰던 것은 중복이자 경쟁이었습니다.** 지금은 `hermes gateway install`에 위임하고, 이 레포가 더하는 값은 **5개 프로필 팬아웃**뿐입니다.

## 4. Paperclip

- 패키지: `paperclipai@2026.722.0` — *"Paperclip CLI — orchestrate AI agent teams to run a business"*
- 의존성에 **`embedded-postgres@^18.1.0-beta.16` 실재 확인** → 설치 파일 번들 시 PostgreSQL 배포판과 제3자 라이선스가 따라옵니다 (데스크톱 설치 파일 기획의 라이선스 판정 근거)

## 5. 아직 측정하지 못한 것

- **컨테이너의 프로필 선택 방식** — 이 환경에 Docker 데몬이 없어 `docker compose up`을 실행하지 못했습니다. `gateway run`에 `--external-supervisor` / `--no-supervise` 플래그가 있는 것으로 보아 컨테이너 모드는 지원되지만, compose 서비스가 `HERMES_PROFILE`로 프로필을 고르는지는 미확인입니다.
  → `docker compose up -d` 후 **반드시** `companyctl doctor --online`으로 봇 신원 5종이 서로 다름을 확인하세요. 초록 컨테이너 5개는 프로필 5개의 증거가 아닙니다.
- 실제 Discord 토큰을 넣은 상태의 게이트웨이 동작 (토큰 없이 뜬 게이트웨이는 *"No messaging platforms enabled"* 경고를 냅니다)

## 6. 핀

이 계약은 **hermes-agent 0.19.0** 기준입니다. 업스트림이 `gateway` 동사 체계를 바꾸면 재측정이 필요합니다:

```bash
companyctl verify-runtime --out RUNTIME-CONTRACT.md
```
