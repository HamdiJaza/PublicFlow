"""Build a brief RAG PDF with tables taken from the recorded evaluation files."""

import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

REPORT = Path(__file__).resolve().parent
ROOT = REPORT.parent


def read_json(path):
    """Read an existing evidence file, never manufacture missing results."""
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def escape(value):
    """Escape text inserted into a LaTeX table."""
    replacements = {"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#"}
    return "".join(replacements.get(c, c) for c in str(value))


def write_table(name, columns, headers, rows):
    """Use visible rules and fixed row order for comparable results."""
    lines = [r"{\small", r"\begin{tabularx}{\linewidth}{" + columns + r"}\hline",
             " & ".join(r"\textbf{" + h + "}" for h in headers) + r"\\\hline"]
    lines.extend(" & ".join(row) + r"\\\hline" for row in rows)
    lines.extend([r"\end{tabularx}}", ""])
    (REPORT / "generated" / name).write_text("\n".join(lines), encoding="utf-8")


def make_tables():
    """Generate the report's numeric content from saved scores and raw run counts."""
    (REPORT / "generated").mkdir(exist_ok=True)
    with (ROOT / "rag/sources.csv").open(encoding="utf-8-sig", newline="") as handle:
        active = [r for r in csv.DictReader(handle) if r["include_in_index"] == "true"]
    documents = [ROOT / "rag/corpus" / (r["doc_id"] + ".md") for r in active]
    folders = ["prompt_study", "prompt_revision", "prompt_roles", "prompt_examples"]
    calls = sum(len(list((ROOT / "evaluation" / folder / "runs").glob("*.json"))) for folder in folders)
    if calls != 25:
        raise ValueError("The report expects the 25 archived prompt runs; review new evidence before rebuilding.")
    values = {"activecount": len(active), "activebytes": f"{sum(p.stat().st_size for p in documents):,}",
              "activewords": sum(len(p.read_text(encoding="utf-8").split()) for p in documents), "promptcalls": calls}
    (REPORT / "generated/evidence_values.tex").write_text(
        "\n".join("\\newcommand{\\" + key + "}{" + str(value) + "}" for key, value in values.items()) + "\n",
        encoding="utf-8")

    replay = read_json("evaluation/retrieval/historical_replay.json")
    rows = []
    for strategy in ("structure", "fixed"):
        m = replay["metrics"][strategy]
        old = replay["comparison_cutoff_0.50"][strategy]
        n = m["positive_queries"]
        def ratio(value, total=n):
            return f"{round(value * total)}/{total}"
        rows.append([strategy.title(), ratio(m["raw"]["hit_at_1"]), ratio(m["raw"]["hit_at_k"]),
                     f"{m['raw']['mrr']:.3f}", ratio(m["retained"]["hit_at_k"]),
                     ratio(old["retained"]["hit_at_k"])])
    write_table("retrieval_metrics.tex", "|Y|c|c|c|c|c|",
                ["Strategy", "Raw Hit@1", "Raw Hit@3", "Raw MRR", "Hit@3, 0.40", "Hit@3, 0.50"], rows)

    descriptions = ["Pothole report (FR)", "National-road damage (FR)", "Streetlights out (AR)",
                    "Fallen electrical cable (FR)", "Burst water pipe (FR)", "Meter leak diagnosis (FR)",
                    "Sewer overflow (AR/Derja)", "Dumped construction waste (FR)",
                    "Bulky-waste collection (FR)", "Passport/birth record (FR)"]
    cases = read_json("evaluation/queries.json")["cases"]
    by_key = {(r["query_id"], r["strategy"]): r for r in replay["results"]}
    rows = []
    for number, (case, description) in enumerate(zip(cases, descriptions), 1):
        structure, fixed = (by_key[case["query_id"], s] for s in ("structure", "fixed"))
        def ranks(row, expected=case["expected_doc"]):
            if expected == "NO_ANSWER":
                return "Passes cutoff"
            kept = str(row["retained_rank"]) if row["retained_rank"] else "--"
            return f"{row['raw_rank']} $\\to$ {kept}"
        scores = f"{structure['candidates'][0]['score']:.4f}/{fixed['candidates'][0]['score']:.4f}"
        expected = case["expected_doc"].removeprefix("DOC-").replace("NO_ANSWER", "No answer")
        if case["expected_doc"] in {"DOC-WATER-03", "DOC-WASTE-01"}:
            expected += r"$^\dagger$"
        rows.append([str(number), escape(description), expected, ranks(structure), ranks(fixed), scores])
    write_table("retrieval_cases.tex", "|c|Y|L{23mm}|L{22mm}|L{20mm}|L{29mm}|",
                ["ID", "Query summary", "Expected", "Structure", "Fixed", "Top score S/F"], rows)
    with (REPORT / "generated/retrieval_cases.tex").open("a", encoding="utf-8") as handle:
        handle.write(r"\par{\footnotesize $\dagger$ Expected document excluded after source review; original references unchanged.}" + "\n")

    metadata = [
        ("v1", "Zero-shot role, context, language/refusal instructions.", "Plain-answer baseline; no saved run.", None, None),
        ("v2", "Zero-shot role; stronger context-only guardrails.", "Adds explicit refusal/null rules; no saved run.", None, None),
        ("v3", "Role instruction; few-shot; JSON instructions; guardrails.", "Unsupported demonstration details found by inspection; language contamination observed.", "prompt_study", "v3_structured"),
        ("v4", "Source-backed few-shot; role; JSON; guardrails.", "Replaces unsupported examples; contact refusal and English copying remain.", "prompt_study", "v4_grounded"),
        ("v5", "Zero-shot decision rules; JSON; contact/procedure distinction.", "Contact recovers; injected phone and deadline are copied.", "prompt_revision", "v5_decision"),
        ("v6", "System/user separation; zero-shot; JSON data; language rule.", "Quoted null and overrefusal; role separation alone fails.", "prompt_roles", "v6_roles"),
        ("v7", "System role; source-backed few-shot; JSON-null examples.", "Contact recovers; Arabic refusal and invented integer deadline persist.", "prompt_examples", "v7_examples"),
    ]
    rows = []
    for version, techniques, finding, folder, key in metadata:
        if key:
            m = read_json(f"evaluation/{folder}/metrics.json")["metrics"][key]
            score = f"{m['valid_json_and_schema']}/5; {m['all_constraints']}/5"
        else:
            score = "Not tested"
        rows.append([version, escape(techniques), escape(finding), score])
    write_table("prompt_versions.tex", "|L{14mm}|L{49mm}|Y|L{23mm}|",
                ["Version", "Techniques used", "Change and observed result", "Schema; checks"], rows)

    inputs = [ROOT / "rag/sources.csv", *documents, ROOT / "evaluation/retrieval/historical_replay.json",
              ROOT / "evaluation/queries.json", ROOT / "evaluation/prompt_cases.json"]
    for folder in folders:
        inputs.extend((ROOT / "evaluation" / folder / "runs").glob("*.json"))
        inputs.append(ROOT / "evaluation" / folder / "metrics.json")
    snapshot = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)}
    (REPORT / "evidence_inputs.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def compile_report():
    """Compile twice, reject overflow and enforce the brief report's four-page limit."""
    build = REPORT / "build"
    build.mkdir(exist_ok=True)
    command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-output-directory=build", "rag_report.tex"]
    for _ in range(2):
        result = subprocess.run(command, cwd=REPORT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        output = result.stdout + result.stderr
        (build / "console.log").write_text(output, encoding="utf-8")
        finished = re.search(r"Output written on .*?\((\d+)\s+pages?,", output, re.DOTALL)
        if not finished:
            raise RuntimeError("LaTeX failed. Read report/build/console.log.")
        logging_only = "log4cxx" in output and "Access is denied" in output
        if result.returncode and not logging_only:
            raise RuntimeError("LaTeX returned an error. Read report/build/console.log.")
    if int(finished.group(1)) > 4:
        raise ValueError(f"The report has {finished.group(1)} pages; shorten it to four.")
    if "Overfull \\hbox" in output or "Overfull \\vbox" in output:
        raise ValueError("The PDF has layout overflow; inspect the log before delivering it.")
    target = REPORT / "rag_report.pdf"
    shutil.copyfile(build / target.name, target)
    print(f"Created {target}: {finished.group(1)} pages.")


if __name__ == "__main__":
    make_tables()
    compile_report()
