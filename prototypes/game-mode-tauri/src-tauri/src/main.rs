#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{path::PathBuf, process::Command};
use tauri_plugin_dialog::DialogExt;
mod engine;
mod runtime;

#[tauri::command]
fn exit_app(app: tauri::AppHandle) { app.exit(0); }

#[tauri::command]
fn desktop_mode(app: tauri::AppHandle) -> Result<(), String> {
    let mut candidates = Vec::new();
    #[cfg(windows)] {
        if let Some(base) = std::env::var_os("LOCALAPPDATA") {
            candidates.push(PathBuf::from(base).join("Programs/rtxForge/rtxForge.exe"));
        }
        for key in ["ProgramFiles", "ProgramW6432"] {
            if let Some(base) = std::env::var_os(key) {
                candidates.push(PathBuf::from(base).join("rtxForge/rtxForge.exe"));
            }
        }
    }
    #[cfg(not(windows))] {
        if let Some(paths) = std::env::var_os("PATH") {
            candidates.extend(std::env::split_paths(&paths).map(|base| base.join("rtxforge")));
        }
    }
    let executable = candidates.into_iter().find(|path| path.is_file())
        .ok_or("The desktop application is not installed in its standard location.")?;
    Command::new(executable).env_remove("SteamAppId").env_remove("SteamGameId")
        .spawn().map_err(|_| "The desktop application could not be opened.")?;
    app.exit(0);
    Ok(())
}

#[tauri::command]
async fn choose_path(app: tauri::AppHandle, kind: String) -> Result<Option<String>, String> {
    if !engine::enabled() { return Err("Source selection is disabled in this read-only preview.".into()); }
    tauri::async_runtime::spawn_blocking(move || {
        let dialog = app.dialog().file();
        let selected = match kind.as_str() {
            "folder" => dialog.blocking_pick_folder(),
            "package" => dialog.add_filter("Package archive", &["zip", "7z"]).blocking_pick_file(),
            "addon" => dialog.add_filter("ReShade add-on", &["addon64"]).blocking_pick_file(),
            "executable" => dialog.add_filter("Game executable", &["exe"]).blocking_pick_file(),
            "image" => dialog.add_filter("Artwork image", &["png", "jpg", "jpeg"]).blocking_pick_file(),
            "tool" => dialog.blocking_pick_file(),
            _ => return Err("Unsupported file selection.".to_string()),
        };
        selected.map(|path| path.into_path().map(|path| path.to_string_lossy().to_string()).map_err(|_| "This file has no local path.".to_string())).transpose()
    }).await.map_err(|_| "The file picker closed unexpectedly.".to_string())?
}

fn read_snapshot(app: tauri::AppHandle, artwork: Option<(String,String)>) -> Result<serde_json::Value, String> {
    // Fixed reader only. No caller-supplied executable, method or filesystem path.
    let checkout = runtime::root();
    let reader = runtime::bridge(&app, "read_snapshot.py")?;
    let python = runtime::python();
    let mut command = Command::new(python);
    command.arg("-B").arg(reader).arg("--root").arg(checkout);
    if let Some((id,role)) = artwork { command.arg("--artwork").arg(id).arg("--role").arg(role); }
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let output = command.output().map_err(|_| "Python is unavailable. Set RTXFORGE_PYTHON to Python 3.11+ and restart.")?;
    if !output.status.success() { return Err("The local reader could not read the checkout or library. Check RTXFORGE_ROOT and refresh.".into()); }
    if output.stdout.len() > 16 * 1024 * 1024 { return Err("Library snapshot exceeded its display limit.".into()); }
    serde_json::from_slice(&output.stdout).map_err(|_| "The library reader returned an invalid snapshot.".into())
}

#[tauri::command]
async fn snapshot(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || read_snapshot(app,None)).await.map_err(|_| "The library reader stopped unexpectedly.".to_string())?
}

#[tauri::command]
async fn artwork(app: tauri::AppHandle, id: String, role: String) -> Result<serde_json::Value,String> {
    if id.len()>100 || !["poster","hero","capsule"].contains(&role.as_str()) { return Err("Invalid artwork selection.".into()); }
    tauri::async_runtime::spawn_blocking(move || read_snapshot(app,Some((id,role)))).await.map_err(|_| "Artwork reader stopped.".to_string())?
}

fn main() {
    tauri::Builder::default().plugin(tauri_plugin_dialog::init()).manage(engine::EngineState::default()).invoke_handler(tauri::generate_handler![snapshot, artwork, choose_path, desktop_mode, exit_app, engine::engine_status, engine::engine_request])
        .run(tauri::generate_context!()).expect("Could not run the Game Mode prototype");
}
