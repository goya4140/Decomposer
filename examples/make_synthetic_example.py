#!/usr/bin/env python3
"""Generate original geometry and fixture proposals; no research data required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.out
    fixtures = root / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 40, 110, 120), fill="#DBEAFE", outline="#2563EB", width=2)
    draw.ellipse((210, 40, 290, 120), fill="#DCFCE7", outline="#16A34A", width=2)
    image.save(root / "source.png")
    rows = [("box", "rect", [30, 40, 80, 80], "#DBEAFE", "#2563EB"),
            ("circle", "ellipse", [210, 40, 80, 80], "#DCFCE7", "#16A34A")]
    proposals = {
        "recognition": {"background": "#FFFFFF", "objects": [
            {"id": owner, "category": "shape", "bbox": bbox, "text": "", "confidence": 1.0}
            for owner, kind, bbox, fill, stroke in rows]},
        "representation": {"components": [
            {"label_id": owner, "width": 80, "height": 80, "primitives": [
                {"id": "body", "kind": kind, "bbox": [0, 0, 80, 80],
                 "style": {"fill": fill, "stroke": stroke, "stroke_width": 2}}]}
            for owner, kind, bbox, fill, stroke in rows]},
        "layout": {"operations": [
            {"op": "place", "label_id": owner, "bbox": bbox, "rotation_deg": 0}
            for owner, kind, bbox, fill, stroke in rows]},
        "refinement": {"acceptable": True, "owner_stage": "layout",
                       "mechanism": "synthetic-smoke-stop", "summary": "Stop fixture refinement.",
                       "affected_label_ids": [], "affected_primitive_ids": [],
                       "confidence": 1.0, "operations": []},
    }
    for stage, proposal in proposals.items():
        (fixtures / f"{stage}.json").write_text(json.dumps(proposal, indent=2) + "\n")
    print(root)


if __name__ == "__main__":
    main()
