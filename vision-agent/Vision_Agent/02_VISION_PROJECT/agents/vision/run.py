"""Classify one supplied photo with Ollama and save the actual result."""

import argparse
import base64
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from time import perf_counter

import requests
from PIL import Image

from .schema import (
    CaptionClaim,
    CaptionComparison,
    VisionDecision,
    VisionDecisionWithoutText,
    VisionEvidence,
    VisionObservation,
    VisualCondition,
)

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "evaluation/vision/image_inventory.csv"
PROMPT_FOLDER = ROOT / "prompts/vision"
RESULTS_FOLDER = ROOT / "evaluation/vision/runs"
NO_DESCRIPTION = (
    "No citizen description was provided. Analyze only the attached photo. "
    "Set text_image_consistent to null because there is no text to compare."
)


def parse_arguments():
    """Read the image ID, model and optional citizen description from the command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", required=True, help="Photo ID from the inventory, e.g. IMG-01.")
    parser.add_argument("--model", default="qwen2.5vl:3b")
    parser.add_argument("--prompt-version", choices=["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11"], default="v1")
    parser.add_argument("--description", help="An actual report description, if available.")
    parser.add_argument("--severity-rubric", action="store_true",
                        help="Append the versioned prototype severity rubric (v1-v3 or v6-v11).")
    parser.add_argument("--timeout", type=int, help="Seconds to wait; defaults to 600 for v3/v7 and 240 otherwise.")
    parser.add_argument(
        "--context-size", type=int,
        help="Context tokens; defaults to 8192 for v3/v7 image examples and 4096 otherwise.",
    )
    parser.add_argument(
        "--structured", action=argparse.BooleanOptionalAction, default=True,
        help="Request the JSON schema. Use --no-structured for a prompt-only comparison.",
    )
    args = parser.parse_args()
    if args.timeout is None:
        args.timeout = 600 if args.prompt_version in ("v3", "v7") else 240
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero.")
    if args.context_size is not None and args.context_size <= 0:
        parser.error("--context-size must be greater than zero.")
    if args.description is not None:
        args.description = args.description.strip() or None
    return args


def load_photo(image_id):
    """Find a photo in the CSV and check its hash and image format before using it."""
    with INVENTORY.open(encoding="utf-8-sig", newline="") as file:
        for photo in csv.DictReader(file):
            if photo["image_id"] != image_id:
                continue

            image_path = (ROOT / photo["file"]).resolve()
            if not image_path.is_relative_to(ROOT):
                raise ValueError("The photo must be inside the project folder.")
            image_bytes = image_path.read_bytes()

            # The hash catches accidental edits or replacement of an evaluation photo.
            if hashlib.sha256(image_bytes).hexdigest() != photo["sha256"]:
                raise ValueError(f"{image_id} has changed since it was added to the inventory.")
            with Image.open(BytesIO(image_bytes)) as image:
                image.verify()
            return photo, image_bytes

    raise ValueError(f"Unknown image ID: {image_id}. See {INVENTORY.name}.")


def load_prompt(version, query_photo):
    """Load instructions and reject examples from the query's own scene.

    V3 reuses v2 instructions; v7 reuses v6 with contrasting captions on IMG-02.
    JSON specifications store actual image IDs and authored reference answers.
    V5 loads its observer separately. Metadata comments are not sent to Ollama.
    """
    # V4 returns to one image per call after v3 produced unsupported waste.
    if version in ("v1", "v2", "v4", "v6", "v8", "v9", "v10", "v11"):
        name = "v2" if version in ("v9", "v10", "v11") else version
        prompt = (PROMPT_FOLDER / f"{name}.txt").read_text(encoding="utf-8")
        return prompt, [], None
    if version == "v5":
        prompt = (PROMPT_FOLDER / "v5_classify.txt").read_text(encoding="utf-8")
        return prompt, [], None
    if version not in ("v3", "v7"):
        raise ValueError(f"Unknown prompt version: {version}")
    spec_text = (PROMPT_FOLDER / f"{version}.json").read_text(encoding="utf-8")
    spec = json.loads(spec_text)
    expected_system = "v2.txt" if version == "v3" else "v6.txt"
    if spec["version"] != version or spec["system_prompt"] != expected_system:
        raise ValueError(f"{version} must reuse {expected_system}.")
    prompt = (PROMPT_FOLDER / expected_system).read_text(encoding="utf-8")
    if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != spec["system_prompt_sha256"]:
        raise ValueError("The tested system prompt has changed.")
    demonstrations = []
    scenes = set()
    for example in spec["demonstrations"]:
        photo, image_bytes = load_photo(example["image_id"])
        if photo["scene_group"] == query_photo["scene_group"]:
            raise ValueError(f"{example['image_id']} is a demonstration from the query's scene.")
        if version == "v3" and photo["scene_group"] in scenes:
            raise ValueError("Demonstrations must come from different scenes.")
        if (photo["sha256"] != example["image_sha256"]
                or photo["scene_group"] != example["scene_group"]):
            raise ValueError(f"Demonstration provenance changed: {example['image_id']}")
        answer = VisionObservation.model_validate(example["answer"]).model_dump()
        if not example.get("description") and answer["text_image_consistent"] is not None:
            raise ValueError("Image-only demonstrations must have null text/image consistency.")
        scenes.add(photo["scene_group"])
        demonstration = {"image_bytes": image_bytes, "answer": answer}
        if example.get("description"):
            demonstration["description"] = example["description"]
        demonstrations.append(demonstration)
    if len(demonstrations) != 3:
        raise ValueError(f"{version} requires its three documented demonstrations.")
    metadata = {"spec": spec, "spec_sha256": hashlib.sha256(spec_text.encode("utf-8")).hexdigest()}
    return prompt, demonstrations, metadata


def build_messages(prompt, image_bytes, description, demonstrations):
    """Place each example image beside its answer, followed by the actual query."""
    messages = [{"role": "system", "content": prompt}]
    for example in demonstrations:
        example_text = ("Citizen description:\n" + example["description"]
                        if example.get("description") else NO_DESCRIPTION)
        messages.extend([
            {"role": "user", "content": example_text,
             "images": [base64.b64encode(example["image_bytes"]).decode("ascii")]},
            {"role": "assistant", "content": json.dumps(example["answer"], ensure_ascii=False)},
        ])
    query_text = "Citizen description:\n" + description if description else NO_DESCRIPTION
    messages.append({"role": "user", "content": query_text,
                     "images": [base64.b64encode(image_bytes).decode("ascii")]})
    return messages


def validate_comparison(observation, description):
    """Check missing-text rules; the model must still judge semantic agreement."""
    if description is None and observation.text_image_consistent is not None:
        raise ValueError("The model compared text and image, but no description was supplied.")
    if (description and observation.text_image_consistent is None
            and not (observation.uncertainty_reason or "").strip()):
        raise ValueError("An inconclusive comparison with supplied text needs an uncertainty reason.")


def run_model(messages, args, result, response_model=VisionObservation):
    """Call Ollama, record its raw response, and return a validated observation.

    The result dictionary also keeps model details and request settings. If the
    response fails validation, run_case() saves those details along with the error.
    """
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    info = requests.post(base_url + "/api/show", json={"model": args.model}, timeout=15)
    info.raise_for_status()
    model_info = info.json()
    if "vision" not in model_info.get("capabilities", []):
        raise ValueError(f"{args.model} does not support images.")
    result["model_details"] = model_info.get("details")

    # Save the installed model's digest so later experiments can identify it exactly.
    tags = requests.get(base_url + "/api/tags", timeout=15)
    tags.raise_for_status()
    for model in tags.json()["models"]:
        if model["name"] == args.model:
            result["model_digest"] = model["digest"]
            break

    # Ollama accepts image bytes as base64 in the user message.
    payload = {
        "model": args.model,
        "messages": messages,
        "stream": False,
        "options": result["options"],
        "keep_alive": "2m",
    }
    if "thinking" in model_info.get("capabilities", []):
        payload["think"] = False
    if args.structured:
        payload["format"] = response_model.model_json_schema()
        if issubclass(response_model, VisionDecision):
            # Request observations before the category. This changes generation
            # order, not the downstream field names or their factual reliability.
            properties = payload["format"]["properties"]
            order = ["description", "evidence", "uncertainty_reason", "category",
                     "severity", "text_image_consistent", "confidence"]
            payload["format"]["properties"] = {name: properties[name] for name in order}
            result["decision_policy"] = "observations_first_null_scores_missing_text_null"
        result["output_schema"] = payload["format"]
    result["think"] = payload.get("think")
    # Hash the entire request, including the example images. The record stores
    # readable text and image hashes rather than duplicating base64 data on disk.
    # Preserve schema field order because it can affect constrained generation.
    # Earlier records used sorted keys; the marker makes reconstruction explicit.
    request_text = json.dumps(payload, ensure_ascii=False)
    result["request_hash_serialization"] = "json_utf8_preserve_order"
    result["request_sha256"] = hashlib.sha256(request_text.encode("utf-8")).hexdigest()

    started = perf_counter()
    response = requests.post(base_url + "/api/chat", json=payload, timeout=args.timeout)
    result["inference_seconds"] = round(perf_counter() - started, 3)
    response.raise_for_status()
    answer = response.json()
    result["raw_response"] = answer

    # A stopped or empty response is a failed run, not a valid classification.
    if answer.get("done_reason") == "length":
        raise ValueError("Ollama reached the output token limit. The answer is incomplete.")
    content = answer.get("message", {}).get("content", "")
    if not content.strip():
        raise ValueError("Ollama returned no final answer.")
    observation = response_model.model_validate_json(content)
    if isinstance(observation, VisionObservation):
        validate_comparison(observation, args.description)
    return observation.model_dump()


def observe_photo(image_bytes, args, result):
    """Run v5's visual checklist separately and retain its full intermediate result."""
    prompt = (PROMPT_FOLDER / "v5_observe.txt").read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Describe the visible conditions in this photograph.",
         "images": [base64.b64encode(image_bytes).decode("ascii")]},
    ]
    stage = {
        "name": "observe", "prompt_text": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "user_message": messages[-1]["content"], "options": dict(result["options"]),
        "status": "failed",
    }
    # Attach the stage before the call, so even a failed observation is saved.
    result["stages"] = [stage]
    observation = run_model(messages, args, stage, VisionEvidence)
    stage["observation"] = observation
    stage["status"] = "completed"
    return observation


