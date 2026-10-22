"""Test input validation and scoring with real files and recorded model outputs."""

import argparse
import base64
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agents.vision.api import app, model_lock
from agents.vision.experiment import read_cases, score_group, syntax_valid
from agents.vision.run import (
    ROOT,
    load_photo,
    validate_comparison,
    verify_caption_claim,
)
from agents.vision.schema import CaptionClaim, CaptionComparison, VisionObservation


class VisionDeliveryTests(unittest.TestCase):
    """HTTP replay tests check transport only; they are not model experiments."""

    def setUp(self):
        self.client = TestClient(app)
        _, self.photo = load_photo("IMG-01")

    def test_invalid_image_and_blank_id_do_not_call_model(self):
        with patch("agents.vision.api.analyze_image") as infer:
            for data, report_id in (((ROOT / "README.md").read_bytes(), "invalid-file"),
                                    (self.photo[:64], "truncated-image"), (self.photo, " ")):
                response = self.client.post("/vision", data={"report_id": report_id},
                                            files={"image": ("image.jpg", data, "image/jpeg")})
                self.assertEqual(response.status_code, 422)
            infer.assert_not_called()

    def test_missing_fields_and_long_text_are_rejected(self):
        with patch("agents.vision.api.analyze_image") as infer:
            self.assertEqual(self.client.post("/vision").status_code, 422)
            response = self.client.post("/vision", data={"report_id": "long-text", "description": "x" * 2001},
                                        files={"image": ("image.jpg", self.photo, "image/jpeg")})
            self.assertEqual(response.status_code, 422)
            infer.assert_not_called()

    def test_report_id_echo_with_real_saved_output(self):
        path = ROOT / "evaluation/vision/runs/20261011T214102_399836Z_IMG-01.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        with patch("agents.vision.api.analyze_image", return_value=(saved, path)) as infer:
            response = self.client.post("/vision", data={"report_id": "vision-transport-test"},
                                        files={"image": ("photo.jpg", self.photo, "image/jpeg")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report_id"], "vision-transport-test")
        self.assertEqual(response.json()["evidence"], saved["observation"]["evidence"])
        args, photo, data = infer.call_args.args
        self.assertEqual(args.report_id, "vision-transport-test")
        self.assertIsNone(args.description)
        self.assertTrue(args.severity_rubric)
        self.assertEqual(args.prompt_version, "v11")
        self.assertEqual(data, self.photo)
        self.assertTrue((ROOT / photo["file"]).is_relative_to(ROOT))

    def test_busy_model_returns_503_without_another_call(self):
        with model_lock, patch("agents.vision.api.analyze_image") as infer:
            response = self.client.post("/vision", data={"report_id": "busy-test"},
                                        files={"image": ("photo.jpg", self.photo, "image/jpeg")})
            self.assertEqual(response.status_code, 503)
            infer.assert_not_called()

    def test_actual_failed_run_is_not_a_successful_http_observation(self):
        path = ROOT / "evaluation/vision/runs/20261017T114001_930175Z_IMG-04.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        with patch("agents.vision.api.analyze_image", return_value=(saved, path)):
            response = self.client.post("/vision", data={"report_id": "failure-replay"},
                                        files={"image": ("photo.jpg", self.photo, "image/jpeg")})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("category", response.json())

    def test_failed_run_counts_in_quality_denominators(self):
        path = ROOT / "evaluation/vision/runs/20261017T114001_930175Z_IMG-04.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        cases = [c for c in read_cases() if c["case_id"] == "C03"]
        group = score_group([{"case_id": "C03", "result": saved}], cases, "test", saved["model"], "v5")
        self.assertTrue(syntax_valid(saved))  # Its JSON parses, but the missing-text check failed.
        self.assertEqual(group["metrics"]["valid_output"], {"correct": 0, "total": 1, "rate": 0.0})
        self.assertEqual(group["metrics"]["conservative_abstention"]["correct"], 0)
        self.assertIsNone(group["median_success_seconds"])

    def test_repeated_text_and_blur_conditions_do_not_inflate_category_denominator(self):
        group = score_group([], read_cases(), "test", "not_called", "v2")
        self.assertEqual(group["metrics"]["category_accuracy"]["total"], 5)
        self.assertEqual(group["metrics"]["text_image_match"]["total"], 2)
        self.assertEqual(group["metrics"]["severity_agreement"]["total"], 4)

    def test_supplied_text_with_null_comparison_requires_a_reason(self):
        path = ROOT / "evaluation/vision/runs/20261017T172138_096324Z_IMG-01.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        observation = VisionObservation.model_validate(saved["observation"])
        validate_comparison(observation, saved["description"])
        # This mutation is a validation fixture, never saved as model evidence.
        observation.uncertainty_reason = None
        with self.assertRaisesRegex(ValueError, "needs an uncertainty reason"):
            validate_comparison(observation, saved["description"])

    def test_missing_text_rejects_a_boolean_comparison(self):
        path = ROOT / "evaluation/vision/runs/20261017T114001_930175Z_IMG-04.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        observation = VisionObservation.model_validate_json(saved["raw_response"]["message"]["content"])
        with self.assertRaisesRegex(ValueError, "no description"):
            validate_comparison(observation, None)

    def test_structure_check_cannot_detect_the_actual_vague_text_failure(self):
        path = ROOT / "evaluation/vision/runs/20261017T174532_118741Z_UPLOAD-3a42ff6ad5fd.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        observation = VisionObservation.model_validate(saved["observation"])
        # True passes field checks even for vague text; the prompt study scores it.
        self.assertTrue(observation.text_image_consistent)
        validate_comparison(observation, saved["description"])

    def test_caption_schema_rejects_a_missing_nonclaim_reason(self):
        path = ROOT / "evaluation/vision/runs/20261017T181647_512402Z_IMG-01.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        raw = saved["stages"][0]["raw_response"]["message"]["content"]
        decision = CaptionComparison.model_validate_json(raw)
        self.assertEqual(decision.decision, "NO_CLAIM")
        # Invalid test fixture only; never saved or counted as inference evidence.
        invalid = {**decision.model_dump(), "reason": None}
        with self.assertRaisesRegex(ValueError, "needs a reason"):
            CaptionComparison.model_validate(invalid)

    def load_claim_case(self, case_id):
        """Read an actual v11 pipeline; replaying it is not an inference experiment."""
        index = ROOT / "evaluation/vision/claim_gate/runs.jsonl"
        row = next(row for row in map(json.loads, index.read_text().splitlines())
                   if row["case_id"] == case_id and row["prompt_version"] == "v11")
        return json.loads((ROOT / row["result_file"]).read_text(encoding="utf-8"))

    def replay_claim_case(self, saved):
        """Check stage inputs while replaying only recorded model responses."""
        stages = iter(saved["stages"])

        def replay(messages, args, stage, response_model):
            recorded = next(stages)
            self.assertEqual(messages[0]["content"], recorded["prompt_text"])
            self.assertEqual(messages[1]["content"], recorded["user_message"])
            if stage["name"] == "claim":
                self.assertNotIn("images", messages[1])
            else:
                self.assertEqual(base64.b64decode(messages[1]["images"][0]), self.photo)
                self.assertEqual(set(json.loads(messages[1]["content"])), {"condition"})
            stage.update(recorded)
            return response_model.model_validate(recorded["observation"]).model_dump()

        args = argparse.Namespace(prompt_version="v11", description=saved["description"])
        result = {"options": saved["options"], "model_digest": saved["model_digest"]}
        original = json.dumps(saved["visual_observation"])
        with patch("agents.vision.run.run_model", side_effect=replay) as infer:
            output = verify_caption_claim(saved["visual_observation"], args, result, self.photo)
        self.assertEqual(json.dumps(saved["visual_observation"]), original)
        self.assertEqual(output, saved["observation"])
        self.assertEqual(infer.call_count, len(saved["stages"]))

    def test_nonclaim_does_not_reach_visual_verification(self):
        saved = self.load_claim_case("T02")
        self.assertEqual(len(saved["stages"]), 1)
        self.replay_claim_case(saved)

    def test_concrete_claim_uses_original_pixels_and_preserves_visual_fields(self):
        saved = self.load_claim_case("T04")
        self.assertEqual(len(saved["stages"]), 2)
        self.replay_claim_case(saved)

    def test_claim_schema_rejects_a_missing_condition(self):
        saved = self.load_claim_case("T04")
        claim = saved["stages"][0]["observation"]
        CaptionClaim.model_validate(claim)
        # Invalid validation fixture only, not saved as a model attempt.
        with self.assertRaisesRegex(ValueError, "positive condition"):
            CaptionClaim.model_validate({**claim, "condition": None})


if __name__ == "__main__":
    unittest.main()
