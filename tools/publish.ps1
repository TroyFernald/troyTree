<#
  publish.ps1 — rebuild the family site from the research database and push it
  so Cloudflare Pages redeploys. This is the "auto-update from the project" step:
  run it after doing research, or schedule it (Task Scheduler) to run on a cadence.

  Usage:
    .\tools\publish.ps1                              # photos via relative paths
    .\tools\publish.ps1 -MediaBase https://media.troytree.org/   # photos from R2
    .\tools\publish.ps1 -ShowLiving                  # publish living people too

  Respects the project rules: only the GitHub repo is touched (Cloudflare Pages
  deploys itself); no database or media is committed to the site repo.
#>
param(
  [string]$MediaBase = "",
  [switch]$ShowLiving
)
$ErrorActionPreference = "Stop"
$project = "C:\tree\troy-family-tree-research"
$site = "C:\tree\troy-family-site"

# Build the site bundle from the current database.
$redact = if ($ShowLiving) { "False" } else { "True" }
$py = "import sys; from src.build_site import build_site; " +
      "print(build_site(media_base=sys.argv[1], redact_living=(sys.argv[2]=='True')))"
Push-Location $project
try { python -c $py $MediaBase $redact } finally { Pop-Location }

# Commit + push only if something changed (avoids empty commits / needless deploys).
git -C $site add -A
if (git -C $site status --porcelain) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
  git -C $site commit -m "Rebuild site from research database ($stamp)"
  git -C $site push
  Write-Host "Published: changes pushed; Cloudflare Pages will redeploy." -ForegroundColor Green
} else {
  Write-Host "No changes since last publish." -ForegroundColor Yellow
}
