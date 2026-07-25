# Paperclip 연동 — 실측 계약

> **전부 실측입니다.** `paperclipai@2026.722.0`을 이 저장소 개발 환경에서 실제로 기동하고, API를 호출해 확인한 내용만 적습니다. 추정이 필요한 곳은 추정이라고 표시합니다. (실측 원칙: [ROADMAP.md](./ROADMAP.md) §3.2)

## 1. 설치와 기동

```bash
npx -y paperclipai onboard --yes     # 온보딩 체크 9종 → 서버 기동
# 서버: http://127.0.0.1:3100 (기본), UI 포함
```

- DB는 `DATABASE_URL` 미설정 시 **embedded PostgreSQL** (기본 `~/.paperclip/instances/default/db`, 포트 54329)
- 설정 파일: `~/.paperclip/instances/default/config.json`
- 기본 배포 모드: **`local_trusted`** — loopback 바인드, **루프백 요청은 인증 불필요** (실측: 무헤더 요청이 200)

### 루트(컨테이너)에서 기동할 때 — 실측한 함정 2가지

Paperclip의 embedded-postgres는 `createPostgresUser: false`로 고정되어 있습니다. root로 실행하면 라이브러리가 **시스템에 이미 있는 `postgres` 유저**로 `initdb`를 실행하는데, 두 가지가 터집니다:

| 증상 | 원인 | 해결 |
|------|------|------|
| `spawn .../initdb EACCES` | `postgres` 유저가 npm 캐시 경로를 통과 못 함 (`/root/.npm` 등이 700) | 설치 경로 디렉터리 체인에 `chmod o+x` |
| `Postgres init script exited with code 1` (버퍼 로그는 `fixing permissions ...`에서 끊김) | 실제 stderr: `initdb: could not change permissions of directory ... Operation not permitted` — 데이터 디렉터리가 root 소유인데 initdb는 postgres 유저로 실행됨 | `chown postgres:postgres ~/.paperclip/instances/default/db` 후 재기동 |

일반 데스크톱(비 root 사용자)에서는 해당 없음 — postgres가 root 실행을 거부해서 생기는 컨테이너 특유의 문제입니다. [ORCHESTRATION.md](./ORCHESTRATION.md) 컨테이너 경로에 반영되어 있습니다.

## 2. 인증

| 모드 | 인증 |
|------|------|
| `local_trusted` (onboard 기본) | 루프백 요청 무인증 (실측) |
| 그 외 (hosted 등) | bearer / `x-api-key` (dist 미들웨어 실측; 라이브 미검증) |

`companyctl`은 `PAPERCLIP_API_KEY` 환경변수가 있으면 `Authorization: Bearer`로 보내고, 없으면 헤더를 생략합니다. 키는 **환경변수로만** — 플래그·파일·로그 금지 (레포 공통 원칙).

## 3. 이슈 생성 계약

**엔드포인트**: `POST {base}/api/companies/{companyId}/issues`

- `POST /issues` 같은 회사 무관 경로는 **존재하지 않음** (실측 404)
- 스키마는 비엄격: 모르는 필드는 **에러 없이 조용히 버려짐** — 예전 `{title, body, owner, due}` 페이로드는 201이 떨어지지만 **본문이 통째로 유실**된 빈 이슈가 생김 (실측)

측정된 필드 (`createIssueBaseSchema`):

| 필드 | 타입 | 비고 |
|------|------|------|
| `title` | string, 필수 (min 1) | |
| `description` | string, 선택 | 멀티라인 허용 |
| `priority` | enum, 기본 `medium` | |
| `assigneeAgentId` | uuid, 선택 | **존재하지 않는 uuid면 404 "Agent not found"** (실측) |
| `projectId`, `status`, `workMode` 등 | 선택 | companyctl은 사용하지 않음 |

`OWNER:`/`DUE:`는 생성 스키마에 없으므로 companyctl은 description 말미에 텍스트로 실어 보냅니다.

## 4. companyctl 연동

```bash
export PAPERCLIP_COMPANY_ID=<회사 uuid>          # 또는 --paperclip-company
export PAPERCLIP_API_KEY=<키>                    # local_trusted면 생략 가능
python3 scripts/companyctl.py decision --to-paperclip < close-block.txt
```

- 회사 id 없음 → 이슈를 만들지 않고 **페이로드를 출력** (복사해서 수동 등록 가능)
- 서버 불통/HTTP 오류 → 몇 건 만들다 실패했는지와 **남은 페이로드**를 출력
- ACTION의 owner가 `roles[].paperclipAgentId`(uuid)를 가진 역할이면 `assigneeAgentId`로 매핑 — [templates/company.discord.json](./templates/company.discord.json)에 역할별로 선택 기입

