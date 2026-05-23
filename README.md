# Troy Family Tree Research

Local genealogy research and cleanup system for the Troy family tree.

Working philosophy:

- Ancestry is the source and record-review platform.
- Google Drive stores files and exports.
- This local project does AI-assisted research and cleanup.
- SQLite stores candidate evidence.
- Nothing becomes genealogical fact until reviewed.

Private genealogy data is intentionally ignored by git. Source exports live in
`data/original/`, the working database lives in `data/working/`, and generated
review files live in `data/exports/`.

## First Run

```powershell
python -m src.import_pilot_data
python -m src.export_reports
```

