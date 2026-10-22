"""Create the portable handoff and verify the archived file hashes."""

import hashlib
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from api.knowledge_agent import app

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "Knowledge_Agent"


def check_workflow():
    """Check the export's structure and settings without claiming n8n execution."""
    workflow = json.loads((ROOT / "handoff/03_IMPORT_Knowledge_Webhook.json").read_text())
    nodes = {node["name"]: node for node in workflow["nodes"]}
    hook = nodes["Receive knowledge question"]
    call = nodes["Call Knowledge API"]
    reply = nodes["Return Knowledge response"]
    checks = [
        len(nodes) == 3,
        hook["parameters"]["httpMethod"] == "POST",
        hook["parameters"]["responseMode"] == "responseNode",
        call["parameters"]["url"] == "http://host.docker.internal:8020/knowledge",
        call["parameters"]["method"] == "POST",
        call["parameters"]["specifyBody"] == "json",
        call["parameters"]["options"]["timeout"] == 420000,
        call["parameters"]["options"]["response"]["response"]["fullResponse"],
        call["parameters"]["options"]["response"]["response"]["neverError"],
        call["onError"] == "continueRegularOutput",
        reply["parameters"]["respondWith"] == "json",
        "502" in reply["parameters"]["options"]["responseCode"],
        "$json.body" in reply["parameters"]["responseBody"],
        "'v4_grounded'" in call["parameters"]["jsonBody"],
        "JSON.stringify" in call["parameters"]["jsonBody"],
        workflow["connections"][hook["name"]]["main"][0][0]["node"] == call["name"],
        workflow["connections"][call["name"]]["main"][0][0]["node"] == reply["name"],
        not workflow["pinData"],
        not any("credentials" in node for node in workflow["nodes"]),
    ]
    if not all(checks):
        raise ValueError("A workflow structure or parameter check failed.")
    status_path = ROOT / "handoff/VALIDATION_STATUS.json"
    status = json.loads(status_path.read_text())
    status["workflow_static_checks"] = {
        "passed": len(checks),
        "scope": "JSON structure, node settings, expression text and connections inspected. Expressions and the n8n engine were not executed.",
    }
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"Passed {len(checks)} static workflow checks; n8n engine not executed.")


def package_files():
    """Keep code and development evidence; omit environments, secrets and machine files."""
    excluded = {".venv", "__pycache__", ".ruff_cache", ".pytest_cache", "data",
                "build", "api_runs", "http_runs", "integration_runs"}
    for directory, folders, names in os.walk(ROOT):
        folders[:] = [name for name in folders if name not in excluded and not name.startswith("tmp")]
        for name in sorted(names):
            path = Path(directory) / name
            if name in {".env", "PACKAGE_CONTENTS.json"} or name.endswith((".pyc", ".zip")):
                continue
            if ROOT not in path.resolve().parents:
                raise ValueError("Refusing to include a file outside the project: " + str(path))
            yield path


def main():
    """Use a new delivery filename so the earlier corrected-project ZIP is preserved."""
    check_workflow()
    (ROOT / "handoff/04_OPENAPI.json").write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    files = sorted(package_files())
    required = {"00_START_HERE.md", "handoff/01_Setup_Knowledge.ps1", "handoff/02_Start_Knowledge.ps1",
                "handoff/03_IMPORT_Knowledge_Webhook.json", "handoff/VALIDATION_STATUS.json",
                "report/rag_report.pdf", "prompts/README.md", "rag/sources.csv", "requirements.txt"}
    names = {path.relative_to(ROOT).as_posix() for path in files}
    if not required.issubset(names):
        raise ValueError("Missing handoff files: " + str(sorted(required - names)))
    inventory = {"created_at": datetime.now(timezone.utc).isoformat(), "prefix": PREFIX,
                 "note": "No prebuilt index or model weights. Run setup on the target PC. Inventory excludes itself.",
                 "files": [{"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]}
    manifest_path = ROOT / "PACKAGE_CONTENTS.json"
    manifest_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    output = ROOT.parent / "delivery/Knowledge_Agent_2026-10-18.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [*files, manifest_path]:
            archive.write(path, PREFIX + "/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("A ZIP entry failed its CRC check.")
        for entry in inventory["files"]:
            data = archive.read(PREFIX + "/" + entry["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Archived bytes do not match: " + entry["path"])
        print(f"Verified {len(archive.namelist())} files; {output.stat().st_size:,} bytes.")
    checksum = output.with_suffix(".zip.sha256")
    checksum.write_text(hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n", encoding="ascii")
    print(output)


if __name__ == "__main__":
    main()
