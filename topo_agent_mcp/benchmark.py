# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load and score the fixed real-route development set."""

import hashlib
import importlib
import io
import json
import math
import sys
from pathlib import Path

from PIL import Image


class Benchmark:
    def __init__(self, topo_root, data_dir=None):
        self.root = Path(topo_root).resolve()
        self.data = Path(data_dir or self.root / "samples" / "real_routes").resolve()
        manifest = self.data / "annotations.json"
        evaluator = self.root / "topo_agent" / "eval.py"
        if not manifest.is_file() or not evaluator.is_file():
            raise FileNotFoundError("Set TOPO_AGENT_ROOT and TOPO_MCP_DATA_DIR to the evaluator and real_routes data")
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        self.eval = importlib.import_module("topo_agent.eval")
        self.items = self._load_manifest(manifest)
        self.cases = {item["id"]: item for item in self.items}
        digest = hashlib.sha256()
        for path in [manifest, *sorted((self.data / "images").glob("*.jpg")), evaluator]:
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        self.version = digest.hexdigest()

    def _load_manifest(self, manifest):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        items, seen = [], set()
        for image in data.get("images", []):
            image_id = image.get("id")
            relative = image.get("file")
            if not isinstance(image_id, str) or not isinstance(relative, str):
                raise ValueError("Every image needs an id and file")
            path = (self.data / relative).resolve()
            if not path.is_relative_to(self.data) or not path.is_file():
                raise ValueError(f"Invalid image path: {relative}")
            jpeg = path.read_bytes()
            with Image.open(io.BytesIO(jpeg)) as photo:
                width, height = photo.size
            for route in image.get("routes", []):
                case = f"{image_id}_r{route.get('route_id')}"
                if case in seen or route.get("route_id") is None:
                    raise ValueError(f"Duplicate or missing route ID: {case}")
                seen.add(case)
                tap = route.get("tap") or {}
                if any(not _number(tap.get(k)) or not 0 <= tap[k] <= 1 for k in ("x", "y")):
                    raise ValueError(f"Invalid tap: {case}")
                marks = []
                for truth in route.get("truth") or []:
                    points = truth.get("points")
                    if (not isinstance(points, list) or len(points) < 3 or
                            any(not isinstance(p, list) or len(p) != 2 or
                                any(not _number(v) or not 0 <= v <= 1 for v in p) for p in points)):
                        raise ValueError(f"Invalid truth polygon: {case}")
                    xs, ys = [p[0] for p in points], [p[1] for p in points]
                    marks.append({"kind": "hold", "use": "any", "x": sum(xs) / len(xs),
                                  "y": sum(ys) / len(ys),
                                  "r": max(max(xs) - min(xs), max(ys) - min(ys)) / 2,
                                  "points": points})
                if not marks:
                    raise ValueError(f"No truth holds: {case}")
                items.append({"id": case, "jpeg": jpeg, "tap": tap,
                              "marks": {"marks": marks, "photo": {"width": width, "height": height}}})
        if not items:
            raise ValueError("No benchmark routes")
        return items

    def info(self):
        images = list((self.data / "images").glob("*.jpg"))
        return {"dataset": "real_routes", "version": self.version,
                "images": len(images), "routes": len(self.items),
                "case_ids": sorted(self.cases)}

    def score(self, rows):
        if not isinstance(rows, list) or len(rows) != len(self.cases):
            raise ValueError(f"Submit exactly {len(self.cases)} case rows")
        seen, scored = set(), []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Every case row must be an object")
            case = row.get("case_id")
            if case not in self.cases or case in seen:
                raise ValueError(f"Unknown or duplicate case: {case}")
            seen.add(case)
            seconds = row.get("seconds")
            if not _number(seconds) or not 0 <= seconds <= 3600:
                raise ValueError(f"{case}: seconds must be between 0 and 3600")
            error = row.get("error", "")
            if not isinstance(error, str) or len(error) > 500:
                raise ValueError(f"{case}: invalid error")
            holds = row.get("holds")
            if not isinstance(holds, list) or len(holds) > 500:
                raise ValueError(f"{case}: holds must be a list of at most 500")
            for hold in holds:
                _validate_hold(case, hold)
            item = self.cases[case]
            marks = item["marks"]
            truth = self.eval.holds_of(marks)
            size = marks["photo"]
            hits, found, count = self.eval.match(truth, holds, size["width"], size["height"])
            scored.append({"problem": case, "method": "submission", "hits": hits,
                           "found": found, "truth": count, "seconds": round(seconds, 1),
                           "error": error})
        scored.sort(key=lambda row: row["problem"])
        metrics = self.eval.summary(scored)["submission"]
        hits, found, truth = (sum(row[key] for row in scored) for key in ("hits", "found", "truth"))
        metrics["f1"] = round(2 * hits / (found + truth), 3) if found + truth else 0.0
        metrics["hits"] = hits
        metrics["found"] = found
        metrics["truth"] = truth
        return metrics, scored


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_hold(case, hold):
    if not isinstance(hold, dict):
        raise ValueError(f"{case}: hold must be an object")
    if any(not _number(hold.get(key)) or not 0 <= hold[key] <= 1 for key in ("x", "y")):
        raise ValueError(f"{case}: hold x/y must be normalized numbers")
    points = hold.get("points")
    if points is not None:
        if (not isinstance(points, list) or len(points) < 3 or len(points) > 1000
                or any(not isinstance(p, list) or len(p) != 2 or
                       any(not _number(v) or not 0 <= v <= 1 for v in p) for p in points)):
            raise ValueError(f"{case}: invalid hold polygon")
    if not points and (not _number(hold.get("r")) or not 0 <= hold["r"] <= 1):
        raise ValueError(f"{case}: hold needs a polygon or normalized radius")