def run_case(args):
    """Save one real inference attempt and return its record and exact file path."""
    photo, image_bytes = load_photo(args.image_id)
    return analyze_image(args, photo, image_bytes)


def compare_caption(observation, args, result, image_bytes):
    """Keep the caption judgment separate from the saved visual answer.

    The enum-to-boolean mapping is the output contract. Python does not decide
    whether words match the image, and both model responses remain available.
    """
    result["visual_observation"] = dict(observation)
    result["stages"] = []
    if args.description is None:
        return observation
    prompt = (PROMPT_FOLDER / f"{args.prompt_version}_compare.txt").read_text(encoding="utf-8")
    content = json.dumps({"visual_observations": {key: observation[key] for key in ("description", "evidence")},
                          "citizen_description": args.description}, ensure_ascii=False)
    stage = {"name": "compare_caption", "prompt_text": prompt,
             "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
             "user_message": content, "options": dict(result["options"]), "status": "failed"}
    result["stages"].append(stage)
    user_message = {"role": "user", "content": content}
    if args.prompt_version == "v10":
        # V9's text-only reviewer mistook an omitted branch detail for a conflict.
        # V10 can verify the caption against the original pixels as well as notes.
        user_message["images"] = [base64.b64encode(image_bytes).decode("ascii")]
    decision = run_model([{"role": "system", "content": prompt}, user_message], args, stage, CaptionComparison)
    stage["observation"] = decision
    if stage["model_digest"] != result["model_digest"]:
        raise ValueError("The model changed between visual analysis and caption comparison.")
    stage["status"] = "completed"
    output = dict(observation)
    output["text_image_consistent"] = {"NO_CLAIM": None, "UNVERIFIABLE": None,
                                       "SUPPORTED": True, "CONTRADICTED": False}[decision["decision"]]
    if output["text_image_consistent"] is None:
        image_reason = observation["uncertainty_reason"]
        output["uncertainty_reason"] = (f"Image: {image_reason} Text: {decision['reason']}"
                                        if image_reason else decision["reason"])
    checked = VisionObservation.model_validate(output)
    validate_comparison(checked, args.description)
    return checked.model_dump()


