# 오케스트레이션 — 회사를 켜고 끄기

이 레포는 Hermes·Paperclip을 **복사하지 않습니다**. 대신 둘을 **함께 기동·감시·정지하는 계층**만 제공합니다. 업스트림 업그레이드는 버전 핀 한 줄 변경입니다.

경로는 두 가지이고, 원하는 쪽만 쓰면 됩니다.

| | 컨테이너 (권장) | 네이티브 |
|---|---|---|
| 기동 | `docker compose up -d` | `companyctl up` |
| 정지 | `docker compose down` | `companyctl down` |
| 로그 | `docker compose logs -f ceo` | `companyctl logs --profile ceo -f` |
| 상태 | `docker compose ps` | `companyctl status` |
| **자동 재시작** | ✅ `restart: unless-stopped` | ⚠️ `companyctl service`로 systemd/launchd 등록 필요 |
| 격리 | 컨테이너별 볼륨 | `~/.hermes/profiles/<name>/` |
| 사전 요구 | Docker | Hermes 설치 |

## A. 컨테이너 경로

### 1) 설정

```bash
cp .env.example .env                       # 버전 핀 (시크릿 없음)
for p in ceo cto loop growth critic; do
  cp "secrets/$p.env.example" "secrets/$p.env"
done
# 각 secrets/<profile>.env 에 그 봇 전용 DISCORD_BOT_TOKEN 을 넣습니다
```

`secrets/*.env`는 `.gitignore`에 걸려 있습니다. **토큰은 절대 커밋되지 않습니다.**

### 2) 기동

```bash
docker compose up -d          # 게이트웨이 5 + Paperclip
docker compose ps
docker compose logs -f ceo
```

Paperclip을 다른 곳에서 돌린다면 게이트웨이만:

```bash
docker compose up -d ceo cto loop growth critic
```

### 3) 설계 규칙

- **컨테이너 1개 = Hermes 홈 1개 = 프로필 1개 = 봇 토큰 1개.** 같은 토큰을 두 프로필에 쓰면 게이트웨이가 충돌하므로, 볼륨을 분리해 물리적으로 막았습니다
- **Paperclip 포트는 `127.0.0.1:3100`에만 바인딩**됩니다 — 네트워크에 노출되지 않습니다
- 업스트림은 **핀된 git ref에서 빌드**합니다(`HERMES_REF`). 소스를 이 레포에 복사하지 않으므로 업그레이드가 머지 충돌이 되지 않습니다

### 4) 업그레이드

```bash
# .env 에서 HERMES_REF=v1.4.0 으로 변경 후
docker compose build --pull && docker compose up -d
```

## B. 네이티브 경로

```bash
companyctl up                      # 5개 게이트웨이를 detached 로 기동
companyctl status                  # 몇 개가 살아있는지
companyctl logs --profile ceo -f
companyctl restart --profile cto   # 하나만
companyctl down
```

- `up`은 **이미 떠 있는 게이트웨이는 건드리지 않습니다.** 죽은 것만 다시 띄웁니다
- PID는 `~/.hermes/ai-company/gateways.json`, 로그는 `~/.hermes/ai-company/logs/<profile>.log` (둘 다 레포 밖)
- `HERMES_BIN`으로 hermes 실행 파일 경로를 바꿀 수 있습니다

### 자동 재시작은 init에 맡깁니다

`companyctl up`은 **감시자가 아닙니다** — CLI가 종료된 뒤에는 아무것도 되살릴 수 없습니다. 자체 supervisor를 만드는 대신 OS의 init에 등록합니다:

```bash
companyctl service --emit systemd --out ~/.config/systemd/user
systemctl --user daemon-reload
systemctl --user enable --now ai-company-hermes-ceo   # 프로필별로

# macOS
companyctl service --emit launchd --out ~/Library/LaunchAgents
launchctl load ~/Library/LaunchAgents/sh.aicompany.hermes.ceo.plist
```

