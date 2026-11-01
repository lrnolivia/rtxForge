use std::{ffi::OsString, path::PathBuf};
use tauri::Manager;

fn installed_dir() -> Option<PathBuf> {
    std::env::current_exe().ok()?.parent().map(|path| path.to_path_buf())
}

pub fn root() -> PathBuf {
    if let Some(root) = std::env::var_os("RTXFORGE_ROOT") { return root.into(); }
    if let Some(dir) = installed_dir() {
        let root = dir.join("engine");
        if root.join("scripts/discovery.py").is_file() { return root; }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).ancestors().nth(3).unwrap().to_path_buf()
}

pub fn python() -> OsString {
    if let Some(python) = std::env::var_os("RTXFORGE_PYTHON") { return python; }
    if let Some(dir) = installed_dir() {
        let python = dir.join(if cfg!(windows) { "python/python.exe" } else { "python/bin/python3" });
        if python.is_file() { return python.into_os_string(); }
    }
    if cfg!(windows) { "python" } else { "python3" }.into()
}

pub fn bridge(app: &tauri::AppHandle, name: &str) -> Result<PathBuf, String> {
    // Call sites pass fixed filenames; web content never chooses a script.
    if let Some(dir) = installed_dir() {
        let path = dir.join("bridge").join(name);
        if path.is_file() { return Ok(path); }
    }
    let development = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../bridge").join(name);
    if development.is_file() { return Ok(development); }
    Ok(app.path().resource_dir().map_err(|_| "Application resources are unavailable.")?.join("bridge").join(name))
}