def run_caption_stage(name, content, args, result, response_model, image_bytes=None):
    """Save one v11 stage before inference so failed stages remain inspectable."""
    prompt = (PROMPT_FOLDER / f"v11_{name}.txt").read_text(encoding="utf-8")
    stage = {"name": name, "prompt_text": prompt,
             "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
             "user_message": content, "options": dict(result["options"]), "status": "failed"}
    result["stages"].append(stage)
    query = {"role": "user", "content": content}
    if image_bytes is not None:
        query["images"] = [base64.b64encode(image_bytes).decode("ascii")]
    answer = run_model([{"role": "system", "content": prompt}, query], args, stage, response_model)
    stage["observation"] = answer
    if stage["model_digest"] != result["model_digest"]:
        raise ValueError("The model changed between stages.")
    stage["status"] = "completed"
    return answer


def verify_caption_claim(observation, args, result, image_bytes):
    """Extract the claim in text, check its positive condition visually, then compose."""
    result["visual_observation"] = dict(observation)
    result["stages"] = []
    if args.description is None:
        return observation
    claim = run_caption_stage("claim", json.dumps({"citizen_text": args.description}, ensure_ascii=False),
                              args, result, CaptionClaim)
    match, reason = None, claim["reason"]
    if claim["kind"] == "CLAIM":
        checked = run_caption_stage("verify", json.dumps({"condition": claim["condition"]}, ensure_ascii=False),
                                    args, result, VisualCondition, image_bytes)
        reason = checked["reason"]
        if checked["presence"] != "UNVERIFIABLE":
            match = (checked["presence"] == "PRESENT") != claim["negated"]
    output = dict(observation)
    output["text_image_consistent"] = match
    if match is None:
        image_reason = observation["uncertainty_reason"]
        output["uncertainty_reason"] = f"Image: {image_reason} Text: {reason}" if image_reason else reason
    validated = VisionObservation.model_validate(output)
    validate_comparison(validated, args.description)
    return validated.model_dump()


