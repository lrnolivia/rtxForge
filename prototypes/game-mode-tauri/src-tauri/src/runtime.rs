use std::{ffi::OsString, path::PathBuf};
use tauri::Manager;

fn installed_dir() -> Option<PathBuf> {
    std::env::current_exe().ok()?.parent().map(|path| path.to_path_buf())
}

fn validate_root(root: PathBuf) -> Result<PathBuf, String> {
    for file in ["scripts/discovery.py", "scripts/desktop_service.py", "engine/rtxengine.py", "provider.json", "windows/engine-host/rtxforge_win_host.py"] {
        if !root.join(file).is_file() { return Err(format!("The installed engine is incomplete: {file}. Reinstall the complete application.")); }
    }
    Ok(root)
}

pub fn root() -> Result<PathBuf, String> {
    if let Some(root) = std::env::var_os("RTXFORGE_ROOT") { return validate_root(root.into()); }
    if let Some(dir) = installed_dir() {
        let root = dir.join("engine");
        if root.is_dir() { return validate_root(root); }
    }
    #[cfg(debug_assertions)]
    { return validate_root(PathBuf::from(env!("CARGO_MANIFEST_DIR")).ancestors().nth(3).unwrap().to_path_buf()); }
    #[cfg(not(debug_assertions))]
    Err("The private engine is missing. Reinstall the complete application.".into())
}

pub fn python() -> Result<OsString, String> {
    if let Some(python) = std::env::var_os("RTXFORGE_PYTHON") {
        return if PathBuf::from(&python).is_file() { Ok(python) } else { Err("The selected Python executable is missing.".into()) };
    }
    if let Some(dir) = installed_dir() {
        let python = dir.join(if cfg!(windows) { "python/python.exe" } else { "python/bin/python3" });
        if python.is_file() { return Ok(python.into_os_string()); }
    }
    #[cfg(debug_assertions)]
    { return Ok(if cfg!(windows) { "python" } else { "python3" }.into()); }
    #[cfg(not(debug_assertions))]
    Err("The private Python runtime is missing. Reinstall the complete application.".into())
}

pub fn bridge(app: &tauri::AppHandle, name: &str) -> Result<PathBuf, String> {
    // Call sites pass fixed filenames; web content never chooses a script.
    if let Some(dir) = installed_dir() {
        let path = dir.join("bridge").join(name);
        if path.is_file() { return Ok(path); }
    }
    let resource = app.path().resource_dir().map_err(|_| "Application resources are unavailable.")?.join("bridge").join(name);
    if resource.is_file() { return Ok(resource); }
    #[cfg(debug_assertions)] {
        let development = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../bridge").join(name);
        if development.is_file() { return Ok(development); }
    }
    Err(format!("The installed adapter is missing: {name}. Reinstall the complete application."))
}
