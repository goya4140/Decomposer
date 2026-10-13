from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import clamp, number, write_json


DEFAULT_ROLES = {
    "picture", "photo", "photograph", "icon", "illustration", "logo", "rendered_object"
}


def _area(bbox: Any) -> float:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return 0.0
    return max(0.0, number(bbox[2], 0.0)) * max(0.0, number(bbox[3], 0.0))


def _intersection_area(left: Any, right: Any) -> float:
    if not isinstance(left, list) or len(left) != 4 or not isinstance(right, list) or len(right) != 4:
        return 0.0
    lx, ly, lw, lh = (number(value, 0.0) for value in left)
    rx, ry, rw, rh = (number(value, 0.0) for value in right)
    width = max(0.0, min(lx + lw, rx + rw) - max(lx, rx))
    height = max(0.0, min(ly + lh, ry + rh) - max(ly, ry))
    return width * height


def _ocr_coverage(bbox: Any, candidates: dict[str, dict[str, Any]]) -> float:
    area = _area(bbox)
    if area <= 0:
        return 1.0
    covered = sum(
        _intersection_area(bbox, candidate.get("bbox"))
        for candidate in candidates.values()
        if candidate.get("source") == "ocr" and number(candidate.get("confidence"), 0.0) >= 0.8
    )
    return clamp(covered / area, 0.0, 1.0)


