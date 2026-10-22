# Automatic completion and PostgreSQL

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

The completion workflow is a separate development workflow (`municipalCompletionDev`). Original agents and the prior strict workflow remain intact. Valid Vision observations whose only issue is meaningful uncertainty continue through deterministic routing and the native Knowledge API. Gate 2 remains REVIEW. Invalid observations, privacy failures and frame disagreements finish with a saved review record without inventing downstream inputs. Gate 3 is unchanged.

All outcomes reach one atomic PostgreSQL function: PASS creates OPEN, REVIEW creates NEEDS_REVIEW plus a persistent review record, and REJECT creates REJECTED. An unverified RAG procedure/deadline is retained only in the private audit payload, never published as an accepted procedure. A completed pipeline does not imply policy approval.

## Deployment scope

`Deploy_Development.ps1` creates only `municipal-ticket-postgres-dev`, using the already cached `postgres:17-alpine` image, a 256 MB memory limit, loopback port 5434 and named volume `municipal_ticket_development_data`. It joins the existing development n8n network. It briefly restarts development n8n to import a new credential and publish a separate workflow. It does not replace production or delete volumes. Creating this container/volume requires the owner's infrastructure approval.

Credentials are randomly generated into ignored `.runtime/persistence/`, never printed. n8n receives a limited login with permission to execute save/read functions; it cannot directly modify tables or invoke staff status changes. Administrator status updates use `municipal.change_status(tracking_uuid, expected_version, next_status, actor, note)` with an audit event and optimistic concurrency. A staff dashboard remains deferred.

The save function serializes concurrent requests with the same report ID. Identical input returns the existing ticket and never adds another creation event; changed content under that ID is rejected. This is submission idempotency, not semantic duplicate detection across separate citizen reports. Generated tracking UUIDs are returned only after a successful database query/commit. Database errors return HTTP 503 with `persisted: false`.

GET `/webhook/municipal-ticket-status?tracking_id=<uuid>` reads committed data. The portal exposes it through `/api/tickets/<uuid>`. The tracking reference is a local-demo bearer reference, not an authenticated municipality dashboard. A final database confirmation distinguishes COMPLETED from FAILED; REVIEW remains a quality/status flag.

## Checks

- `node n8n/completion-integration/tests/test_workflow.mjs`: labelled synthetic contract/branch checks; no AI calls.
- `.runtime/nvidia-intake-venv/Scripts/python.exe -B integration/persistence/test_database.py`: real isolated PostgreSQL transaction checks; no AI calls.
- Fresh media upload through http://127.0.0.1:8090/ is required to establish real three-agent end-to-end behavior.

## Verified 2026-10-18

Browser report `RPT-9feb4b84ef104ce78fa7545173628c6e` completed all three real agents and the three gates, then saved PostgreSQL ticket `be70587c-6307-4bc0-b9d6-72e52cd8d07f`. Vision returned ROAD_DAMAGE/MEDIUM with uncertainty; routing selected ROADS_DEPARTMENT. RAG used BGE-M3 retrieval and real qwen2.5:3b generation, returning no supported procedure. Gate 2 and Gate 3 stayed REVIEW, while the workflow completed automatically and persisted NEEDS_REVIEW plus its review record. Processing took about 158 seconds. No human action was needed after clicking Submit.

Evidence: `project-docs/integration/completion-live-RPT-9feb4b84ef104ce78fa7545173628c6e.json` and `completion-browser-ticket-20261018.png`. Independent SQL readback confirmed exactly one creation event and the matching review record. The browser tracking button successfully read the ticket after a database restart. The real outage test confirmed HTTP 503 and `persisted:false` when PostgreSQL was unavailable, followed by successful recovery. An invalid-media n8n test confirmed a persisted REJECT outcome and idempotent replay. These do not claim a live all-PASS case or fresh video/audio coverage.

Repeat evidence collection without another AI call using `verify_live.py <report_id>`. `check_outage.py` briefly stops and restarts only this database, requires service-interruption permission, and skips if an upload is active. Its invalid-input fixture never calls an agent.

The browser starts all automatic processing with one submission. `Start_MunicipaliteAuto.cmd` starts already installed services; it does not install infrastructure. No terminal command or individual node execution is needed by the citizen.

## n8n execution recording

The completion builder explicitly enables `saveDataSuccessExecution: all`, `saveDataErrorExecution: all`, `saveManualExecutions: true` and `saveExecutionProgress: true`. Use `Publish_Workflow.ps1` to back up and republish only this existing development workflow. It refuses to stop n8n when a portal upload is active. The demo photo and exact input text are in `demo/`.

These are the [n8n workflow settings for execution retention and progress](https://docs.n8n.io/workflows/settings/). New runs retain node inputs/outputs in the existing n8n volume; historical discarded details cannot be restored. Existing execution pruning is unchanged. Credentials remain credential references; citizen media is part of recorded execution data.

`verify_execution_recording.py <report_id>` matches the PostgreSQL ticket's recorded n8n execution ID to the actual n8n SQLite execution and node data, opening SQLite read-only. It verifies that Intake, Vision, RAG, the three gates and the database step all appear, and that the final saved node output confirms the same ticket. It needs no n8n browser login and triggers no AI calls. To inspect the run visually, sign in to the existing local n8n account and open the returned execution URL.
