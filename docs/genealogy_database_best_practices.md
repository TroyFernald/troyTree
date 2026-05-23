# Genealogy Database Best Practices

This project should use an evidence-first workflow: imports create candidate
evidence and review tasks; human review creates accepted conclusions.

## Recommended Model

- `import_batch`: immutable provenance for each GEDCOM or external import.
- `raw_record`: original GEDCOM/source records, including unknown/custom tags.
- `repository`, `source`, `citation`: separate where a record is held, what the
  source is, and the exact page/image/URL supporting a claim.
- `evidence_assertion`: extracted claims from records before acceptance.
- `person`, `event`, `relationship`: reviewed conclusions only.
- `conclusion_evidence`: join table linking accepted conclusions to supporting
  assertions.
- `review_task`: proposed inserts, updates, merges, conflicts, and audit issues.
- `merge_plan` / `merge_decision`: reviewed duplicate-resolution workflow.
- `change_log`: append-only record of accepted/rejected decisions.

## Key Rules

- Preserve original GEDCOM XREFs like `@I123@`, `@F42@`, and `@S7@`.
- Store raw date/place text and normalized values; do not discard `ABT`, `BET`,
  `CAL`, `EST`, or uncertain imported values.
- Treat GEDCOM family links as relationship containers, not proof.
- Do not auto-merge duplicate-looking people.
- Do not treat public trees or profile pages as proof.
- Keep confidence scoring separate from review status.
- Every accepted direct-ancestor fact should point to supporting evidence.
- Conflicting assertions should coexist until a reviewer writes a conclusion.

## Duplicate Detection

Repeated names across generations are expected in genealogy. A duplicate
candidate should require more than name similarity:

- compatible birth/death years or exact dates
- spouse overlap
- parent/child overlap
- shared place context
- shared source/citation clues

Conflicting years, incompatible generations, or unrelated parent/spouse context
should lower the score or block the candidate from review.

## Review Workflow

1. Generate candidate evidence or duplicate pairs.
2. Show side-by-side evidence and citations.
3. Reviewer accepts, rejects, defers, or creates a merge plan.
4. Accepted conclusions link back to evidence assertions.
5. Old/superseded people are preserved as aliases or inactive records.
6. Export only reviewed conclusions unless a report is explicitly for review.

## Sources

- FamilySearch GEDCOM specs: https://gedcom.io/specs/
- GEDCOM 7 specification: https://gedcom.io/specifications/FamilySearchGEDCOMv7.html
- FamilySearch GEDCOM overview: https://www.familysearch.org/en/gedcom/
- Evidence Explained, sources vs. information vs. evidence vs. proof:
  https://evidenceexplained.com/content/quicklesson-2-sources-vs-information-vs-evidence-vs-proof
- Evidence Explained analysis process map:
  https://evidenceexplained.com/content/quicklesson-17-evidence-analysis-process-map
- Gramps SQL schema: https://www.gramps-project.org/wiki/index.php/SQL_Schema
- SQLite foreign keys: https://www.sqlite.org/foreignkeys.html
- SQLite transactions: https://www.sqlite.org/lang_transaction.html
- SQLite backup API: https://www.sqlite.org/backup.html
