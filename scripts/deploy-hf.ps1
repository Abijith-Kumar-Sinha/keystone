# Push this repo to a Hugging Face Space (Docker SDK). Run from the repo root, after the code is committed.
#   scripts\deploy-hf.ps1 -User your-hf-username [-Space keystone]
# 1. Create the Space first: huggingface.co/new-space, SDK Docker, public, name "keystone".
# 2. Git will ask for your HF username and, as the password, a WRITE token (huggingface.co/settings/tokens).
#    This script never reads or stores the token; Git's credential prompt does.
param([Parameter(Mandatory = $true)][string]$User, [string]$Space = "keystone")
$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$start = (git rev-parse --abbrev-ref HEAD).Trim()
if (git status --porcelain) { throw "Commit your changes first (git status is not clean)." }
git checkout -B hf-deploy | Out-Null
try {
    # Spaces read their config from a YAML header on README.md; the GitHub README stays clean on main.
    $header = "---`ntitle: Keystone`nsdk: docker`napp_port: 7860`npinned: false`n---`n`n"
    $readme = [System.IO.File]::ReadAllText((Join-Path (Get-Location) "README.md"), $utf8)
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) "README.md"), $header + $readme, $utf8)
    git add README.md
    git commit -m "Space header" | Out-Null
    git push --force "https://huggingface.co/spaces/$User/$Space" "hf-deploy:main"
    Write-Host ""
    Write-Host "Pushed. The first build takes a few minutes: https://huggingface.co/spaces/$User/$Space"
    Write-Host "Live app: https://$($User.ToLower())-$($Space.ToLower()).hf.space   MCP: .../mcp   health: .../api/health"
}
finally {
    git checkout $start | Out-Null
    git branch -D hf-deploy 2>$null | Out-Null
}
