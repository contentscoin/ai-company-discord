# 오케스트레이션 — 회사를 켜고 끄기

이 레포는 Hermes·Paperclip을 **복사하지 않습니다**. 대신 둘을 **함께 기동·감시·정지하는 계층**만 제공합니다. 업스트림 업그레이드는 버전 핀 한 줄 변경입니다.

경로는 두 가지이고, 원하는 쪽만 쓰면 됩니다.

| | 컨테이너 (권장) | 네이티브 |
|---|---|---|
| 기동 | `docker compose up -d` | `companyctl up` |
| 정지 | `docker compose down` | `companyctl down` |
| 로그 | `docker compose logs -f ceo` | `companyctl logs --profile ceo -f` |
| 상태 | `docker compose ps` | `companyctl status` |
| **자동 재시작** | ✅ `restart: unless-stopped` | ✅ `companyctl service --apply` (= `hermes gateway install` 팬아웃) |
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

### 자동 재시작은 Hermes 에 맡깁니다

`companyctl up`은 **감시자가 아닙니다** — CLI가 종료된 뒤에는 아무것도 되살릴 수 없습니다. 그리고 자체 유닛을 쓸 필요도 없습니다: **Hermes가 이미 프로필별 서비스 등록을 제공합니다**(`gateway install`이 systemd 유닛/launchd plist를 직접 작성).

```bash
companyctl service                                  # dry-run: 무엇을 실행할지 출력
companyctl service --apply --start-now --start-on-login
hermes gateway list                                 # 등록 결과 확인
```

`companyctl service`가 더하는 값은 **5개 프로필 팬아웃**뿐입니다. 해제는 업스트림 명령 그대로:

```bash
hermes -p ceo gateway uninstall
```

`status`의 게이트웨이 집계는 **좀비 프로세스를 살아있다고 세지 않습니다**(부모인 CLI가 이미 종료돼 회수되지 않은 프로세스를 걸러냅니다).

> **`up`은 `hermes gateway run`을 씁니다** — `gateway start`가 아닙니다. `start`는 *이미 설치된* 서비스를 기동시키는 명령이라 PID를 추적할 수 없습니다. 근거는 [RUNTIME-CONTRACT.md](./RUNTIME-CONTRACT.md).

## C. 이 레포가 하지 않는 일

[ROADMAP.md](./ROADMAP.md) §3의 업스트림 경계 그대로입니다.

| | 담당 |
|---|---|
| 에이전트 런타임·프로필·cron | Hermes (내장 스케줄러 사용) |
| 태스크·예산·감사 | Paperclip |
| 게이트웨이 기동·감시·서비스 등록 | **Hermes** — `gateway run` / `install` / `list` / `status`가 프로필별로 이미 존재 |
| 5개 프로필 **팬아웃**과 Discord·회의·지식 계층 | **이 레포** |

> 초판에는 *"업스트림 누구도 5-프로필 회사의 생명주기를 책임지지 않는다"* 고 적었습니다. **틀렸습니다.** 실측 결과 `hermes gateway list`는 5개 프로필을 전부 인식하고 `gateway install`은 프로필별 서비스를 직접 등록합니다. 이 레포에 남는 몫은 그 위의 팬아웃뿐입니다 — [RUNTIME-CONTRACT.md](./RUNTIME-CONTRACT.md) §3.

## D. 검증 상태

**[RUNTIME-CONTRACT.md](./RUNTIME-CONTRACT.md)** — 실제 hermes-agent 0.19.0을 설치해 측정한 결과입니다.

- ✅ **측정됨**: `gateway run`이 포그라운드 프로세스이고 `start`는 서비스 제어 명령임. `companyctl up`이 기록한 PID 5개가 `hermes gateway list`가 보고한 PID와 **완전히 일치**
- ✅ **측정됨**: Hermes가 멀티 프로필 생명주기를 이미 제공(`list`/`install`/`status`)
- ✅ 확인됨: compose 스펙 유효(`docker compose config`), `HERMES_REF` 버전 핀이 빌드 context에 반영
- ⚠️ **미측정: 컨테이너의 프로필 선택 방식.** 이 환경에 Docker 데몬이 없습니다. `docker compose up -d` 후 **반드시** `companyctl doctor --online`으로 봇 신원 5종이 서로 다름을 확인하세요 — 초록 컨테이너 5개는 프로필 5개의 증거가 아닙니다
- ⚠️ 미측정: 실제 Discord 토큰이 들어간 상태의 게이트웨이 동작

재측정:

```bash
companyctl verify-runtime --out RUNTIME-CONTRACT.md
```
