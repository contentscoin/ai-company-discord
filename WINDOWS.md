# Windows에서 운영하기

스크립트는 모두 **Python 3 표준 라이브러리**로 작성되어 별도 설치 패키지가 없습니다.
Windows에서는 `scripts/companyctl.ps1` 래퍼가 Python 실행기를 찾아 `companyctl.py`로 넘깁니다.

## 1) 사전 준비

```powershell
winget install Python.Python.3 Git.Git
python --version   # 3.10+ 권장
```

Python이 `python` / `python3` / `py -3` 중 무엇으로 잡혀도 래퍼가 자동 탐지합니다.

## 2) 설정 검증

```powershell
.\scripts\companyctl.ps1 validate
```

`templates/company.discord.json`을 스키마·파일시스템과 교차 검증합니다 (역할별 SOUL.md 존재, 채널 access/카테고리 유효성 등).

## 3) 프로필 스캐폴드

```powershell
.\scripts\companyctl.ps1 scaffold
```

`~/.hermes/profiles/<name>/`에 SOUL.md·config.yaml·.env를 생성합니다 (기존 파일은 보존, 재실행 안전).
`$env:HERMES_HOME`으로 위치를 바꿀 수 있습니다.

이후 절차(봇 토큰 입력, 게이트웨이 기동, 스모크 테스트)는 [SETUP.md](./SETUP.md)와 동일합니다.
문제가 생기면 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)를 참고하세요.

## PowerShell 실행 정책

스크립트 실행이 차단되면 현재 세션에만 허용:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 참고: 최초 발행 스크립트

`scripts/publish-github.ps1`(및 `.sh`)은 이 레포를 public GitHub에 **최초 1회** 올릴 때 쓰던 부트스트랩입니다. 레포가 이미 공개되어 일상 운영에는 필요 없으며, 역사적 참고용으로만 남겨 둡니다.
