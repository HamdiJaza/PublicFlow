"""Build a separate development export; never overwrite the original workflow."""

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "n8n/municipal-phase5/n8n/municipal-ticket-phase5.json"


def build():
    workflow = copy.deepcopy(json.loads(SOURCE.read_text(encoding="utf-8")))
    workflow.pop("id", None)
    workflow.pop("versionId", None)
    workflow["id"] = "municipalNativeIntakeDev"
    workflow["name"] = "Municipal - Native Intake - DEVELOPMENT ONLY"
    workflow["active"] = False
    workflow["pinData"] = {}
    workflow["settings"] = {"executionOrder": "v1", "executionTimeout": 660,
        "saveDataSuccessExecution": "none", "saveDataErrorExecution": "none",
        "saveManualExecutions": False, "timezone": "Africa/Tunis"}
    nodes = {n["name"]: n for n in workflow["nodes"]}
    active = {"Citizen Webhook", "Input Check", "Input PASS?", "HTTP Intake",
              "Attach Intake Response", "Gate 1 - Intake", "Intake PASS?",
              "Audit Summary", "Format API Response", "Respond to Citizen"}
    for n in workflow["nodes"]:
        n["disabled"] = n["name"] not in active
        n.pop("credentials", None)
    nodes["Citizen Webhook"]["parameters"]["path"] = "municipal-intake-integration"
    nodes["Citizen Webhook"]["webhookId"] = "municipal-native-intake-development"
    local_files = sorted((ROOT / "intake-agent/local_intake").glob("*.py"))
    source_hash = hashlib.sha256(b"".join(p.read_bytes() for p in local_files)).hexdigest()
    config = {"trusted_safe_root": (ROOT / ".runtime/intake/safe").as_posix(),
              "privacy_invariant": "checked_yunet_output_v1", "local_source_sha256": source_hash}
    for node, filename in {"Input Check":"input.js", "Attach Intake Response":"attach.js",
                           "Gate 1 - Intake":"gate1.js", "Format API Response":"response.js"}.items():
        code = (HERE / "nodes" / filename).read_text(encoding="utf-8")
        nodes[node]["parameters"] = {"mode":"runOnceForAllItems", "jsCode":code.replace("__INTEGRATION_CONFIG__", json.dumps(config))}
    http = nodes["HTTP Intake"]
    for key in ("maxTries", "waitBetweenTries"):
        http.pop(key, None)
    http["retryOnFail"] = False
    http["onError"] = "continueRegularOutput"
    http["parameters"] = {"method":"POST", "url":"http://host.docker.internal:8011/analyser",
        "sendBody":True, "contentType":"multipart-form-data",
        "bodyParameters":{"parameters":[
            {"parameterType":"formBinaryData","name":"image","inputDataFieldName":"image"},
            {"parameterType":"formData","name":"texte","value":"={{ $json.original.description }}"}]},
        "options":{"timeout":600000,"response":{"response":{"fullResponse":True,"neverError":True,"responseFormat":"json"}}}}
    audit = nodes["Audit Summary"]["parameters"]["jsCode"]
    audit = audit.replace("agent_versions:x.versions || {}", "components:x.components || {}")
    nodes["Audit Summary"]["parameters"]["jsCode"] = audit
    workflow["nodes"].append({"id":"intake-development-checkpoint","name":"Downstream unavailable",
        "type":"n8n-nodes-base.code","typeVersion":2,"position":[1400,0],
        "parameters":{"mode":"runOnceForAllItems","jsCode":(HERE/"nodes/downstream.js").read_text(encoding="utf-8")}})
    def edge(name):return {"node":name,"type":"main","index":0}
    workflow["connections"] = {
        "Citizen Webhook":{"main":[[edge("Input Check")]]},
        "Input Check":{"main":[[edge("Input PASS?")]]},
        "Input PASS?":{"main":[[edge("HTTP Intake")],[edge("Audit Summary")]]},
        "HTTP Intake":{"main":[[edge("Attach Intake Response")]]},
        "Attach Intake Response":{"main":[[edge("Gate 1 - Intake")]]},
        "Gate 1 - Intake":{"main":[[edge("Intake PASS?")]]},
        "Intake PASS?":{"main":[[edge("Downstream unavailable")],[edge("Audit Summary")]]},
        "Downstream unavailable":{"main":[[edge("Audit Summary")]]},
        "Audit Summary":{"main":[[edge("Format API Response")]]},
        "Format API Response":{"main":[[edge("Respond to Citizen")]]},
    }
    workflow["meta"] = {"integration_source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    return workflow


if __name__ == "__main__":
    destination = HERE / "municipal-native-intake-development.json"
    destination.write_text(json.dumps(build(), indent=2, ensure_ascii=False)+"\n",encoding="utf-8")
    print("Built separate development workflow:", destination.name)
