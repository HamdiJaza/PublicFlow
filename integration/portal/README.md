# Browser upload → development n8n

> **Package note (2026-10-22):** this runtime package does not include the development test suites (`test_*.py`, `tests/*.mjs`), the development compose files (`compose.dev.yaml`) or the `project-docs/integration/*.json` evidence reports mentioned below. They exist only in the source workspace, so commands referring to them cannot be run from this package. The runtime itself is complete.

Double-click `Start_MunicipaliteAuto.cmd` in the project root, then open
<http://127.0.0.1:8090/>. The launcher starts missing **existing** local services
and the installed `municipal-n8n-dev` and `municipal-ticket-postgres-dev` containers. It does not pull images, import
workflows, change production, or call models during startup.

If Intake is unavailable, visit <http://127.0.0.1:8090/setup> and save the NVIDIA
key in the password field. This uses the existing Windows DPAPI credential
helper, preserves the previous encrypted file, starts Intake, and never places
the key in command arguments or response JSON. This setup is required once per
Windows account. Do not paste credentials into chat or commit them.

## Citizen submission

1. Select a photo with a description (at least five characters), a photo with
   an audio message, or a video by itself. Description is optional for the latter
   two combinations. An address is optional and is never inferred.
2. Click **Send complaint** once. The portal is in English and shows only the citizen side; the operator setup page stays at /setup (linked from the footer).
3. n8n automatically runs Intake → Gate 1 → Vision → Gate 2 → routing → RAG →
   Gate 3, then PostgreSQL. Valid Vision uncertainty continues into RAG while
   retaining REVIEW. Unusable upstream results are saved without fabricating
   downstream inputs. No node requires manual execution.
4. The page displays the actual decision, component execution states, reasons,
   and final trace returned by n8n. While waiting, it shows elapsed time only;
   it does not invent live stage progress. Refreshing resumes result polling.

Images: JPG/PNG/WEBP, 10 MiB. Audio: supported native formats, 30 MiB and 120 s.
Video: supported native formats, 50 MiB and 60 s. Intake remains responsible for
decoding media, duration/dimension checks, privacy preparation and provider work.

## Integration boundary and honest limitations

The portal sends native citizen multipart fields to the **published** webhook
`http://127.0.0.1:5679/webhook/municipal-ticket-development`. It never calls AI agents
directly or substitutes its own decisions. The prior strict workflow and member
implementations are preserved; the new workflow ID is `municipalCompletionDev`. The original Intake `citizen.html` is preserved
untouched; the portal now has its own English citizen-only interface (`static/citizen.css`,
`static/index.html`, `static/app.js`) with a "New complaint" tab and a "Track a complaint" tab that reads
`/api/tickets/{tracking_id}`. Technical execution details (component states, trace, receipt download)
are collapsed under "Processing details" rather than removed.

The native Vision launcher accepts an optional Ollama endpoint; the browser
launcher keeps Vision on its original server on port 11434. RAG separately uses
11435 with flash attention disabled for the BGE-M3 workaround. Applying that
RAG-specific configuration to Vision caused a 4.9 GiB CPU computation buffer and
memory pressure on this workstation. The Vision model and prompts are unchanged.

**Ticket persistence uses PostgreSQL.** A `RPT-...` reference identifies a local
execution receipt; the separate tracking UUID identifies a committed ticket.
`persisted:true` is returned only after the database confirms its write. REVIEW
creates a NEEDS_REVIEW ticket and a persistent review record. The UI distinguishes
processing completion from policy approval. Database failure returns HTTP 503
with `persisted:false`, and the UI does not claim a ticket was saved.

One submission runs at a time. Repeating the same browser submission UUID
returns its existing receipt without another n8n invocation. Requests are never
automatically retried on timeouts. If the portal stops mid-run, inspect n8n
before resubmitting; n8n may have continued running. This is not global ticket
deduplication and does not cover deliberate fresh UUIDs or multiple portal
processes. Run the supplied single-worker launcher only.

The UI is bound to `127.0.0.1:8090`, with same-origin POST checks and a per-process
request token. It is a local demo, not an authenticated public municipal portal.
Execution receipts live in ignored `.runtime/portal/jobs`. Portal upload copies
are removed after dispatch completes; Intake and n8n retain their own existing
development evidence. Receipts are not a municipal review queue.

## Verification

`integration/portal/test_portal.py` has 16 offline integration tests covering
multipart mapping, allowed combinations, input limits, duplicate prevention,
concurrency, outages/invalid replies, restart behavior and secret handling.
Their n8n and credential helper responses are **labelled test doubles**. The
Windows process regression also starts a synthetic background helper to ensure
credential setup returns promptly when the service keeps running. It uses no
real key or provider. Helper stdout/stderr are discarded to avoid inherited
capture pipes keeping the setup request open.

Run with the already installed environment:

```powershell
.\.runtime\nvidia-intake-venv\Scripts\python.exe -B -m unittest discover -s integration\portal -p test_portal.py -v
```

Live browser results and exact scope are recorded separately in
`project-docs/integration/portal-browser-validation-20261018.json` (initial
Intake-outage case) and
`project-docs/integration/portal-live-configuration-20261018.json` (fresh real
Intake and Vision after local credential setup).

The corrected live browser run took about 134 seconds. Gate 1 passed; real
Vision returned ROAD_DAMAGE/MEDIUM, consistency true and an uncertainty reason
because the full extent of damage was not visible. Gate 2 correctly returned
REVIEW, so RAG was not invoked on that earlier strict-workflow path. This remains
historical evidence, not a three-agent PASS or persisted ticket. The new completion
workflow and persistence verification are recorded separately. The earlier attempt using the
RAG-specific runtime for Vision was interrupted due memory pressure and is
preserved separately in the same report.
