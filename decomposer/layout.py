from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import canonical_bbox, clamp, finite, number, write_json
from .model import fixture_or_model
from .schemas import LAYOUT_PROPOSAL_SCHEMA


def _rotation_hint(obj: dict[str, Any]) -> float:
    hint = str(obj.get("geometry_hint") or "").casefold()
    if "rotat" not in hint:
        return 0.0
    if "counterclockwise" in hint or "counter-clockwise" in hint or "anticlockwise" in hint:
        return 270.0
    if "clockwise" in hint or "90" in hint:
        return 90.0
    return 0.0


def _visible_bbox(bbox: list[float], rotation: float) -> list[float]:
    """Axis-aligned extent after a native quarter-turn around the box center."""
    x, y, width, height = bbox
    if abs(rotation % 180 - 90) > .01:
        return bbox
    center_x, center_y = x + width / 2, y + height / 2
    return [center_x - height / 2, center_y - width / 2, height, width]


def _visible_bbox_inside_canvas(bbox: list[float], rotation: float,
                                canvas: tuple[float, float]) -> bool:
    x, y, width, height = _visible_bbox(bbox, rotation)
    return (width > 0 and height > 0 and x >= -.01 and y >= -.01
            and x + width <= canvas[0] + .01 and y + height <= canvas[1] + .01)


def default_layout(recognition: dict[str, Any]) -> dict[str, Any]:
    placements = []
    for obj in recognition["objects"]:
        x, y, width, height = obj["bbox"]
        rotation = _rotation_hint(obj)
        bbox = [x, y, width, height]
        if rotation in {90.0, 270.0}:
            center_x, center_y = x + width / 2, y + height / 2
            unrotated_width, unrotated_height = height, width
            # The unrotated OOXML box may extend beyond the canvas even when
            # its quarter-turned visible extent exactly matches the source.
            # Clamping here shifts edge-adjacent vertical labels inward.
            left = center_x - unrotated_width / 2
            top = center_y - unrotated_height / 2
            bbox = [left, top, unrotated_width, unrotated_height]
        placements.append({
            "label_id": obj["id"], "bbox": [round(value, 4) for value in bbox], "rotation_deg": rotation,
            "font_scale": 1.0, "visible": True,
        })
    return {
        "placements": placements,
        "component_order": [obj["id"] for obj in recognition["objects"]],
    }


def canonicalize(raw: Any, recognition: dict[str, Any], representation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = raw if isinstance(raw, dict) else {}
    base = default_layout(recognition)
    canvas = (recognition["canvas"]["width"], recognition["canvas"]["height"])
    placements = {item["label_id"]: item for item in base["placements"]}
    order = list(base["component_order"])
    repairs: list[dict[str, Any]] = []
    applied = 0
    operations = raw.get("operations") if isinstance(raw.get("operations"), list) else []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            repairs.append({"index": index, "action": "ignored_non_object_operation"})
            continue
        op = str(operation.get("op") or "").lower()
        label_id = operation.get("label_id")
        if op == "place" and label_id in placements:
            placement = placements[label_id]
            rotation = placement["rotation_deg"]
            if finite(operation.get("rotation_deg")):
                rotation = round(number(operation["rotation_deg"]) % 360, 4)
            if "bbox" in operation:
                raw_bbox = operation["bbox"]
                if (abs(rotation % 180 - 90) <= .01
                        and isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4
                        and all(finite(value) for value in raw_bbox)):
                    proposed = [round(number(value), 4) for value in raw_bbox]
                else:
                    proposed = canonical_bbox(raw_bbox, canvas)
            else:
                proposed = placement["bbox"]
            if _visible_bbox_inside_canvas(proposed, rotation, canvas):
                placement["bbox"] = proposed
                placement["rotation_deg"] = rotation
                applied += 1
            else:
                repairs.append({"index": index, "action": "ignored_outside_visible_canvas", "label_id": label_id})
        elif op == "scale_text" and label_id in placements:
            placements[label_id]["font_scale"] = round(clamp(number(operation.get("factor"), 1), 0.1, 10), 4)
            applied += 1
        elif op in ("front", "back"):
            requested = operation.get("label_ids", [])
            selected = [value for value in requested if value in placements]
            if selected:
                remaining = [value for value in order if value not in selected]
                order = remaining + selected if op == "front" else selected + remaining
                applied += 1
        elif op == "hide" and label_id in placements:
            placements[label_id]["visible"] = False
            applied += 1
        else:
            repairs.append({"index": index, "action": "ignored_invalid_operation", "op": op})
    if placements and not any(item["visible"] for item in placements.values()):
        for item in placements.values():
            item["visible"] = True
        repairs.append({"action": "restored_visibility_after_all_components_hidden"})
    result = {
        "schema_version": "decomposer.layout.v1",
        "placements": [placements[label_id] for label_id in base["component_order"]],
        "component_order": order,
        "degraded": bool(repairs),
    }
    report = {"operation_count": len(operations), "applied_count": applied, "repair_count": len(repairs), "repairs": repairs}
    validate(result, representation, recognition)
    return result, report


def validate(data: dict[str, Any], representation: dict[str, Any], recognition: dict[str, Any]) -> None:
    expected = [item["label_id"] for item in representation["components"]]
    actual = [item["label_id"] for item in data["placements"]]
    if actual != expected or set(data["component_order"]) != set(expected) or len(data["component_order"]) != len(expected):
        raise AssertionError("layout must place and order every component exactly once")
    width, height = recognition["canvas"]["width"], recognition["canvas"]["height"]
    for placement in data["placements"]:
        if not _visible_bbox_inside_canvas(placement["bbox"], placement["rotation_deg"],
                                           (width, height)):
            raise AssertionError(f"invalid placement {placement['label_id']}")


def run(
    image: str | Path,
    recognition: dict[str, Any],
    representation: dict[str, Any],
    config: dict[str, Any],
    directory: str | Path,
    calls: str | Path,
    fixture_dir: str | Path | None = None,
) -> dict[str, Any]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    base = default_layout(recognition)
    write_json(directory / "default-layout.json", base)
    payload = {
        "canvas": recognition["canvas"], "objects": recognition["objects"],
        "components": representation["components"], "default_layout": base,
        "allowed_operations": ["place", "scale_text", "front", "back", "hide"],
        # Historical knowledge is deliberately unavailable to first-pass generation.
        "applicable_memories": [],
    }
    prompt = (Path(__file__).parents[1] / "prompts" / "layout.md").read_text()
    proposal, metadata = fixture_or_model("layout", prompt, payload, LAYOUT_PROPOSAL_SCHEMA, image, config, Path(calls) / "layout", fixture_dir)
    write_json(directory / "model-output.json", proposal)
    result, report = canonicalize(proposal, recognition, representation)
    report["model"] = metadata
    write_json(directory / "patch-report.json", report)
    write_json(directory / "layout.json", result)
    return result