def decide(
    recognition: dict[str, Any],
    evidence: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    policy = config.get("asset_policy", {})
    max_area_ratio = clamp(number(policy.get("max_area_ratio"), 0.35), 0.01, 0.85)
    max_recognition_leaf_area_ratio = clamp(
        number(policy.get("max_recognition_leaf_area_ratio"), max_area_ratio),
        0.01, 0.85,
    )
    max_ocr_coverage = clamp(number(policy.get("max_ocr_coverage"), 0.12), 0.0, 1.0)
    allow_recognition_bbox_fallback = bool(policy.get("allow_recognition_bbox_fallback", True))
    minimum_recognition_confidence = clamp(number(policy.get("minimum_recognition_confidence"), 0.9), 0.0, 1.0)
    minimum_sam_object_coverage = clamp(number(policy.get("minimum_sam_object_coverage"), 0.6), 0.0, 1.0)
    allowed_roles = {
        str(value).strip().lower()
        for value in policy.get("allowed_roles", sorted(DEFAULT_ROLES))
    }
    candidates = {
        str(item.get("id")): item
        for item in evidence.get("candidates", [])
        if isinstance(item, dict) and item.get("id")
    }
    decisions: list[dict[str, Any]] = []
    for obj in recognition.get("objects", []):
        reasons: list[str] = []
        eligible: list[dict[str, Any]] = []
        strong_recognition_leaf = (
            obj.get("category") == "image"
            and obj.get("semantic_level") == "leaf"
            and number(obj.get("confidence"), 0.0) >= minimum_recognition_confidence
            and not str(obj.get("text") or "").strip()
            and _area(obj.get("bbox")) > 0
        )
        rejected_partial_sam = False
        if obj.get("category") != "image":
            reasons.append("category_requires_native_representation")
        if obj.get("semantic_level") == "container":
            reasons.append("container_not_crop_eligible")
        for candidate_id in obj.get("candidate_ids", []):
            candidate = candidates.get(str(candidate_id))
            if not candidate or candidate.get("source") not in {"sam", "sam3"}:
                continue
            if candidate.get("label") not in allowed_roles:
                continue
            if not candidate.get("crop_candidate"):
                continue
            if candidate.get("semantic_level") != "leaf" or candidate.get("child_ids"):
                continue
            if candidate.get("whole_canvas_risk") or candidate.get("needs_split"):
                continue
            if number(candidate.get("area_ratio"), 1.0) > max_area_ratio:
                continue
            if number(candidate.get("ocr_covered_area_ratio"), 1.0) > max_ocr_coverage:
                continue
            if strong_recognition_leaf and (
                _intersection_area(candidate.get("bbox"), obj.get("bbox")) / _area(obj.get("bbox"))
                < minimum_sam_object_coverage
            ):
                rejected_partial_sam = True
                continue
            eligible.append(candidate)
        if rejected_partial_sam and not eligible:
            reasons.append("sam_insufficient_object_coverage")
        source_basis = None
        if obj.get("category") == "image" and obj.get("semantic_level") != "container" and eligible:
            selected = sorted(
                eligible,
                key=lambda value: (-number(value.get("confidence"), 0.0), number(value.get("area_ratio"), 1.0)),
            )[0]
            decision = "localized_raster"
            reasons.extend(["sam_visual_leaf", "below_area_limit", "low_ocr_overlap"])
            source_candidate_id = selected["id"]
            source_basis = "sam_candidate"
            approved_bbox = list(selected["bbox"])
            area_ratio = number(selected.get("area_ratio"), 0.0)
        elif obj.get("category") == "image" and obj.get("semantic_level") == "leaf" and allow_recognition_bbox_fallback:
            bbox = list(obj.get("bbox") or [])
            canvas = recognition.get("canvas", {})
            canvas_area = max(1.0, number(canvas.get("width"), 0.0) * number(canvas.get("height"), 0.0))
            area_ratio = _area(bbox) / canvas_area
            ocr_coverage = _ocr_coverage(bbox, candidates)
            confidence = number(obj.get("confidence"), 0.0)
            if (
                len(bbox) == 4
                and area_ratio <= max_recognition_leaf_area_ratio
                and ocr_coverage <= max_ocr_coverage
                and confidence >= minimum_recognition_confidence
                and not str(obj.get("text") or "").strip()
            ):
                decision = "localized_raster"
                reasons.extend([
                    "recognition_image_leaf", "recognition_bbox_fallback", "below_area_limit",
                    "low_ocr_overlap", "high_recognition_confidence",
                ])
                source_candidate_id = f"recognition:{obj['id']}"
                source_basis = "recognition_bbox"
                approved_bbox = bbox
            else:
                decision = "native"
                source_candidate_id = None
                approved_bbox = None
                area_ratio = 0.0
                reasons.append("no_eligible_sam_or_safe_recognition_bbox")
        else:
            decision = "native"
            source_candidate_id = None
            approved_bbox = None
            area_ratio = 0.0
            if obj.get("category") == "image" and not eligible:
                reasons.append("no_eligible_sam_leaf")
        decisions.append({
            "label_id": obj["id"],
            "decision": decision,
            "source_candidate_id": source_candidate_id,
            "source_basis": source_basis,
            "approved_bbox": approved_bbox,
            "area_ratio": round(area_ratio, 6),
            "reason_codes": list(dict.fromkeys(reasons)),
        })
    return {
        "schema_version": "decomposer.asset-decisions.v1",
        "policy": {
            "allowed_roles": sorted(allowed_roles),
            "max_area_ratio": max_area_ratio,
            "max_recognition_leaf_area_ratio": max_recognition_leaf_area_ratio,
            "max_ocr_coverage": max_ocr_coverage,
            "allow_recognition_bbox_fallback": allow_recognition_bbox_fallback,
            "minimum_recognition_confidence": minimum_recognition_confidence,
            "minimum_sam_object_coverage": minimum_sam_object_coverage,
        },
        "decisions": decisions,
        "summary": {
            "localized_raster_count": sum(item["decision"] == "localized_raster" for item in decisions),
            "native_count": sum(item["decision"] == "native" for item in decisions),
        },
    }


def materialize(
    recognition: dict[str, Any],
    evidence: dict[str, Any],
    config: dict[str, Any],
    path: str | Path,
) -> dict[str, Any]:
    result = decide(recognition, evidence, config)
    write_json(path, result)
    return result
