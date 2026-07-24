#Requires -Version 5.1
<#
.SYNOPSIS
  DEPRECATED: one-time bootstrap to first-publish this repo. It is already
  public, so day-to-day operation does not need this. Kept for history only.
  Create public contentscoin/ai-company-discord and push this folder.
  Run in PowerShell where `gh` is logged in as an account that can create repos.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Owner = if ($env:GITHUB_OWNER) { $env:GITHUB_OWNER } else { "contentscoin" }
$RepoName = if ($env:REPO_NAME) { $env:REPO_NAME } else { "ai-company-discord" }
$Full = "$Owner/$RepoName"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Error "GitHub CLI (gh) not found. Install: winget install GitHub.cli"
}

if (-not (Test-Path .git)) {
  git init -b main
  git add .
  git commit -m "Initial commit: Discord-first AI Company OS"
}

$exists = $true
gh repo view $Full 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { $exists = $false }

if (-not $exists) {
  Write-Host "Creating public repo $Full ..."
  gh repo create $Full --public --source=. --remote=origin --push `
    --description "Discord-first AI Company OS: Hermes souls, GJC roles, Paperclip + OpenCrab"
  Write-Host "Done: https://github.com/$Full"
  exit 0
}

Write-Host "Repo $Full already exists — pushing..."
git remote remove origin 2>$null
git remote add origin "https://github.com/$Full.git"
git push -u origin HEAD:main
Write-Host "Pushed: https://github.com/$Full"