def analyze_image(args, photo, image_bytes):
    """Analyze validated image bytes from the inventory or the HTTP endpoint.

    The caller verifies the image. Reference labels are never passed to the
    model. The optional severity addendum leaves the original prompts unchanged.
    """
    prompt, demonstrations, metadata = load_prompt(args.prompt_version, photo)
    base_prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    addendum = None
    if getattr(args, "severity_rubric", False):
        if args.prompt_version not in ("v1", "v2", "v3", "v6", "v7", "v8", "v9", "v10", "v11"):
            raise ValueError("The severity rubric is for v1-v3 and v6-v11; v4/v5 request null scores.")
        text = (PROMPT_FOLDER / "severity_v1.txt").read_text(encoding="utf-8")
        addendum = {"version": "severity_v1", "text": text,
                    "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        prompt += "\n\n" + text
    minimum_context = metadata["spec"]["minimum_context"] if metadata else 4096
    context_size = args.context_size or minimum_context
    if metadata and context_size < minimum_context:
        raise ValueError("Few-shot prompts require at least 8192 context tokens for image demonstrations.")
    visual_description = None if args.prompt_version in ("v9", "v10", "v11") else args.description
    messages = build_messages(prompt, image_bytes, visual_description, demonstrations)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + "_" + args.image_id
    result = {
        "run_id": run_id,
        "image_id": args.image_id,
        "image_sha256": photo["sha256"],
        "scene_group": photo["scene_group"],
        "split": photo["split"],
        "model": args.model,
        "prompt_version": args.prompt_version,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "base_prompt_sha256": base_prompt_hash,
        "prompt_addendum": addendum,
        "prompt_text": prompt,
        "prompt_spec": metadata,
        "demonstration_count": len(demonstrations),
        "user_message": messages[-1]["content"],
        "description": args.description,
        "input_mode": "image_and_text" if args.description else "image_only",
        "options": {"temperature": 0, "seed": 42, "num_ctx": context_size, "num_predict": 512},
        "format_constraint": "json_schema" if args.structured else None,
        "status": "failed",
        "schema_valid": False,
    }
    if getattr(args, "report_id", None):
        result["report_id"] = args.report_id
    if photo.get("file"):
        result["image_file"] = photo["file"]
    started = perf_counter()
    try:
        response_model = VisionObservation
        if args.prompt_version == "v5":
            facts = observe_photo(image_bytes, args, result)
            # The second call receives the first call's observations, not another
            # photograph or a reference label. Errors in those facts can propagate.
            content = json.dumps({"visual_observations": facts,
                                  "citizen_description": args.description}, ensure_ascii=False)
            messages = [{"role": "system", "content": prompt},
                        {"role": "user", "content": content}]
            result["classification_message"] = content
            response_model = VisionDecisionWithoutText if args.description is None else VisionDecision
        model_args = args
        if args.prompt_version in ("v9", "v10", "v11"):
            model_args = argparse.Namespace(**{**vars(args), "description": None})
            result["decision_policy"] = "image_only_then_caption_enum"
        observation = run_model(messages, model_args, result, response_model)
        if args.prompt_version in ("v9", "v10"):
            observation = compare_caption(observation, args, result, image_bytes)
        elif args.prompt_version == "v11":
            result["decision_policy"] = "image_only_then_claim_extraction_and_positive_visual_check"
            observation = verify_caption_claim(observation, args, result, image_bytes)
        result["observation"] = observation
        result["schema_valid"] = True
        result["status"] = "completed"
    except (requests.RequestException, ValueError) as error:
        # Pydantic validation errors also inherit from ValueError.
        result["error_type"] = type(error).__name__
        result["error"] = str(error)
    result["elapsed_seconds"] = round(perf_counter() - started, 3)

    # Keep failures as well as successes for the exam's experiment log.
    RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_FOLDER / (run_id + ".json")
    result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, result_file


def main():
    """Read CLI options, analyze one photo, and print its result or error."""
    args = parse_arguments()
    try:
        result, result_file = run_case(args)
    except (OSError, ValueError) as error:
        print(f"Input error: {error}")
        return 2
    print(json.dumps(result.get("observation", {"error": result.get("error")}), indent=2))
    print(f"Status: {result['status']} | Time: {result['elapsed_seconds']} s")
    print(f"Saved: {result_file}")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
