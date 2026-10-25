# Municipalité Automatisée

**An AI-assisted platform that turns a citizen's photo of a city problem into a tracked municipal ticket.**

This is a university project (Advanced Deep Learning) built by a team of five students. It demonstrates multimodal AI, prompt engineering, RAG (Retrieval-Augmented Generation), multi-agent orchestration, automation, deterministic validation and human review.

> **Status:** a local demonstration. It has run end to end with real AI models and saved a real database ticket. It is not a production system. See [Current status and limitations](#current-status-and-limitations).

---

## Table of contents

1. [The idea in one minute](#the-idea-in-one-minute)
2. [How a report flows through the system](#how-a-report-flows-through-the-system)
3. [The building blocks](#the-building-blocks)
4. [What the three decisions mean](#what-the-three-decisions-mean)
5. [Repository map](#repository-map)
6. [Run the demo](#run-the-demo)
7. [Ports and services](#ports-and-services)
8. [Design principles](#design-principles)
9. [Current status and limitations](#current-status-and-limitations)
10. [Glossary](#glossary)
11. [Where to read next](#where-to-read-next)

---

## The idea in one minute

Imagine you see a pothole. Today you would have to find the right office, describe the problem and hope someone reads it.

With this platform you:

1. Open a web page.
2. Upload a **photo** (or a video, or a photo plus a voice message) and describe the problem.
3. Click **Send complaint**.
4. Receive a **tracking ID** and see the result.

Behind the scenes, three specialised AI agents read your report. Strict, non-AI rules then check their work. The system picks the right municipal department, looks up the relevant procedure and saves a ticket.

When the AI is unsure, the system does **not** guess. It marks the ticket for **human review**.

**Problems it handles:** potholes and road damage, broken streetlights, waste accumulation, water leaks, and damaged public infrastructure.

---

## How a report flows through the system

```
 Citizen
    |  photo / audio / video + text
    v
 Web portal (port 8090)
    |
    v
 n8n workflow  <-- the "conductor" that runs every step below
    |
    |-- 1. Intake Agent     clean and normalise the input, protect privacy
    |-- 2. Policy Gate 1    is the intake result usable?
    |-- 3. Vision Agent     what is in the photo? how severe?
    |-- 4. Policy Gate 2    is the classification trustworthy?
    |-- 5. Router           pick department and priority (fixed rules)
    |-- 6. Knowledge Agent  find the municipal procedure (RAG)
    |-- 7. Policy Gate 3    is the answer backed by real sources?
    |
    v
 PostgreSQL ticket  ->  tracking ID returned to the citizen
```

**Key rule:** AI is used to *understand* things (what is in the image, what the text means). **Fixed, testable rules** make the decisions (which department, PASS or REVIEW or REJECT, how the ticket is formatted).

---

## The building blocks

### 1. Web portal: `integration/portal/`
The citizen-facing page, in English. It has two tabs: **New complaint** and **Track a complaint**. It sends uploads to n8n and shows the result. It never calls the AI agents directly.

### 2. n8n workflow: `n8n/`
n8n is the orchestration tool that connects everything. The workflow JSON files are *generated* by `build_workflow.py` scripts, with the logic for each step kept in small JavaScript files under `nodes/`. The current full workflow is called `municipalCompletionDev`.

### 3. Intake Agent: `intake-agent/`
Prepares the raw report. It detects the language, transcribes audio, extracts video frames, blurs faces for privacy and cleans the text into French. It uses a cloud model from NVIDIA, so **you need your own NVIDIA API key**.

### 4. Vision Agent: `vision-agent/`
Looks at the photo and returns:
- the **category** (road damage, street lighting, waste, water leak, and so on),
- the **severity**,
- a **confidence** level and the visible evidence.

It runs locally through Ollama with the `qwen2.5vl:3b` model. The folder also contains a study of 11 prompt versions.

### 5. Knowledge Agent (RAG): `rag-agent/`
Finds the right municipal procedure for the problem. It searches a small library of source documents (the **corpus**), then asks a local model (`qwen2.5:3b`) to answer **using only what it found**. If nothing supports an answer, it says so. It does not invent procedures. The demo covers the **Commune de Tunis**.

### 6. Policy gates (inside n8n)
Three checkpoints written as plain code, with no AI involved. They decide PASS, REVIEW or REJECT at each stage.

### 7. Ticket database: `integration/persistence/`
PostgreSQL stores tickets, review records and a full history of status changes. Saving is **atomic** (all or nothing) and **idempotent** (sending the same report twice does not create two tickets).

---

## What the three decisions mean

| Decision | Meaning | What happens |
|---|---|---|
| **PASS** | All checks are satisfied. | Ticket is created as `OPEN`. |
| **REVIEW** | The AI is uncertain, or evidence is weak or missing. | Ticket is saved as `NEEDS_REVIEW` with a review record for a human. |
| **REJECT** | The input is invalid or unsupported. | Ticket is saved as `REJECTED`. |

Ticket statuses: `OPEN`, `NEEDS_REVIEW`, `IN_PROGRESS`, `RESOLVED`, `REJECTED`.

The system **never silently continues** when something is uncertain.

---

## Repository map

```
MunicipaliteAuto/
├── README.md                  <- you are here
├── AGENTS.md                  project context and rules for AI coding assistants
├── READ_ME_FIRST.txt          step-by-step guide for running the packaged demo
├── Start_MunicipaliteAuto.cmd double-click launcher (Windows)
├── PACKAGE_MANIFEST.json      file hashes checked at launch (see warning below)
│
├── demo/                      sample photo + description to try the system
├── distribution/              launcher scripts, Docker compose, packaging tools
│
├── intake-agent/              Intake Agent (media handling, privacy, text cleaning)
├── vision-agent/              Vision Agent (image classification, prompt study)
├── rag-agent/                 Knowledge Agent (corpus, retrieval, evaluation, report)
│
├── n8n/                       workflow builders and generated workflow JSON
│   ├── intake-integration/
│   ├── vision-integration/
│   ├── knowledge-integration/
│   └── completion-integration/   <- the full, final workflow
│
├── integration/               glue code that connects each agent to n8n
│   ├── portal/                citizen web interface
│   ├── intake-local/          NVIDIA key setup and benchmarks
│   ├── vision/                media bridge for video and audio
│   ├── knowledge/             Knowledge API launcher and evidence bridge
│   └── persistence/           PostgreSQL schema and setup
│
└── project-docs/              integration evidence reports
```

> **Warning:** the launcher checks a SHA-256 hash of every file listed in `PACKAGE_MANIFEST.json`. If you edit a listed file (even `.gitignore`) without regenerating the manifest, the launcher refuses to start. New files that are not in the manifest are fine.

---

## Run the demo

### Requirements
- Windows 10 or 11 (64-bit)
- **Docker Desktop** (Linux containers mode)
- **Ollama**, with these models installed: `qwen2.5vl:3b`, `qwen2.5:3b`, `bge-m3:latest`
- An **NVIDIA API key** (free), for the Intake Agent
- Internet access for the first run
- Roughly 2 GB of disk space, plus Docker images and enough RAM for the local models

### Steps
1. Extract the whole project into a **short folder path** such as `C:\Municipal`.
2. Start **Docker Desktop** and **Ollama**.
3. Double-click **`Start_MunicipaliteAuto.cmd`** and leave the window open. The first launch builds the search indexes and imports the workflow, which can take several minutes.
4. Open <http://127.0.0.1:8090/setup> and enter your NVIDIA key once. It is encrypted for your Windows account and never stored in plain text.
5. Open <http://127.0.0.1:8090/>, upload `demo/road-damage.jpg`, paste the text from `demo/description.txt` and click **Send complaint once**.
6. Wait about **3 to 9 minutes**. The page then shows the ticket, the decision and the tracking ID.

To watch the workflow run, open n8n at <http://127.0.0.1:5679/> and go to **Executions**.

### Troubleshooting
- **Port already in use:** close the earlier run and retry.
- **Setup interrupted:** run `Start_MunicipaliteAuto.cmd` again. Credentials are reused.
- **Do not delete Docker volumes to fix a startup error.** They hold your saved tickets.
- Logs are in `.runtime/portal/services` and `.runtime/knowledge-ollama`.

---

## Ports and services

| Port | Service |
|---|---|
| 8090 | Citizen web portal |
| 5679 | n8n workflow editor and webhooks |
| 5434 | PostgreSQL ticket database |
| 8010 | Vision Agent API |
| 8012, 8013 | Intake and media services |
| 8020 | Knowledge Agent API |
| 8021 | Evidence verification bridge |
| 11434 / 11435 | Ollama (Vision / RAG) |

Everything is bound to `127.0.0.1` (your own computer only).

---

## Design principles

- **n8n stays the backbone.** Each agent runs one after another.
- **AI interprets; rules decide.** Routing, policy and ticket formatting are deterministic.
- **Validate between every stage.** Outputs are checked before the next step uses them.
- **Never invent anything.** No made-up procedures, classifications or locations. RAG answers must come from retrieved sources.
- **Privacy first.** Faces are anonymised and sensitive data is not exposed.
- **Uncertain means REVIEW.** Human review is a real, stored record, not just an idea.
- **Keep traces.** Executions, agent versions and errors are recorded.
- **Be honest about results.** Mocked or simulated runs are never presented as real AI inference.

---

## Current status and limitations

**Working (verified with real runs):**
- Upload through the portal, then Intake, Vision, Knowledge, all three gates, and a saved PostgreSQL ticket.
- Tracking a ticket by ID, including after a database restart.
- A clean 503 error, with no false "saved" message, when the database is down.
- Invalid input is rejected and saved as `REJECTED`, and resubmitting does not create duplicates.

**Known limitations:**
- **No staff dashboard yet.** Review records are stored in the database, but there is no screen for staff to review, assign or update tickets. This is the biggest missing piece.
- **No all-PASS demo case recorded.** The sample report ended as `NEEDS_REVIEW` because Vision was uncertain and the RAG corpus had no supported procedure.
- **RAG is still modest.** In development tests the correct source appeared in the top 3 results for 5 of 9 questions (structure chunking) and 6 of 9 (fixed chunking). The corpus is small (9 enabled documents).
- **Slow.** A run takes minutes on a laptop because the models run locally.
- **Local demo only.** There is no login, and the tracking ID acts like a password. Do not expose it to the internet.
- **One report at a time.**
- **Needs a cloud key.** Intake uses NVIDIA's hosted model, so it is not fully offline.
- **Some test suites and the original design documents are not in this repository.** Some READMEs mention them.

---

## Glossary

| Term | Plain meaning |
|---|---|
| **Agent** | A program that uses an AI model to do one specialised job. |
| **n8n** | A visual workflow tool that runs the steps in order. |
| **Multimodal** | Handling more than one kind of input: images, audio, video and text. |
| **RAG** | Retrieval-Augmented Generation. The AI first looks up documents, then answers using only them. |
| **Corpus** | The collection of source documents the Knowledge Agent searches. |
| **Embedding** | A numeric fingerprint of text that lets the computer find similar passages. |
| **Qdrant** | The vector database that stores those fingerprints. |
| **Ollama** | A tool for running AI models on your own computer. |
| **Policy gate** | A fixed-rule checkpoint that outputs PASS, REVIEW or REJECT. |
| **Idempotent** | Doing the same action twice has the same result as doing it once. |
| **Webhook** | A web address that receives data and starts a workflow. |

---

## Where to read next

| If you want to understand... | Read |
|---|---|
| How to run the packaged demo | `READ_ME_FIRST.txt` |
| The citizen portal | `integration/portal/README.md` |
| Database, tickets and review records | `integration/persistence/README.md` |
| The Knowledge Agent integration | `integration/knowledge/README.md` |
| The Vision Agent | `vision-agent/Vision_Agent/02_VISION_PROJECT/README.md` |
| The Intake Agent (NVIDIA) | `integration/intake-local/README-nvidia.md` |
| Project rules and context | `AGENTS.md` |
