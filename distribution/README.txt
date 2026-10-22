MUNICIPALITÉ AUTOMATISÉE - WINDOWS PACKAGE

1. Extract the ENTIRE ZIP into a short local folder, for example C:\Municipal.
   Do not run it inside the ZIP. Keep this folder in place after first setup.
2. Start Docker Desktop (Linux containers) and Ollama.
3. Double-click Start_MunicipaliteAuto.cmd. Leave its window open until setup finishes.
4. On http://127.0.0.1:8090/setup, enter YOUR NVIDIA API key once.
   The key is encrypted for your Windows account. No teammate key is included.
5. Open http://127.0.0.1:8090/, upload demo/road-damage.jpg and paste the text
   in demo/description.txt. Click Send report ONCE and wait.
   Intake -> Vision -> RAG -> policy gates -> PostgreSQL all run automatically.
   The final page displays the ticket and tracking ID. No curl or manual nodes.

PREREQUISITES
- Windows 10/11 x64, Docker Desktop, Ollama, internet for NVIDIA and the first
  Docker image downloads. Python and agent dependencies are included.
- Installed Ollama tags: qwen2.5vl:3b, qwen2.5:3b, bge-m3:latest.
  No generation or embedding weights are included or automatically downloaded.
- Ollama must run on 127.0.0.1:11434. If your model store is nonstandard, launch
  from a terminal with OLLAMA_MODELS pointing to that existing folder.
- Allow roughly 2 GB for extraction/runtime, plus Docker images and volumes.
  Local models need additional RAM/VRAM. Close other model-heavy applications.

FIRST LAUNCH
The launcher checks file hashes, creates local Python environments, creates new
bridge/database credentials, builds the two native BGE-M3/Qdrant indexes, starts
PostgreSQL and imports/publishes the n8n workflow with all three credentials.
First indexing/image downloads can take several minutes. Later launches reuse
the indexes, credentials and data. No global Python/PATH/firewall changes.
The native models/prompts and PASS/REVIEW/REJECT rules are preserved.

n8n VISUALIZATION
Open http://127.0.0.1:5679/ and create your local n8n owner account the first time
you visit. Upload automation does not require signing in to the editor.
Workflow: Municipalité Automatisée - Traitement automatique complet + PostgreSQL
http://127.0.0.1:5679/workflow/municipalCompletionDev
Select Executions and the upload execution containing Citizen Webhook. Short
ticket-status lookups also appear. Successful/failed runs and node outputs are
saved in your local n8n volume; n8n's ordinary pruning rules still apply.

WHAT THE RESULT MEANS
The supplied real photo/text previously completed all three agents and created
a PostgreSQL ticket on the source PC. Runs took about 3-9 minutes depending on
available memory. This is a useful demo input, not a guaranteed all-PASS case.
Uncertain Vision output or unsupported RAG evidence produces NEEDS_REVIEW with
the ticket still saved and displayed. No procedures/citations are fabricated.
Invalid input can end in REJECT; service failures are reported truthfully.
The staff dashboard remains deferred. PostgreSQL stores tickets, reviews and
status events. This package includes the citizen upload/result portal.

STORAGE AND TROUBLESHOOTING
Docker project: municipalite-auto. Containers: municipalite-auto-n8n and
municipalite-auto-postgres. Volumes: municipalite-auto_n8n_data and
municipalite-auto_ticket_data. Existing installations are not overwritten.
Logs: .runtime/portal/services and .runtime/knowledge-ollama.
Reserved local ports: 5679, 5434, 8090, 8010, 8012, 8013, 8020, 8021, 11435.
If a port is busy, close the earlier project before retrying. Do not delete
Docker volumes to solve a startup error: they contain your saved tickets.
If setup is interrupted, run Start_MunicipaliteAuto.cmd again. Credentials are reused.
Do not copy the folder AFTER use to another PC: it then contains credentials,
uploads and runtime records. Share the original clean ZIP instead.

REPEATABLE CHECKS (optional; no AI calls)
powershell -NoProfile -ExecutionPolicy Bypass -File distribution\Start_MunicipaliteAuto.ps1 -PrepareOnly
This verifies packaged files, native imports, tokenizer and workflow generation.
Offline checks do not prove fresh model inference on a different machine.

SOURCE / THIRD-PARTY NOTICES
The package includes the integration source, original RAG delivery, native Vision
source/prompts, Intake runtime source, dependency license metadata and manifest.
Historical private/runtime reports and source notebooks are excluded.
CPython license: vendor/python/LICENSE.txt; https://www.python.org/
Python dependencies: licenses in each vendor/*/site-packages/*.dist-info folder.
FFmpeg: vendor/media/FFmpeg-LICENSE and FFmpeg-README.txt; exact build 9.0.2:
https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2
Source/build information: https://www.gyan.dev/ffmpeg/builds/#sources
BGE-M3 tokenizer: https://huggingface.co/BAAI/bge-m3 (MIT).
YuNet: pinned OpenCV Zoo revision in intake-agent/assets.lock.json (Apache 2.0).
Docker images remain under their respective licenses and are pulled from their
publishers. This ZIP is a local university demonstration distribution.
