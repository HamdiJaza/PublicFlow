# Municipalité Automatisée — Codex Instructions

## 1. Project Context
This repository contains our Advanced Deep Learning university project: Municipalité Automatisée.

We are a team of five students building an AI-assisted municipal incident reporting and ticket management platform.

Citizens should be able to report urban problems such as potholes, damaged roads, broken streetlights, waste accumulation, damaged public infrastructure and visible water leaks.

The platform receives multimedia reports, analyzes them with specialized AI agents, verifies the results, assigns the appropriate municipal department, retrieves relevant municipal procedures and creates a trackable incident ticket.

This is an academic project demonstrating multimodal AI, prompt engineering, RAG, multi-agent orchestration, automation, deterministic validation and human review.

Read the project documentation in project-docs/ to understand the original design and exam requirements.

## 2. Main Technologies and Architecture
- n8n is the central workflow orchestrator.
- Intake Agent processes and normalizes multimodal reports.
- Vision Agent analyzes visual evidence.
- Knowledge Agent uses Retrieval-Augmented Generation (RAG).
- Policy Gates validate AI outputs and make PASS, REVIEW or REJECT decisions.
- Deterministic routing assigns departments and priorities.
- PostgreSQL is the intended ticket and status database.
- Qdrant is the originally proposed vector database for municipal knowledge.
- The web interface provides citizen reporting and municipal ticket management.

These are intended architecture components; verify the actual implementations before assuming any technology is already installed or working.

## 3. Intended End-to-End Workflow
1. Citizen submits a report through the web interface.
2. Report includes visual evidence and textual or audio context, or a video.
3. n8n receives the submission.
4. Validate required fields and supported media.
5. Intake Agent normalizes input, detects language, performs necessary transcription and/or frame extraction, and prepares structured report data.
6. Apply privacy and safety processing, including personal-data protection and face anonymization where needed.
7. Policy Gate 1 validates intake results.
8. Vision Agent analyzes the visual evidence and determines the incident category, visible severity, confidence and supporting evidence.
9. Policy Gate 2 validates the visual classification.
10. Deterministic Router chooses the municipal department and priority based on explicit rules.
11. Knowledge Agent retrieves relevant municipal procedures using RAG and supplies source evidence.
12. Policy Gate 3 checks source relevance and grounding.
13. Create a structured incident ticket and persist it in the database.
14. Return a tracking reference to the citizen.
15. Municipality dashboard enables human review, assignment and status updates.

Uncertain or invalid cases must follow explicit REVIEW or REJECT paths rather than silently proceeding.

## 4. Core Design Principles
- Keep n8n as the orchestration backbone.
- Preserve the sequential three-agent architecture.
- Use AI for semantic interpretation, not fixed business rules.
- Keep routing, policy decisions and ticket formatting deterministic.
- Validate structured outputs between stages.
- Preserve privacy and avoid exposing sensitive information.
- Do not invent municipal procedures, classifications or locations.
- RAG responses must be grounded in retrieved sources.
- Keep human review operational, not merely conceptual.
- Record useful execution traces, agent versions and errors.
- Prefer simple, testable integration over unnecessary complexity.

## 5. Current Development State
The team developed components independently.

The n8n orchestration workflow has previously been tested using mocked agent responses. Earlier results were explicitly marked as demo mode and did not prove end-to-end real AI execution.

Other members are providing the Intake, Vision and Knowledge Agent implementations. A separate member developed the interface.

Do not assume that the provided services already communicate successfully or implement every requirement.

Inspect the actual files to determine what is implemented, missing, simulated, broken or incompatible.

## 6. Integration Priority
Phase 0: Inspect the entire project and establish compatibility.
Phase 1: Connect the real Intake Agent to n8n.
Phase 2: Connect the real Vision Agent.
Phase 3: Connect the real Knowledge/RAG Agent.
Phase 4: Implement and verify persistent tickets and review.
Phase 5: Integrate the web interface.
Phase 6: Test the complete end-to-end system.

Existing working functionality should be preserved.

## 7. Repository Rules
- Before making changes, read project documentation and inspect the repository.
- Do not modify files during the initial audit.
- Do not invent endpoints, schemas or credentials.
- Clearly distinguish intended behavior from verified implementation.
- Preserve original code and workflow backups.
- Propose changes before performing large refactors.
- Make changes incrementally and explain them.
- Add tests for each integration.
- Avoid exposing or committing secrets and personal data.
- Do not describe mocked results as real AI inference.
- Prioritize reproducibility and a reliable university project demonstration.

## 8. First Assignment
Study project-docs/, inspect all components and the n8n JSON, compare their contracts and produce a detailed architecture and integration audit.

Wait for approval before changing anything.