`status`의 게이트웨이 집계는 **좀비 프로세스를 살아있다고 세지 않습니다**(부모인 CLI가 이미 종료돼 회수되지 않은 프로세스를 걸러냅니다).

## C. 이 레포가 하지 않는 일

[ROADMAP.md](./ROADMAP.md) §3의 업스트림 경계 그대로입니다.

| | 담당 |
|---|---|
| 에이전트 런타임·프로필·cron | Hermes (내장 스케줄러 사용) |
| 태스크·예산·감사 | Paperclip |
| **기동·감시·정지** | **이 레포** ← 업스트림 누구도 5-프로필 회사의 생명주기를 책임지지 않음 |

## D. 아직 검증되지 않은 것

> **먼저 이것부터 실행하세요.** 아래 미확인 항목 중 가장 중요한 것은 명령 하나로 판별됩니다:
>
> ```bash
> companyctl verify-runtime --out RUNTIME-CONTRACT.md
> ```
>
> 실제 Hermes가 설치된 기계에서 게이트웨이를 한 번 띄웠다 내리며 **`gateway start`가 포그라운드 프로세스인지 서비스 제어 명령인지**를 실측하고, 결과를 `RUNTIME-CONTRACT.md`로 남깁니다.
> 종료 코드 `0`이면 아래 네이티브 경로 설계가 맞습니다. **`1`이면 틀렸다는 뜻**이고(추적한 PID가 게이트웨이가 아님), 계약서가 무엇을 바꿔야 하는지 적어줍니다.

정직하게 남깁니다. 이 환경에는 Docker 데몬이 없어 **이미지 빌드와 실제 기동은 확인하지 못했습니다.**

- ✅ 확인됨: compose 스펙 유효(`docker compose config`), 6개 서비스·볼륨 해석, `HERMES_REF` 버전 핀이 빌드 context에 실제 반영
- ✅ 확인됨: 네이티브 `up`/`down`/`restart`/`logs`/`service` 전 경로 (스텁 게이트웨이로 기동·중복 방지·강제 종료 감지·선택 재기동까지)
- ⚠️ **미확인: 컨테이너가 프로필을 선택하는 방식.** 업스트림 이미지가 `HERMES_PROFILE` 환경변수를 읽는지 확인하지 못했습니다. 첫 `docker compose up` 때 게이트웨이가 엉뚱한(또는 기본) 프로필로 뜨면, 업스트림 이미지의 실제 진입점 규약에 맞게 각 서비스의 `environment`/`command`를 한 줄 조정해야 합니다
- ⚠️ 미확인: Paperclip을 `npx`로 컨테이너에서 띄우는 경로(내장 Postgres 초기화 포함)
- ⚠️ **미확인이자 이 설계의 최대 전제: `hermes -p <profile> gateway start`가 포그라운드 프로세스인가.** 네이티브 경로는 이 명령이 블로킹 프로세스라고 가정하고 PID를 추적합니다. 만약 업스트림에서 이것이 **서비스 제어 명령**(launchd/systemd/schtasks에 등록된 유닛을 기동시키고 즉시 반환)이라면, 기록된 PID는 게이트웨이가 아니라 제어 클라이언트이므로 `status`는 곧바로 DOWN을 보고하고 `up`은 중복 기동을 시도합니다. Hermes 문서 사이트(403)와 raw 문서 경로(404) 모두 접근하지 못해 `gateway install` 서브커맨드의 존재를 확인도 반증도 하지 못했습니다. **실제 Hermes 설치본에서 `hermes gateway --help`를 한 번 실행하면 즉시 판별됩니다** — 그 결과에 따라 네이티브 경로는 PID 추적 대신 업스트림 서비스 유닛에 위임하는 쪽으로 바뀌어야 합니다. 이 확인은 다른 무엇보다 먼저 이뤄져야 합니다
