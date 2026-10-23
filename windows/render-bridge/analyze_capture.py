"""Summarize observed texture bindings without inferring DLSS input semantics."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys


def analyze(path):
    path = Path(path)
    raw = path.read_bytes() if path.stat().st_size <= 64 * 1024 * 1024 else None
    if raw is None:
        raise ValueError("Capture exceeds the 64 MiB analysis budget")
    data = json.loads(raw)
    if data.get("schema") != 1 or data.get("stage") != "diagnostic" or data.get("api") != "d3d12":
        raise ValueError("Expected a render bridge D3D12 diagnostic capture")
    resources = {r["id"]: r for r in data["resources"]}
    activity = defaultdict(Counter)
    shaders = defaultdict(lambda: {"events": Counter(), "reads": set(), "writes": set()})
    unresolved = 0
    missing_types = 0
    for event in data["events"]:
        if event["kind"] == "submit":
            continue
        reads, writes = set(), set()
        for resource in set(event["targets"]):
            if resource:
                activity[resource]["render_target_events"] += 1
                writes.add(resource)
        if event["depth"]:
            activity[event["depth"]]["depth_attachment_events"] += 1
            writes.add(event["depth"])
        for binding in event["descriptors"]:
            expected = binding.get("expected_type", binding["type"])
            missing_types += "expected_type" not in binding and binding["type"] == 0
            resource = binding["resource"]
            if expected != 0 and (not resource or not binding["alive"]):
                unresolved += 1
            if resource and binding["alive"]:
                if expected in (1, 2, 4):
                    reads.add(resource)
                elif expected in (3, 5):
                    writes.add(resource)
        for resource in reads:
            activity[resource]["shader_read_events"] += 1
        for resource in writes:
            activity[resource]["possible_write_events"] += 1
        shader = shaders[event["shader_sha256"]]
        shader["events"][event["kind"]] += 1
        shader["reads"].update(reads)
        shader["writes"].update(writes)
    textures = []
    for resource, counts in sorted(activity.items()):
        description = resources.get(resource)
        if description and description["height"]:
            textures.append({**description, "observations": dict(counts)})
    return {
        "capture_sha256": hashlib.sha256(raw).hexdigest(),
        "executable": data["executable"],
        "frames": [data["capture_start"], data["capture_end"]],
        "event_counts": dict(Counter(e["kind"] for e in data["events"])),
        "coverage": {
            "dropped_events": data["dropped_events"],
            "catalog_drops": data["catalog_drops"],
            "catalog_drop_reasons": data.get("catalog_drop_reasons"),
            "sampled_descriptor_ranges": data["sampled_descriptor_ranges"],
            "constant_samples": len(data["constant_buffer_samples"]),
            "constant_samples_truncated": data.get("constant_buffer_samples_truncated"),
            "unresolved_or_dead_resource_bindings": unresolved,
            "legacy_bindings_without_expected_type": missing_types,
            "missing_shader_fingerprints": sum(e["kind"] != "submit" and not e["shader_sha256"] for e in data["events"]),
            "gpu_execution_order_verified": data["gpu_execution_order_verified"],
        },
        "interpretation": "Binding observations only; attachment presence does not prove a write, and descriptor presence does not prove shader access. CPU recording order does not establish GPU execution order. No color, depth, motion, jitter or HUD input is semantically verified.",
        "texture_activity": textures,
        "shader_bindings": [
            {"sha256": key, "event_counts": dict(value["events"]),
             "read_bindings": sorted(value["reads"]), "possible_write_bindings": sorted(value["writes"])}
            for key, value in sorted(shaders.items())
        ],
        "sr_verified": False,
        "fg_verified": False,
    }


if __name__ == "__main__":
    print(json.dumps(analyze(sys.argv[1]), indent=2))
