# Project Setup Report

## Files Found

| File | Found | Size |
| --- | --- | ---: |
| Troy Tree.ged | True | 3587099 |
| troy_tree_research_pilot.sqlite | True | 28672 |
| persons.csv | True | 1108 |
| evidence_candidates.csv | True | 3661 |
| research_queue.csv | True | 1137 |
| README.md | True | 721 |

## Missing Expected Files

None.

## Pilot SQLite Tables

- `evidence_candidates`: 9 rows
  - Columns: id, person_id, source_title, source_url, evidence_type, claimed_facts, confidence, action, status
- `persons`: 7 rows
  - Columns: person_id, generation, name, sex, birth_date, birth_place, death_date, death_place, ancestry_source_count, ancestry_source_titles
- `research_queue`: 7 rows
  - Columns: person_id, priority, reason, next_search, status

## Working SQLite Tables

- `direct_ancestor_audit`: 2825 rows
  - Columns: audit_id, person_id, person_name, generation, birth_date, birth_place, death_date, death_place, spouse_names, parent_names, source_count, confidence_status, audit_flags, priority, notes
- `duplicate_candidates`: 760 rows
  - Columns: duplicate_id, left_person_id, right_person_id, left_name, right_name, score, reason, review_status
- `evidence_candidates`: 9 rows
  - Columns: evidence_id, person_id, person_name, source_title, source_type, source_url, source_site, claimed_birth_date, claimed_birth_place, claimed_death_date, claimed_death_place, claimed_spouse, claimed_parents, claimed_children, summary, transcription, confidence_score, confidence_label, conflicts, date_found, review_status, review_notes
- `family_relationships`: 10872 rows
  - Columns: relationship_id, family_id, person_id, related_person_id, relationship_type, notes
- `people`: 3761 rows
  - Columns: person_id, gedcom_id, full_name, given_name, surname, birth_date, birth_place, death_date, death_place, spouse_names, parent_names, generation, relationship_to_root, source_count, confidence_status, notes
- `proposed_updates`: 0 rows
  - Columns: update_id, person_id, person_name, field_name, current_value, proposed_value, reason, supporting_evidence_ids, confidence_score, review_status, review_notes
- `research_queue`: 1183 rows
  - Columns: queue_id, person_id, person_name, priority, reason, search_terms, target_sources, status, assigned_to, created_date, last_researched_date, notes

## CSV Columns

- `persons.csv`: 7 rows
  - Columns: person_id, generation, name, sex, birth_date, birth_place, death_date, death_place, ancestry_source_count, ancestry_source_titles
- `evidence_candidates.csv`: 9 rows
  - Columns: id, person_id, source_title, source_url, evidence_type, claimed_facts, confidence, action, status
- `research_queue.csv`: 7 rows
  - Columns: person_id, priority, reason, next_search, status

## Recommended Next Steps

1. Review all `needs_review` evidence before changing any master tree data.
2. Resolve the Daniel Smith Meservie death-date conflict against an original record or cemetery source.
3. Prioritize direct ancestors with zero sources or only `Ancestry Family Trees` source coverage.
4. Add original record searches for Maine, New Hampshire, Massachusetts, and Nova Scotia ancestors in generations 4 through 8.
5. Keep `data/original/` read-only and run all SQLite work from `data/working/research.sqlite`.
