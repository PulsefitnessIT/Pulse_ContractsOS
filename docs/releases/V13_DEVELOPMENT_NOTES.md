# Pulse Contracts OS V13 development checkpoint

Status: **development only**, not a production release.

## Implemented

- `app/v13_history.py` provides source-linked, coordinator-confirmed PPM visit history.
- `POST /api/contracts/{id}/ppm-visits` records Completed, Scheduled or Cancelled, requiring `confirmed=true`, a traceable source type/reference, and blocking duplicated contract/source references.
- `GET /api/contracts/{id}/ppm-visits` lists a contract's visit history, last confirmed completed service and optional next-service date calculated **only when** an explicit verified `interval_months` is supplied.
- Existing agreement fields and Excel Master are not changed when visits are added. The V12 service planner queue remains separately reviewed.
- `tests/v13_history.py` exercises confirmation, duplicates, future completion, status selection and calculation.

## Not implemented

- Customer profile and PPM frontend views for these new APIs.
- Automated contact enrichment; web research and manual verification are still required.
- Synchronisation with Sicon or any live system.
- Excel export of individual PPM history records (the eight-sheet approved Master is unchanged).
- Fully hosted office pilot, external security review, real invoice OCR benchmarking.

## Security and source migration

V12 archive includes a populated contracts database, original Excel Master, equipment JSON catalogue and customer PPM planner JSON. **Do not commit these into GitHub.** The published *source-only* bundle excludes `data/`, uploaded documents, ZIPs and private runtime data. Start with anonymised fixtures or restore operational data outside the repository in a secure pilot data volume.

Check the exact entry point and migration checklist before using the package. This source-only bundle cannot start its full business application without an approved Excel template and runtime data.
