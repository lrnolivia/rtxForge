"""Stage the pinned native Vulkan provider and emit a Visual Studio build command.

Dependencies are read as Git objects at their exact revisions. No dependency
checkout is reset or edited. Build output must be outside the product checkout.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def archive(repo: Path, commit: str, destination: Path, paths: list[str]) -> None:
    data = git(repo, "archive", "--format=tar", commit, *paths)
    with tarfile.open(fileobj=io.BytesIO(data)) as source:
        for member in source.getmembers():
            if not member.isfile():
                continue
            path = (destination / member.name).resolve()
            if not path.is_relative_to(destination.resolve()):
                raise ValueError("Dependency archive escaped staging directory")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.extractfile(member).read())


def replace_once(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if text.count(before) != 1:
        raise ValueError(f"Pinned source adaptation no longer matches: {path.name}: {before[:65]}")
    path.write_text(text.replace(before, after), encoding="utf-8")


def stage(deps: Path, output: Path, vcvars: Path) -> None:
    product = ROOT.parents[1]
    output = output.resolve()
    if output.is_relative_to(product) or output.exists():
        raise ValueError("Choose a new output directory outside the product checkout")
    manifest = json.loads((ROOT / "source.json").read_text())
    for name, entry in manifest["dependencies"].items():
        if git(deps / name, "rev-parse", entry["commit"] + "^{commit}").decode().strip() != entry["commit"]:
            raise ValueError(f"Missing pinned dependency: {name}")
    output.mkdir(parents=True)
    stage_dir = output / "source"
    stage_dir.mkdir()
    for name in ("src", "nr", "panel", "mfg", "checks", "licenses"):
        shutil.copytree(ROOT / name, stage_dir / name)
    shutil.copyfile(ROOT / "LICENSE", stage_dir / "LICENSE")
    pin = manifest["dependencies"]
    imgui_files = ["imgui.cpp", "imgui_draw.cpp", "imgui_tables.cpp", "imgui_widgets.cpp",
                   "imgui.h", "imgui_internal.h", "imconfig.h", "imstb_rectpack.h",
                   "imstb_textedit.h", "imstb_truetype.h", "LICENSE.txt",
                   "backends/imgui_impl_win32.cpp", "backends/imgui_impl_win32.h",
                   "backends/imgui_impl_vulkan.cpp", "backends/imgui_impl_vulkan.h"]
    imgui = stage_dir / "rdr/vendor/imgui"
    archive(deps / "imgui-mfg", pin["imgui-mfg"]["commit"], imgui, imgui_files)
    # Upload buffers follow the acquired game image, whose fence we checked.
    # A cyclic frame index can reuse a still-busy buffer after skipped presents.
    replace_once(imgui / "backends/imgui_impl_vulkan.cpp",
                 "VkCommandBuffer command_buffer, VkPipeline pipeline)\n{",
                 "VkCommandBuffer command_buffer, VkPipeline pipeline, uint32_t image_index)\n{")
    replace_once(imgui / "backends/imgui_impl_vulkan.h",
                 "VkPipeline pipeline = VK_NULL_HANDLE);",
                 "VkPipeline pipeline = VK_NULL_HANDLE, uint32_t image_index = UINT32_MAX);")
    replace_once(imgui / "backends/imgui_impl_vulkan.cpp",
                 "wrb->Index = (wrb->Index + 1) % wrb->Count;",
                 "IM_ASSERT(image_index == UINT32_MAX || image_index < wrb->Count);\n    wrb->Index = image_index == UINT32_MAX ? (wrb->Index + 1) % wrb->Count : image_index;")
    nr_source = deps / "optiscaler-dlss5"
    archive(nr_source, pin[nr_source.name]["commit"], stage_dir / "nr-source", [
        "OptiScaler/dlssnr/DlssNrFeature_Vk.cpp", "OptiScaler/dlssnr/DlssNrFeature_Vk.h",
        "OptiScaler/dlssnr/forwarder/dlssnr_forwarder.cpp", "OptiScaler/shaders/Shader_Vk.cpp",
        "OptiScaler/shaders/Shader_Vk.h", "OptiScaler/shaders/dlssnr/DlssNr_Vk.cpp",
        "OptiScaler/shaders/dlssnr/DlssNr_Vk.h", "OptiScaler/shaders/dlssnr/DlssNr_Common.h",
        "OptiScaler/shaders/dlssnr/precompile", "OptiScaler/shaders/output_scaling",
        "external/nvngx_dlss_sdk", "external/nlohmann/json.hpp", "LICENSE"])
    nr_root = stage_dir / "nr-source/OptiScaler"
    # Generate and compile the canonical panel, including its exact Inter assets.
    (nr_root / "menu").mkdir(parents=True)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(product / "providers/skynizz-bridge/Generate-Panel.ps1"),
                    "-SourceRoot", str(stage_dir / "nr-source")], check=True, capture_output=True)
    for path in (nr_root / "menu").iterdir():
        shutil.copyfile(path, stage_dir / "panel" / path.name)

    backend = nr_root / "dlssnr/DlssNrFeature_Vk.cpp"
    # Count completed composition recording, never an attempted/refused model call.
    replace_once(backend, "    g_vk.frames++;\n", "")
    replace_once(backend, "    // Close it, and read the pair", "    g_vk.frames++;\n\n    // Close it, and read the pair")
    replace_once(backend, "    const int evaluated = g_vk.evaluate(",
                 '    float mvScaleX = 1.f, mvScaleY = 1.f;\n'
                 '    params->Get("MV.Scale.X", &mvScaleX);\n'
                 '    params->Get("MV.Scale.Y", &mvScaleY);\n'
                 '    const int evaluated = g_vk.evaluate(')
    replace_once(backend, "cfg.DlssNrAutoMask.value_or_default() ? 1 : 0, 1.0f, 1.0f);",
                 "cfg.DlssNrAutoMask.value_or_default() ? 1 : 0, mvScaleX, mvScaleY);")
    # This provider has no generic upscaler feature object. NR always passes
    # explicit image dimensions and its own scaler selection.
    scaler = nr_root / "shaders/output_scaling/OS_Vk.cpp"
    for expression, replacement in {
        "State::Instance().currentFeature->TargetWidth()": "InResourceView.Width",
        "State::Instance().currentFeature->TargetHeight()": "InResourceView.Height",
        "State::Instance().currentFeature->DisplayWidth()": "OutResourceView.Width",
        "State::Instance().currentFeature->DisplayHeight()": "OutResourceView.Height",
    }.items():
        replace_once(scaler, expression, replacement)
    # Preserve both the pinned HLSL and the upstream compiled SPIR-V in the source receipt.
    functions = set()
    nr_cpp = [nr_root / "dlssnr/DlssNrFeature_Vk.cpp", nr_root / "shaders/Shader_Vk.cpp",
              nr_root / "shaders/dlssnr/DlssNr_Vk.cpp", scaler]
    for source in nr_cpp:
        functions.update(re.findall(r"\b(vk[A-Z]\w+)\s*\(", source.read_text(encoding="utf-8-sig")))
    instance_functions = {"vkGetPhysicalDeviceProperties", "vkGetPhysicalDeviceMemoryProperties"}
    header = ["#pragma once", "#include <vulkan/vulkan.h>"]
    header += [f"inline PFN_{f} {f}{{}};" for f in sorted(functions)]
    header += ["inline bool NrBindDispatch(PFN_vkGetInstanceProcAddr gipa, PFN_vkGetDeviceProcAddr gdpa, VkInstance instance, VkDevice device) {", "bool ready = true;"]
    for function in sorted(functions):
        lookup = f'gipa(instance, "{function}")' if function in instance_functions else f'gdpa(device, "{function}")'
        header += [f"{function} = reinterpret_cast<PFN_{function}>({lookup}); ready = ready && {function};"]
    header += ["return ready;", "}"]
    (stage_dir / "nr/VulkanDispatch.h").write_text("\n".join(header) + "\n")
    for name, paths in {"Vulkan-Headers": ["include", "LICENSE.md", "LICENSES"],
                        "Streamline-2.12": ["include", "license.txt"],
                        "Detours": ["src", "system.mak", "LICENSE.md"],
}.items():
        archive(deps / name, pin[name]["commit"], stage_dir / name, paths)
    imgui = stage_dir / "rdr/vendor/imgui"
    includes = [stage_dir / p for p in ("src", "panel", "nr", "mfg", "Vulkan-Headers/include", "Streamline-2.12/include", "Detours/src")]
    includes += [imgui, imgui.parent, imgui / "backends", nr_root, stage_dir / "nr-source/external/nvngx_dlss_sdk", stage_dir / "nr-source/external/nlohmann"]
    source_files = sorted((stage_dir / "src").glob("*.cpp"))
    source_files += [stage_dir / "panel/menu.cpp", stage_dir / "panel/menu_vulkan.cpp", stage_dir / "nr/bridge.cpp"]
    source_files += [imgui / f for f in ("imgui.cpp", "imgui_draw.cpp", "imgui_tables.cpp", "imgui_widgets.cpp", "backends/imgui_impl_win32.cpp", "backends/imgui_impl_vulkan.cpp")]
    source_files += nr_cpp
    source_files += [stage_dir / "mfg/component.cpp"]
    for path in [output, vcvars, *source_files, *includes]:
        if any(c in str(path) for c in '\"%\r\n&|<>^'):
            raise ValueError("Build path contains unsupported shell characters")
    inc = " ".join(f'/I"{p}"' for p in includes)
    sources = " ".join(f'"{p}"' for p in source_files)
    detours_lib = stage_dir / "Detours/lib.X64/detours.lib"
    lines = ["@echo off", f'call "{vcvars}" x64 >nul', "if %errorlevel% neq 0 exit /b 1",
             f'cd /d "{stage_dir / "Detours/src"}"', "nmake /nologo > build.log 2>&1", "if %errorlevel% neq 0 goto detours_failed",
             f'cd /d "{output}"',
             # Vulkan backend uses the RDR fork's image-indexed upload buffers.
             f'cl /nologo /std:c++20 /O2 /MT /EHsc /Brepro /DWIN32_LEAN_AND_MEAN /DNOMINMAX /DVK_NO_PROTOTYPES /DIMGUI_IMPL_VULKAN_NO_PROTOTYPES {inc} {sources} /LD /Fe:fgvk.dll /link /Brepro "{detours_lib}" user32.lib gdi32.lib dwmapi.lib imm32.lib version.lib advapi32.lib > compile.log 2>&1',
             "if %errorlevel% neq 0 goto compile_failed",
             f'cl /nologo /std:c++17 /O2 /MT /EHsc /Brepro "{nr_root / "dlssnr/forwarder/dlssnr_forwarder.cpp"}" /LD /Fe:nvngx.dll_dlssnr.dll /link /Brepro d3d12.lib > forwarder.log 2>&1',
             "if %errorlevel% neq 0 goto forwarder_failed",
             f'cl /nologo /std:c++20 /O2 /MT /EHsc {inc} "{stage_dir / "panel/test_state.cpp"}" /Fe:test-panel.exe > tests.log 2>&1',
             "if %errorlevel% neq 0 goto tests_failed", "test-panel.exe", "if %errorlevel% neq 0 exit /b 1",
             f'cl /nologo /std:c++20 /O2 /MT /EHsc /DNOMINMAX {inc} "{stage_dir / "checks/contracts.cpp"}" /Fe:test-contracts.exe >> tests.log 2>&1',
             "if %errorlevel% neq 0 goto tests_failed", "test-contracts.exe", "if %errorlevel% neq 0 exit /b 1",
             f'cl /nologo /std:c++20 /O2 /MT /EHsc /DNOMINMAX {inc} "{stage_dir / "checks/latency_imports.cpp"}" /Fe:test-latency-imports.exe >> tests.log 2>&1',
             "if %errorlevel% neq 0 goto tests_failed", "test-latency-imports.exe", "if %errorlevel% neq 0 exit /b 1",
             f'cl /nologo /std:c++20 /O2 /MT /EHsc /DNOMINMAX /DVK_NO_PROTOTYPES /DIMGUI_IMPL_VULKAN_NO_PROTOTYPES {inc} "{stage_dir / "checks/vulkan_backend.cpp"}" ' + ' '.join(f'"{imgui / f}"' for f in ("imgui.cpp", "imgui_draw.cpp", "imgui_tables.cpp", "imgui_widgets.cpp", "backends/imgui_impl_win32.cpp", "backends/imgui_impl_vulkan.cpp")) + ' /Fe:test-vulkan-backend.exe /link user32.lib gdi32.lib dwmapi.lib imm32.lib >> tests.log 2>&1',
             "if %errorlevel% neq 0 goto tests_failed", "test-vulkan-backend.exe", "if %errorlevel% neq 0 exit /b 1",
             f'cl /nologo /std:c++20 /O2 /MT /EHsc /DNOMINMAX /DVK_NO_PROTOTYPES {inc} "{stage_dir / "checks/panel.cpp"}" "{imgui / "imgui.cpp"}" "{imgui / "imgui_draw.cpp"}" "{imgui / "imgui_tables.cpp"}" "{imgui / "imgui_widgets.cpp"}" /Fe:test-canonical-panel.exe /link user32.lib advapi32.lib >> tests.log 2>&1',
             "if %errorlevel% neq 0 goto tests_failed", "test-canonical-panel.exe", "if %errorlevel% neq 0 exit /b 1",
             f'cl /nologo /std:c++20 /O2 /MT /EHsc /DNOMINMAX {inc} "{stage_dir / "checks/mfg_ui.cpp"}" /Fe:test-mfg-ui.exe /link "{detours_lib}" user32.lib >> tests.log 2>&1',
             "if %errorlevel% neq 0 goto tests_failed",
             "exit /b 0",
             ":detours_failed", "type build.log", "exit /b 1",
             ":compile_failed", "type compile.log", "exit /b 1",
             ":forwarder_failed", "type forwarder.log", "exit /b 1", ":tests_failed", "type tests.log", "exit /b 1"]
    (output / "build.cmd").write_text("\n".join(lines) + "\n")
    receipt = {"schema": 1, "provider": manifest["id"], "dependencies": pin, "source": {}}
    for path in sorted(stage_dir.rglob("*")):
        if path.is_file():
            receipt["source"][path.relative_to(stage_dir).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "source-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"output": str(output), "sources": len(source_files), "dispatch_functions": len(functions)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vcvars", type=Path, required=True)
    args = parser.parse_args()
    stage(args.dependencies, args.output, args.vcvars)
