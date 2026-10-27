"""Deterministic registrations must measure the owner region they report."""

import ast
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from decomposer.quality import affected_scene_region, boxes_region, compare


MODULES = (
    "flat_panel_registration",
    "joint_shadow_text_registration",
    "native_shadow_registration",
    "post_short_text_registration",
    "post_tracking_text_registration",
    "rect_fill_registration",
    "short_text_registration",
    "source_line_registration",
    "styled_multiline_registration",
    "text_registration",
    "text_tracking_registration",
)


class LocalAssessmentContractTest(unittest.TestCase):
    def test_owner_region_covers_old_and_new_geometry(self):
        before = {"canvas": {"width": 100, "height": 80}, "elements": [
            {"id": "moved", "bbox": [10, 20, 20, 10]},
            {"id": "other", "bbox": [0, 0, 5, 5]},
        ]}
        after = {"canvas": before["canvas"], "elements": [
            {"id": "moved", "bbox": [25, 12, 20, 16]},
            {"id": "other", "bbox": [0, 0, 5, 5]},
        ]}
        self.assertEqual(affected_scene_region(before, after, ["moved"]), [10, 12, 35, 18])
        self.assertEqual(affected_scene_region(before, after, []), [0, 0, 100, 80])
        with self.assertRaisesRegex(ValueError, "affected primitive missing"):
            affected_scene_region(before, after, ["missing"])




    def test_local_metrics_differ_from_global_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = Image.new("RGB", (100, 100), "white")
            before = reference.copy()
            after = reference.copy()
            ImageDraw.Draw(reference).rectangle((10, 10, 29, 29), fill="black")
            ImageDraw.Draw(after).rectangle((10, 10, 29, 29), fill="black")
            paths = [root / name for name in ("reference.png", "before.png", "after.png")]
            for image, path in zip((reference, before, after), paths):
                image.save(path)
            assessment = compare(*paths, [0, 0, 40, 40])
            self.assertGreater(assessment["local_pixel_delta"], assessment["global_pixel_delta"])
            self.assertGreater(assessment["after_local"]["pixel_similarity"],
                               assessment["before_local"]["pixel_similarity"])


if __name__ == "__main__":
    unittest.main()
