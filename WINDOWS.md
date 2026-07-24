# Windows에서 public 레포로 배포하기

이 폴더는 Cloud Agent 안의 `.tar.gz`가 **아닙니다**. GitHub에서 clone/ZIP으로 받은 뒤 아래를 실행하세요.

## 1) 사전 준비

```powershell
winget install GitHub.cli Git.Git
gh auth login
```

`contentscoin` org에 레포를 만들 권한이 있는 계정으로 로그인하세요.

## 2) 이 패키지 받기

**방법 A — 브랜치 clone (권장)**

```powershell
cd $HOME
git clone --branch publish/ai-company-discord --single-branch `
  https://github.com/contentscoin/bni-trafficlight-multi.git ai-company-discord
cd ai-company-discord
```

**방법 B — ZIP**

브라우저에서:
`https://github.com/contentscoin/bni-trafficlight-multi/archive/refs/heads/publish/ai-company-discord.zip`
다운로드 후 압축 해제 → 폴더로 이동.

## 3) public 레포 생성 + push

```powershell
cd ai-company-discord
powershell -ExecutionPolicy Bypass -File .\scripts\publish-github.ps1
```

성공 시: https://github.com/contentscoin/ai-company-discord

## 4) (대안) GitHub 웹에서 빈 레포만 만들기

1. https://github.com/organizations/contentscoin/repositories/new
2. Repository name: `ai-company-discord`
3. Public, **README 없이** Create
4. 그다음:

```powershell
cd ai-company-discord
git remote remove origin -ErrorAction SilentlyContinue
git remote add origin https://github.com/contentscoin/ai-company-discord.git
git push -u origin main
```
