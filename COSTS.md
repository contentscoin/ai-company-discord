# 비용 가시성

> **진실원천은 Paperclip입니다.** Paperclip이 에이전트·모델별 사용량·예산을 추적합니다 ([README](./README.md) 스택 표). 이 문서는 **Paperclip을 아직 안 쓰는 경우**를 위한 최소 안내입니다. 이 레포는 자체 비용 추적 로직을 만들지 않습니다 (경량 원칙 — [ROADMAP.md](./ROADMAP.md) §3 업스트림 경계).

## modelHint

각 역할이 어떤 모델/프로바이더를 쓰는지 `company.discord.json`의 `roles[].modelHint`에 적어 둡니다. 이건 계약이 아니라 **비용 추적 지점을 가리키는 힌트**입니다.

```bash
python3 scripts/companyctl.py doctor   # modelHint 미설정 역할을 WARN
```

기본값(예시, [ROUTING.md](./ROUTING.md)의 모델 힌트 열 기준):

| 역할 | modelHint | 사용량 확인 |
|------|-----------|-------------|
| CEO | `anthropic/opus` | Anthropic Console → Usage |
| CTO | `cursor (codex/claude satellites)` | Cursor 대시보드 + OpenAI/Anthropic Usage |
| Loop | `gemini/opus-longform` | Google AI Studio / Anthropic Console |
| Growth | `anthropic/sonnet` | Anthropic Console → Usage |
| Critic | `cross-family` | 본체와 다른 벤더의 Usage (교차 검증용) |

## 프로바이더별 사용량 확인 경로

| 프로바이더 | 위치 |
|-----------|------|
| Anthropic | console.anthropic.com → Settings → Usage / Billing |
| OpenAI | platform.openai.com → Usage |
| OpenRouter | openrouter.ai → Activity / Credits |
| Google (Gemini) | aistudio.google.com / Cloud Console → Billing |
| Cursor | cursor.com → Settings → Usage |

## 권장

- 토큰·API 키는 **레포에 넣지 않습니다** (`~/.hermes/profiles/<name>/.env`에만)
- 실사용/예산 알림·한도는 각 프로바이더 콘솔 또는 Paperclip에서 설정
- 모델 라우팅 방침은 [ROUTING.md](./ROUTING.md) (GJC `daily` / `coding-sprint` / `cyber-cop`)
