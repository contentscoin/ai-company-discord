# CLAUDE.md — 에이전트 작업 규칙

## 작업 경계 (Board 지시, 2026-07-26)

- **작업 레포는 이 저장소(ai-company-discord) 하나뿐입니다.** 커밋·브랜치·PR·이슈는 여기에만 만듭니다.
- 원질문의 다른 레포들 — hermes-agent, paperclip, gjc-multivendor-setup-guide, akanjs,
  hermes-paperclip-adapter, hermes-ceo-console-installer, social-ai-team-custom, gbrain — 은
  **참고·분석 전용**입니다. 클론해서 읽고 실측하는 것은 허용되지만, 그 레포로의 푸시·PR·이슈
  생성은 금지입니다.
- 다른 레포에서 발견한 개선점·부채·제안은 그 레포에 반영하려 들지 말고, **이 저장소의 문서**
  (ALIGNMENT.md 등)에 기록해 Board에 보고합니다. 반영 여부는 각 프로젝트의 자율입니다.

## 작업 방식

- 실측 우선: 문서·추정보다 실행/클론/API 호출로 확인한 사실을 기록한다. 반증되면 원문을
  보존한 채 정정을 병기한다.
- 출하 전 검증 3종: `python3 scripts/companyctl.py validate`, `python3 -m unittest discover -s tests`,
  `python3 scripts/check_links.py`.
- 시크릿은 환경변수/`.env`로만 다루고 레포·로그·문서에 남기지 않는다 (`companyctl lint`가 게이트).
