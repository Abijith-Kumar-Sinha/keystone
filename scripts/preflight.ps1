# Is everything ready to record the demo or to submit? Works on the local app or the deployed one.
#   scripts\preflight.ps1                                  # http://127.0.0.1:8000
#   scripts\preflight.ps1 -Url https://keystone-xxxx.onrender.com
param([string]$Url = "http://127.0.0.1:8000")
$ErrorActionPreference = "Stop"
$bad = 0
function Show($ok, $name, $detail = "") { if (-not $ok) { $script:bad++ }; "{0,-5} {1}{2}" -f $(if ($ok) { "OK" } else { "FAIL" }), $name, $(if ($detail) { "  ($detail)" } else { "" }) }
function Post($path, $body) { Invoke-RestMethod -Method Post -Uri ($Url + $path) -ContentType "application/json" -Body ($body | ConvertTo-Json -Depth 6) -TimeoutSec 120 }

try { $h = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 120 } catch { Show $false "app answers at $Url" $_.Exception.Message; exit 1 }
Show $true "app answers" "writable=$($h.writable)"
Show (($h.tenants -contains "falkordb") -and ($h.tenants -contains "pallets")) "both graphs are loaded" ($h.tenants -join ", ")
Show ($h.server_llm -eq $true) "a model is configured" $(if ($h.server_llm) { $h.models -join " then " } else { "router only: add LLM_API_KEY" })
foreach ($p in "/", "/workbench", "/static/workbench.js", "/static/fonts/bebas-neue.woff2") { Show ((Invoke-WebRequest -UseBasicParsing -Uri ($Url + $p) -TimeoutSec 60).StatusCode -eq 200) "GET $p" }

$box = (Post "/api/sandbox" @{ base = "falkordb" }).tenant
Show $true "private sandbox created" $box
$sw = [Diagnostics.Stopwatch]::StartNew()
$a = Post "/api/ask" @{ tenant = $box; question = "Who steps in for Anchel123?" }
$secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)
Show ($a.outcome -eq "answered") "the agent answers a question" "$secs s, tools: $((($a.trace | ForEach-Object { $_.tool }) -join ', '))"
if ($h.server_llm) { Show ($a.mode -eq "llm") "a model (not the router) wrote the answer" $(if ($a.mode -eq "llm") { $a.model } else { ($a.notes -join "; ") }) }
$p = Post "/api/tool" @{ tenant = $box; name = "succession_review"; args = @{ person = "Anchel123" } }
Show (($p.outcome -eq "answered") -and ($p.data.decision.status -eq "approved")) "the plan is approved" "$($p.data.plans.Count) pairings"
if ($h.writable -eq "sandbox") {                       # only in public mode: on a local app this call would really write into the shared graph
    $w = Post "/api/tool" @{ tenant = "falkordb"; name = "succession_review"; args = @{ person = "Anchel123" } }
    Show ($w.outcome -ne "answered") "the shared graph refuses writes"
}
""
if ($bad -eq 0) { "Everything is ready." } else { "$bad check(s) failed." }