라이브 왕복 실측: 한국어 DECISION 블록 → `AIC-3`/`AIC-4` 생성, `paperclipAgentId` 매핑 시 `AIC-5`에 hermes_local 에이전트 uuid가 assignee로 박히는 것까지 확인.

## 5. 어댑터 레지스트리 — hermes / cursor 는 내장

`GET /api/adapters` 실측 (14종 전부 `source: "builtin"`, `loaded: true`):

| 어댑터 | 모델 수 | 이 프로젝트와의 관계 |
|--------|---------|---------------------|
| `hermes_local` | 0 (게이트웨이 위임) | **Hermes 프로필 ↔ Paperclip 에이전트 연결의 정답** — 별도 설치 불필요 |
| `hermes_gateway` | 0 | 원격 게이트웨이 연결용 |
| `cursor` | **39** | Cursor CLI(`agent`) 실행 어댑터 — **구독 요금제 과금 경로 실측 확인** (§5.1) |
| `cursor_cloud` | 0 | Cursor Cloud Agents 위임 — `CURSOR_API_KEY` **필수** (없으면 즉시 `"CURSOR_API_KEY is required for cursor_cloud"` 실측) |
| `claude_local` / `codex_local` / `gemini_local` / … | 8 / 14 / 8 | 위성 코딩 에이전트 |

- 어댑터들은 `@paperclipai/adapter-*` 패키지로 서버에 **번들**되어 있습니다 — `@paperclipai/hermes-paperclip-adapter`도 그 중 하나. [공식 어댑터 레포](https://github.com/NousResearch/hermes-paperclip-adapter) README의 `registry.ts` 수동 등록 절차는 **소스 체크아웃 전용**이며 npx/npm 배포판에서는 불필요합니다 (Phase 6.1 결론).
- 외부 어댑터는 `POST /api/adapters/install {packageName, version}`으로 동적 설치 가능 (인스턴스 관리자).

### 5.1 `cursor` 어댑터의 과금 주체 — 원질문의 답 (dist 실측)

`@paperclipai/adapter-cursor-local`의 `execute.js`에서 그대로 읽은 로직:

```js
function resolveCursorBillingType(env) {
    return hasNonEmptyEnvValue(env, "CURSOR_API_KEY") || hasNonEmptyEnvValue(env, "OPENAI_API_KEY")
        ? "api"
        : "subscription";
}
// billingType === "subscription" 이면 biller = "cursor"
```

| 인증 방법 | billingType | 과금 주체 |
|-----------|-------------|-----------|
| `agent login` (Cursor CLI 네이티브 로그인) | `subscription` | **커서 구독 요금제** |
| `CURSOR_API_KEY` / `OPENAI_API_KEY` env | `api` | API 사용량 과금 |

- 실행은 로컬 **`agent` CLI**를 스폰합니다 (`config.command` 기본값 `"agent"`, `cursor-agent`도 인식). 모델 목록도 `agent models` 출력 파싱 + 패키지 내 폴백 목록(39종)
- 어댑터 자체 점검 메시지가 두 경로를 명시합니다: *"Set CURSOR_API_KEY in adapter env or run `agent login`."* / *"Cursor is authenticated via `agent login`."*
- `adapterType: "cursor"` 에이전트 생성은 라이브 확인 (이 샌드박스에는 `agent` CLI가 없어 **실행**은 사용자 환경에서 검증 필요)

에이전트 생성 실측:

```bash
curl -X POST http://127.0.0.1:3100/api/companies/$CID/agents \
  -H "Content-Type: application/json" \
  -d '{"name":"CTO","adapterType":"hermes_local","adapterConfig":{"model":"Hermes-4.5","maxIterations":20}}'
# → 201, id(uuid) 반환 — 이 uuid를 roles[].paperclipAgentId에 기입
```

## 6. Phase 6.2 결론 — 커서 요금제 경로는 둘, 정답은 어댑터

§5.1 실측으로 원질문("커서 요금제로 프로필 작동")의 실행 축 답이 확정됐습니다:

| 경로 | 인증 | 과금 | 요구사항 |
|------|------|------|----------|
| **Paperclip `cursor` 어댑터** (권장) | `agent login` | **구독 요금제** | Cursor CLI 설치 + 로그인. API 키·이그레스 불필요 |
| `companyctl delegate` (Cloud Agents) | `CURSOR_API_KEY` | 플랜 크레딧 풀 (API) | `api.cursor.com` 도달 가능해야 함 |

프로필 5개의 **대화**(Hermes 게이트웨이)는 여전히 LLM 키입니다 — 이 경계는 변하지 않습니다 ([COSTS.md](./COSTS.md)). 남은 검증은 사용자 환경 1회: Cursor CLI 로그인 상태에서 `adapterType: "cursor"` 에이전트에 이슈를 배정해 실행·과금이 구독으로 잡히는지 확인. [ALIGNMENT.md](./ALIGNMENT.md) §Phase 6.2에서 추적.
