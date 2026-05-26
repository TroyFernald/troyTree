<#
  make_handoff_bundle.ps1 - gather everything that is NOT in the git repo into one
  movable folder, so the project can be handed off to another PC.

  The code travels via git (github.com/TroyFernald/troyTree). This bundle is the
  rest: the working database, the 900 MB media library, the RootsMagic source,
  the curated/generated exports, and the secrets - none of which are committed.

  Usage:
    powershell -ExecutionPolicy Bypass -File tools\make_handoff_bundle.ps1
    powershell ... -Dest E:\troytree-handoff          # write to a USB drive
    powershell ... -IncludeDist                        # also copy C:\troytree-dist (2.8 GB; regenerable)

  Move the whole -Dest folder to the new PC, then run the RESTORE.ps1 it contains.
#>
param(
  [string]$Dest = "C:\troytree-handoff",
  [switch]$IncludeDist
)

$repo = "C:\tree\troy-family-tree-research"
$rc = "/E","/NFL","/NDL","/NJH","/NJS","/NP","/R:1","/W:1"   # quiet, resilient robocopy flags

New-Item -ItemType Directory -Force -Path "$Dest\repo-data" | Out-Null
New-Item -ItemType Directory -Force -Path "$Dest\Tree" | Out-Null

Write-Host "Copying repo data (db, exports, original, snapshots)..."
robocopy "$repo\data\working"   "$Dest\repo-data\working"   @rc | Out-Null
robocopy "$repo\data\exports"   "$Dest\repo-data\exports"   @rc | Out-Null
robocopy "$repo\data\original"  "$Dest\repo-data\original"  @rc | Out-Null
robocopy "$repo\data\snapshots" "$Dest\repo-data\snapshots" @rc | Out-Null
foreach ($f in "site_password.txt","access_allowlist.txt") {
  if (Test-Path "$repo\data\$f") { Copy-Item "$repo\data\$f" "$Dest\repo-data\$f" -Force }
}

Write-Host "Copying C:\Tree assets (RootsMagic source, media, news dropbox)..."
if (Test-Path "C:\Tree\ancestory-import.rmtree") { Copy-Item "C:\Tree\ancestory-import.rmtree" "$Dest\Tree\ancestory-import.rmtree" -Force }
robocopy "C:\Tree\ancestory-import_media" "$Dest\Tree\ancestory-import_media" @rc | Out-Null
if (Test-Path "C:\Tree\news_dropbox") { robocopy "C:\Tree\news_dropbox" "$Dest\Tree\news_dropbox" @rc | Out-Null }

if ($IncludeDist -and (Test-Path "C:\troytree-dist")) {
  Write-Host "Copying C:\troytree-dist (this is large)..."
  robocopy "C:\troytree-dist" "$Dest\troytree-dist" @rc | Out-Null
}

# --- write a RESTORE.ps1 the new PC runs to put everything back in place ---
$restore = @'
# RESTORE.ps1 - run on the NEW PC after cloning the repo and copying this bundle here.
# Assumes the repo was cloned to C:\tree\troy-family-tree-research. Edit $repo if not.
param([string]$repo = "C:\tree\troy-family-tree-research")
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rc = "/E","/NFL","/NDL","/NJH","/NJS","/NP"
Write-Host "Restoring repo data into $repo\data ..."
robocopy "$here\repo-data\working"   "$repo\data\working"   @rc | Out-Null
robocopy "$here\repo-data\exports"   "$repo\data\exports"   @rc | Out-Null
robocopy "$here\repo-data\original"  "$repo\data\original"  @rc | Out-Null
robocopy "$here\repo-data\snapshots" "$repo\data\snapshots" @rc | Out-Null
foreach ($f in "site_password.txt","access_allowlist.txt") {
  if (Test-Path "$here\repo-data\$f") { Copy-Item "$here\repo-data\$f" "$repo\data\$f" -Force }
}
Write-Host "Restoring C:\Tree assets ..."
New-Item -ItemType Directory -Force -Path "C:\Tree" | Out-Null
if (Test-Path "$here\Tree\ancestory-import.rmtree") { Copy-Item "$here\Tree\ancestory-import.rmtree" "C:\Tree\ancestory-import.rmtree" -Force }
robocopy "$here\Tree\ancestory-import_media" "C:\Tree\ancestory-import_media" @rc | Out-Null
if (Test-Path "$here\Tree\news_dropbox") { robocopy "$here\Tree\news_dropbox" "C:\Tree\news_dropbox" @rc | Out-Null }
New-Item -ItemType Directory -Force -Path "C:\troytree-dist\pub\media" | Out-Null
Write-Host "Done. Next: pip install -r requirements.txt, npm install, wrangler login, then rebuild (see HANDOFF.md)."
'@
Set-Content -Path "$Dest\RESTORE.ps1" -Value $restore -Encoding utf8

# --- manifest ---
$man = Get-ChildItem -Recurse -File $Dest -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum
$lines = @(
  "Troy Family Tree - handoff bundle",
  ("created: " + (Get-Date -Format s)),
  ("total:   {0:N1} MB, {1} files" -f ($man.Sum/1MB), $man.Count),
  "",
  "Contents (local-only assets NOT in the git repo):",
  "  repo-data\working\research.sqlite   the live working database (SOURCE OF TRUTH; living-relative data - keep private)",
  "  repo-data\exports\                  generated site HTML + curated research (deep_dives, dd_batch*, findings, geocode cache)",
  "  repo-data\original\                 original import sqlite",
  "  repo-data\site_password.txt         site gate password",
  "  repo-data\access_allowlist.txt      access allowlist",
  "  Tree\ancestory-import.rmtree        RootsMagic source tree (the genealogy master)",
  "  Tree\ancestory-import_media\        ~955 MB photo/document library",
  "  Tree\news_dropbox\                  newspaper-clipping drop folder",
  "",
  "TO RESTORE on the new PC:",
  "  1. git clone https://github.com/TroyFernald/troyTree.git C:\tree\troy-family-tree-research",
  "  2. copy this whole folder to the new PC, then:  powershell -ExecutionPolicy Bypass -File .\RESTORE.ps1",
  "  3. follow HANDOFF.md in the repo for prerequisites, auth, and deploy."
)
Set-Content -Path "$Dest\MANIFEST.txt" -Value $lines -Encoding utf8

Write-Host ""
Write-Host ("Bundle ready at $Dest  ({0:N1} MB, {1} files)" -f ($man.Sum/1MB), $man.Count)
Write-Host "Move that folder to the new PC and run its RESTORE.ps1 (see MANIFEST.txt / HANDOFF.md)."
