# Native NR and Ada MFG under Proton: prerequisites

Status: detection and gating are implemented and fixture-tested
(`scripts/proton_stack.py`, `scripts/proton_mfg.py`, `tests/linux_runtime/`). **No Linux
NR or MFG runtime result exists yet.** Windows evidence (RTX 4070, Halo and CONTROL
Resonant, `providers/mfg-unlocker/source.json`) is not Linux proof.

## What the in-game stack needs under Proton

| Piece | Where it comes from on Linux | How rtxForge checks it (read-only) | Reason code |
|---|---|---|---|
| NVIDIA driver with DLSS Frame Generation under Proton | Host driver, 570 series or newer | `/proc/driver/nvidia/version` | `nvidia-driver-missing`, `nvidia-driver-old` |
| RTX GPU; Ada for MFG | Host | `/proc/driver/nvidia/gpus/*/information` model name | `gpu-not-rtx`, `mfg-gpu-unverified-linux` |
| NGX core (`nvngx.dll`, `_nvngx.dll`) | Driver's Wine folder (`/usr/lib64/nvidia/wine`), copied into `pfx/drive_c/windows/system32` by Proton on each run | Both the driver folder and the prefix copies | `driver-ngx-missing`, `ngx-not-in-prefix` |
| D3D12 → Vulkan | vkd3d-proton in the Proton build the game last ran (`compatdata/<appid>/config_info` line 3 → `lib/wine/vkd3d-proton`) | DLLs plus `version` file | `vkd3d-missing`, `vkd3d-disabled` (`PROTON_NO_D3D12`, `PROTON_USE_WINED3D`) |
| NVAPI (DLSS and Reflex entry points) | dxvk-nvapi in the same build. Proton copies `nvapi64.dll` into the prefix when NVAPI is on, and deletes it when off (`PROTON_DISABLE_NVAPI`, or Proton's per-title list) | Tool DLLs, launch environment and the prefix copy from the last run | `nvapi-missing`, `nvapi-disabled`, `nvapi-not-in-prefix` |
| Game-native Streamline DLSS-G | The game | Library scan flag `native_dlssg` | `native-dlssg-missing` |
| Skynizz bridge, OptiScaler 10, private Streamline/NGX DLLs | rtxForge payload (same bytes as Windows) | Pinned hashes at install | — |
| Universal MFG Unlocker 1.6.1 | `OptiScaler/plugins/MFGUnlocker.asi`, `[Plugins] LoadAsiPlugins=true` | Pinned DLL SHA-256 `24e3e6a8…6b33`; `proton_mfg.verify()` after install | `plugin-missing`, `plugin-changed`, `plugin-not-loaded`, `competing-unlock(-ini)` |
| Proxy loading | `WINEDLLOVERRIDES="dxgi=n,b"` in Steam launch options when Steam is closed, or `pfx/user.reg` `[Software\\Wine\\DllOverrides]` when Steam is open | Written by the engine and restored exactly | — |

rtxForge never sets `PROTON_ENABLE_NVAPI`, `DXVK_NVAPI_*` or CUDA variables. Modern
Proton enables dxvk-nvapi by default, and earlier forced flags hurt compatibility
(`build_launch_options`).

## Gate

A fresh Skynizz install on Linux passes only when all of these hold:

1. **Skynizz on Proton** (experimental) is on.
2. The mode is NR Only, or the MFG component is Universal. The integrated unlock and
   the ReShade MFG Unlock addon are not offered on Linux.
3. Every check above is `ok` for **this** game's prefix.
4. No competing unlock is in the game folder.

The review then says `Experimental under Proton · Linux runtime not yet verified`. The
gate runs again at apply time, so a Proton or driver change since review refuses and
undoes that game. `runtime_verified` stays false until
`linux_runtime.record_runtime_evidence` stores a human-confirmed real session for the
exact game, Proton build, GPU and component.

## Feeder route (ReShade + DLSS5 Feeder/RenoDX)

`proton_stack.feeder_detect` reports DXVK, NVAPI and NGX for DX11 games, but the route
is **not offered** on Linux. ReShade's depth and present behaviour, and the Feeder's NGX
path through DXVK, have not been shown in a moving scene under Proton.
`feeder_provider` keeps refusing Linux installs.

## Verification still needed on this machine (RTX 4070, driver 615.71.09)

A read-only check of one real prefix (BG3, compatdata 1086940, Proton Experimental
11.0-100) returned `prerequisites_met: true`. That only shows the files are present. With
Lauren's go-ahead, and with no game launched otherwise:

1. Install NR + MFG (Universal) from Linux into one test game, with backups. CONTROL
   Resonant is the Windows-verified title.
2. Launch it through Steam with Proton. Read `RTXMFG-Universal.status.json` and the
   `RTXMFG-*.log` (`linux_runtime.mfg_observation`).
3. Confirm 4× presented in game, then record the evidence.
4. Restore from Linux and confirm the original hashes and `user.reg`.
