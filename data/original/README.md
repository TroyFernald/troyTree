# Troy Tree Research Pilot

This package is a small proof-of-concept local research database created from the Ancestry GEDCOM export plus a first web-research pass.

Files:
- `troy_tree_research_pilot.sqlite` - local SQLite database with persons, evidence candidates, and a research queue.
- `persons.csv` - selected direct ancestors from the GEDCOM.
- `evidence_candidates.csv` - public-web evidence leads found in the pilot search.
- `research_queue.csv` - suggested next searches.

Important: evidence rows are review candidates, not automatic tree edits. FamilySearch, WikiTree, Find a Grave, and personal genealogy pages can be useful leads, but original records should be preferred before updating the master tree.
