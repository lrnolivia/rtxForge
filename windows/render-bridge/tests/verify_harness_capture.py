"""Validate real recorder output against the controlled D3D12 harness graph."""
import json
from pathlib import Path
import struct
import sys


def verify(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Capture exceeds the diagnostic size budget")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["stage"] == "diagnostic" and data["api"] == "d3d12"
    assert data["sr_enabled"] is False and data["fg_enabled"] is False
    assert data["gpu_execution_order_verified"] is False
    assert data["jitter_verified"] is False and data["motion_vectors_verified"] is False
    assert data["dropped_events"] == 0 and data["catalog_drops"] == 0
    assert data["sampled_descriptor_ranges"] == 0
    resources = {r["id"]: r for r in data["resources"]}
    draws = [e for e in data["events"] if e["kind"] == "draw"]
    frames = sorted({e["frame"] for e in draws})
    assert len(frames) == 2 and frames[1] == frames[0] + 1
    assert len(draws) == 4
    assert len({e["shader_sha256"] for e in draws}) == 2
    assert all(len(e["shader_sha256"]) == 64 for e in draws)
    for frame in frames:
        scene, post = [e for e in draws if e["frame"] == frame]
        assert len(scene["targets"]) == 2
        color, motion = (resources[r] for r in scene["targets"])
        assert (color["width"], color["height"], color["format"]) == (320, 180, 10)
        assert (motion["width"], motion["height"], motion["format"]) == (320, 180, 34)
        depth = resources[scene["depth"]]
        assert (depth["width"], depth["height"], depth["format"]) == (320, 180, 39)
        output = resources[post["targets"][0]]
        assert (output["width"], output["height"], output["format"]) == (640, 360, 28)
        read_ids = {d["resource"] for d in post["descriptors"] if d["type"] == 2}
        assert read_ids == {color["id"], motion["id"], depth["id"]}
        assert all(d["alive"] for d in post["descriptors"])
        submits = [e for e in data["events"] if e["kind"] == "submit" and e["frame"] == frame]
        assert any(e["command_list"] == scene["command_list"] == post["command_list"] for e in submits)
    samples = data["constant_buffer_samples"]
    assert {s["frame"] for s in samples} == set(frames)
    jitter_x = set()
    for sample in samples:
        values = struct.unpack("<64f", bytes.fromhex(sample["bytes_hex"]))
        assert [values[i] for i in (0, 5, 10, 15)] == [1.0] * 4
        jitter_x.add(values[16])
    assert jitter_x == {-0.25, 0.25}
    return {"pass": True, "criterion": "controlled D3D12 input recorder", "frames": frames,
            "draws": len(draws), "resources": len(resources), "camera_samples": len(samples),
            "valhalla_verified": False, "sr_verified": False, "fg_verified": False}


if __name__ == "__main__":
    print(json.dumps(verify(sys.argv[1])))
