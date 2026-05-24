<#
  refresh.ps1 — auto-add pipeline. Ingest every research finding in
  data/exports/findings/, rebuild the whole site (which also picks up
  noble_images.json portraits/castles and the password gate), and deploy the
  live site to Cloudflare Pages. Run after any research agent finishes.

  Usage:  .\tools\refresh.ps1
#>
$ErrorActionPreference = "Stop"
$proj = "C:\tree\troy-family-tree-research"
Set-Location $proj

Write-Host "1/3  Ingesting findings..." -ForegroundColor Cyan
python -m src.record_findings data\exports\findings

Write-Host "2/3  Rebuilding site..." -ForegroundColor Cyan
python -c "from pathlib import Path; from src.build_site import build_site; print(build_site(media_base='/media/', out_dir=Path(r'C:/troytree-dist/pub')))"

Write-Host "3/3  Deploying to Cloudflare Pages..." -ForegroundColor Cyan
npx --yes wrangler pages deploy C:/troytree-dist/pub --project-name=troytree --branch=main --commit-dirty=true

Write-Host "Done - live changes are on troytree.pages.dev" -ForegroundColor Green
