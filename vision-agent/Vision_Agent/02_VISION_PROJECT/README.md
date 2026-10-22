# Municipal ticket project

The Vision component analyzes municipal incident photographs with local Ollama models. It provides a command-line runner and the required multipart POST /vision endpoint.

Start with the [Vision run guide](docs/vision_delivery.md) for setup, requests, experiments and evaluation limits.

## Run Vision

Use Python 3.11 or newer and a running Ollama instance with qwen2.5vl:3b installed.

~~~powershell
python -m pip install -r requirements-vision.txt
python -m uvicorn agents.vision.api:app --host 127.0.0.1 --port 8010
~~~

The API documentation is at http://127.0.0.1:8010/docs. For a single inventoried photo:

~~~powershell
python -B -m agents.vision.run --image-id IMG-01 --prompt-version v11 --severity-rubric --context-size 8192 --timeout 600
~~~

## Deliverables

| File | Purpose |
| --- | --- |
| [Engineering report](report/vision_report.pdf) | Design decisions, model comparison and measured prompt results. |
| [Prompt library PDF](report/vision_prompt_library.pdf) | Exact prompts, techniques, comments, failures and corrections. |
| [Prompt library index](prompts/README.md) | Version entries and the shared documentation format. |
| [Results CSV](evaluation/vision_results.csv) | Actual saved attempts, with each controlled study identified. |
| [Final study](evaluation/vision/final_study/protocol.md) | Frozen protocol, reference labels, controlled inputs and scoring. |
| [Design justifications](docs/research/vision_prompts.md) | Choices, alternatives and limits. |
| [Evaluation history](docs/research/vision_prompt_evaluation.md) | Before/after results and remaining failures. |
| [Text comparison correction](prompts/vision/v11.md) | Working caption chain, failed revisions and six-case regression results. |

The original photographs, tested prompt versions and raw run records are submission evidence. All images are development data; visual reference labels have no independent validation. Failed attempts remain part of the prompt-engineering study.

## Checks and report sources

~~~powershell
python -B -m unittest discover -s tests -p "test_vision*.py" -v
python -B scripts/verify_vision_study.py
~~~

The verification command reconstructs the original study and all correction-stage requests without model calls. See the run guide for the separate live HTTP check.

LaTeX sources and shared style files are in report/. To regenerate result tables and compile the reports with an installed pdfLaTeX:

~~~powershell
python -B scripts/export_vision_results.py
python -B report/build.py
~~~

The build command checks page limits and writes final PDFs to report/. Temporary output goes to report/build/.


