"""Check real demonstration images, scene separation and comparison conditions."""

import argparse
import base64
import json
import unittest
from unittest.mock import patch

from agents.vision.compare_prompts import check_pair
from agents.vision.run import ROOT, build_messages, load_photo, load_prompt, run_case
from agents.vision.schema import VisionDecision, VisionDecisionWithoutText


class VisionPromptTests(unittest.TestCase):
    """No model responses are fabricated; tests use source images and saved runs."""

    def test_zero_shot_request_keeps_original_inputs(self):
        photo, image_bytes = load_photo("IMG-01")
        prompt, demonstrations, metadata = load_prompt("v2", photo)
        saved = json.loads((ROOT / "evaluation/vision/runs/20261011T214102_399836Z_IMG-01.json").read_text())
        messages = build_messages(prompt, image_bytes, None, demonstrations)
        self.assertIsNone(metadata)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["content"], saved["prompt_text"])
        self.assertEqual(messages[1]["content"], saved["user_message"])
        self.assertEqual(base64.b64decode(messages[1]["images"][0]), image_bytes)

    def test_few_shot_images_and_answers_stay_paired(self):
        photo, image_bytes = load_photo("IMG-01")
        prompt, demonstrations, metadata = load_prompt("v3", photo)
        messages = build_messages(prompt, image_bytes, None, demonstrations)
        self.assertEqual([message["role"] for message in messages],
                         ["system", "user", "assistant", "user", "assistant", "user", "assistant", "user"])
        for index, example in enumerate(metadata["spec"]["demonstrations"]):
            _, original = load_photo(example["image_id"])
            self.assertEqual(base64.b64decode(messages[1 + 2 * index]["images"][0]), original)
            self.assertEqual(json.loads(messages[2 + 2 * index]["content"]), example["answer"])
            self.assertNotIn("comment", messages[1 + 2 * index])
        self.assertEqual(base64.b64decode(messages[-1]["images"][0]), image_bytes)

    def test_demonstration_scene_cannot_be_a_query(self):
        for image_id in ("IMG-02", "IMG-06", "IMG-10"):
            photo, _ = load_photo(image_id)
            with self.subTest(image_id=image_id), self.assertRaisesRegex(ValueError, "query's scene"):
                load_prompt("v3", photo)
        # Changing an ID alone must not bypass the scene-level exclusion.
        photo["image_id"] = "another-view-of-the-same-scene"
        with self.assertRaisesRegex(ValueError, "query's scene"):
            load_prompt("v3", photo)

    def test_short_context_is_rejected_before_a_model_call(self):
        args = argparse.Namespace(image_id="IMG-01", prompt_version="v3", context_size=4096)
        with patch("agents.vision.run.requests.post") as post:
            with self.assertRaisesRegex(ValueError, "8192"):
                run_case(args)
            post.assert_not_called()

    def test_comparison_detects_changed_settings_and_system_prompt(self):
        paths = ["20261011T213842_982752Z_IMG-01.json", "20261011T214102_399836Z_IMG-01.json"]
        pair = [json.loads((ROOT / "evaluation/vision/runs" / name).read_text()) for name in paths]
        check_pair(pair, ["v1", "v2"])
        with self.assertRaisesRegex(ValueError, "prompt_sha256"):
            check_pair(pair, ["v2", "v3"])
        pair[1]["options"]["num_ctx"] = 8192
        with self.assertRaisesRegex(ValueError, "options"):
            check_pair(pair, ["v1", "v2"])

    def test_missing_text_schema_rejects_the_actual_v5_failure(self):
        path = ROOT / "evaluation/vision/runs/20261017T114001_930175Z_IMG-04.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        content = result["raw_response"]["message"]["content"]
        # This real answer passed the original field types but compared absent text.
        VisionDecision.model_validate_json(content)
        with self.assertRaisesRegex(ValueError, "text_image_consistent"):
            VisionDecisionWithoutText.model_validate_json(content)

    def test_pipeline_comparison_preserves_saved_schemas(self):
        names = ["20261017T113548_255891Z_IMG-09.json", "20261017T114216_041203Z_IMG-09.json"]
        pair = [json.loads((ROOT / "evaluation/vision/runs" / name).read_text(encoding="utf-8"))
                for name in names]
        before = json.dumps(pair)
        check_pair(pair, ["v4", "v5"])
        self.assertEqual(json.dumps(pair), before)

    def test_contrastive_examples_keep_each_caption_with_its_target(self):
        photo, query_bytes = load_photo("IMG-01")
        prompt, examples, metadata = load_prompt("v7", photo)
        self.assertEqual(prompt, load_prompt("v6", photo)[0])
        messages = build_messages(prompt, query_bytes, "Please help us.", examples)
        _, reference_bytes = load_photo("IMG-02")
        targets = []
        for index, demo in enumerate(metadata["spec"]["demonstrations"]):
            user, assistant = messages[1 + 2 * index:3 + 2 * index]
            self.assertEqual(base64.b64decode(user["images"][0]), reference_bytes)
            self.assertEqual(user["content"], "Citizen description:\n" + demo["description"])
            self.assertEqual(json.loads(assistant["content"]), demo["answer"])
            targets.append(demo["answer"]["text_image_consistent"])
        self.assertEqual(targets, [None, True, False])
        self.assertEqual(base64.b64decode(messages[-1]["images"][0]), query_bytes)

    def test_contrastive_demonstration_scene_is_not_an_evaluation_query(self):
        photo, _ = load_photo("IMG-02")
        with self.assertRaisesRegex(ValueError, "query's scene"):
            load_prompt("v7", photo)


if __name__ == "__main__":
    unittest.main()
