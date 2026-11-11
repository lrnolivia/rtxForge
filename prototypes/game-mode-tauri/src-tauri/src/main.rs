#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{path::PathBuf, process::{Command, Stdio}, io::Write};
use tauri_plugin_dialog::DialogExt;
use tauri::{Manager, Emitter};
use std::sync::atomic::Ordering;
mod engine;
mod runtime;
mod desktop_parent;
mod controller;

fn appearance_command(app: tauri::AppHandle, value: Option<serde_json::Value>) -> Result<serde_json::Value,String> {
    let root=runtime::root(&app)?;
    let mut command=runtime::python_command(&app)?;
    command.arg("-B").arg(runtime::bridge(&app,"appearance.py")?).arg("--root").arg(root).arg(if value.is_some(){"write"}else{"read"});
    command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(0x08000000); }
    let bytes=value.map(|value|serde_json::to_vec(&value)).transpose().map_err(|_|"Invalid appearance data.")?;
    if bytes.as_ref().is_some_and(|bytes|bytes.len()>2_000_000){return Err("The appearance file is too large.".into());}
    let mut child=command.spawn().map_err(|_|"Appearance storage could not be opened.")?;
    if let Some(mut input)=child.stdin.take(){if let Some(bytes)=bytes {input.write_all(&bytes).map_err(|_|"Appearance could not be saved.")?;}}
    let output=child.wait_with_output().map_err(|_|"Appearance storage stopped unexpectedly.")?;
    if !output.status.success(){return Err("Appearance could not be saved. Your current session preferences are retained.".into());}
    if output.stdout.len()>2_000_000{return Err("Appearance storage exceeded its limit.".into());}
    serde_json::from_slice(&output.stdout).map_err(|_|"Appearance storage returned invalid data.".into())
}

#[cfg(target_os = "windows")]
fn read_system_accent() -> Option<String> {
    use windows::UI::ViewManagement::{UIColorType, UISettings};
    let color = UISettings::new().ok()?.GetColorValue(UIColorType::Accent).ok()?;
    Some(format!("#{:02x}{:02x}{:02x}", color.R, color.G, color.B))
}

#[cfg(target_os = "linux")]
fn read_system_accent() -> Option<String> {
    use gio::{glib::variant::ToVariant, BusType, Cancellable, DBusCallFlags};
    let bus = gio::bus_get_sync(BusType::Session, Cancellable::NONE).ok()?;
    let parameters = ("org.freedesktop.appearance", "accent-color").to_variant();
    let read = |method| {
        bus.call_sync(
            Some("org.freedesktop.portal.Desktop"),
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Settings",
            method, Some(&parameters), None, DBusCallFlags::NONE, 750, Cancellable::NONE,
        )
    };
    let response = read("ReadOne").or_else(|_| read("Read")).ok()?;
    let value = response.child_value(0).as_variant()?;
    let value = value.as_variant().unwrap_or(value);
    let (r, g, b) = value.get::<(f64, f64, f64)>()?;
    let channels = [r, g, b];
    if !channels.iter().all(|channel| (0.0..=1.0).contains(channel)) {
        return None;
    }
    let [r, g, b] = channels.map(|channel| (channel * 255.0).round() as u8);
    Some(format!("#{r:02x}{g:02x}{b:02x}"))
}

#[tauri::command]
async fn system_accent() -> Option<String> {
    #[cfg(any(target_os = "windows", target_os = "linux"))]
    return tauri::async_runtime::spawn_blocking(read_system_accent).await.ok().flatten();
    #[cfg(not(any(target_os = "windows", target_os = "linux")))]
    None
}

#[tauri::command]
async fn appearance_read(app:tauri::AppHandle)->Result<serde_json::Value,String>{
    tauri::async_runtime::spawn_blocking(move||appearance_command(app,None)).await.map_err(|_|"Appearance reader stopped.".to_string())?
}

#[tauri::command]
async fn appearance_write(app:tauri::AppHandle,value:serde_json::Value)->Result<serde_json::Value,String>{
    if preview_view(std::env::args()).is_some() { return Err("Appearance changes stay in this preview.".into()); }
    tauri::async_runtime::spawn_blocking(move||appearance_command(app,Some(value))).await.map_err(|_|"Appearance writer stopped.".to_string())?
}

#[tauri::command]
fn exit_app(app: tauri::AppHandle) { close_safely(&app); }

fn close_safely(app: &tauri::AppHandle) {
    let state = app.state::<engine::EngineState>();
    if state.closing.swap(true, Ordering::SeqCst) { return; }
    let app = app.clone();
    std::thread::spawn(move || {
        engine::drain(&app.state::<engine::EngineState>());
        app.exit(0);
    });
}

#[tauri::command]
fn toggle_fullscreen(window: tauri::Window) -> Result<bool,String> {
    let fullscreen=!window.is_fullscreen().map_err(|e|e.to_string())?;
    window.set_fullscreen(fullscreen).map_err(|e|e.to_string())?;
    Ok(fullscreen)
}

#[tauri::command]
fn minimize_app(window: tauri::Window) -> Result<(),String> { window.minimize().map_err(|e|e.to_string()) }

#[tauri::command]
async fn desktop_mode(app: tauri::AppHandle) -> Result<(), String> {
    if app.state::<desktop_parent::DesktopParent>().0.lock().ok().and_then(|value| *value).is_some_and(desktop_parent::alive) {
        close_safely(&app);
        return Ok(());
    }
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
    let launch = std::env::var("RTXFORGE_DESKTOP_COMMAND").ok()
        .and_then(|raw| serde_json::from_str::<Vec<String>>(&raw).ok())
        .filter(|args| !args.is_empty() && args.len() <= 12 && PathBuf::from(&args[0]).is_absolute() && PathBuf::from(&args[0]).is_file());
    let (executable, arguments) = if let Some(mut args) = launch {
        (PathBuf::from(args.remove(0)), args)
    } else {
        (candidates.into_iter().find(|path| path.is_file())
            .ok_or("The desktop application is not installed in its standard location.")?, vec!["--desktop-mode".into()])
    };
    if app.state::<engine::EngineState>().closing.swap(true, Ordering::SeqCst) {
        return Err("The application is already closing.".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        engine::drain(&app.state::<engine::EngineState>());
        let result = Command::new(executable).args(arguments).env_remove("SteamAppId").env_remove("SteamGameId").spawn();
        if result.is_ok() { app.exit(0); Ok(()) } else {
            let state = app.state::<engine::EngineState>();
            state.drained.store(false, Ordering::SeqCst);
            state.closing.store(false, Ordering::SeqCst);
            Err("The desktop application could not be opened.".to_string())
        }
    }).await.map_err(|_| "Desktop handoff stopped unexpectedly.".to_string())??;
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
            "renodx-addon" => dialog.add_filter("RenoDX add-on", &["addon32", "addon64"]).blocking_pick_file(),
            "addon" => dialog.add_filter("ReShade add-on", &["addon64"]).blocking_pick_file(),
            "executable" => dialog.add_filter("Game executable", &["exe"]).blocking_pick_file(),
            "image" => dialog.add_filter("Artwork image", &["png", "jpg", "jpeg"]).blocking_pick_file(),
            "tool" => dialog.blocking_pick_file(),
            _ => return Err("Unsupported file selection.".to_string()),
        };
        selected.map(|path| path.into_path().map(|path| path.to_string_lossy().to_string()).map_err(|_| "This file has no local path.".to_string())).transpose()
    }).await.map_err(|_| "The file picker closed unexpectedly.".to_string())?
}

fn read_snapshot(app: tauri::AppHandle, artwork: Option<(String,String)>, background: Option<String>, screenshot: Option<String>, gallery: bool) -> Result<serde_json::Value, String> {
    // Fixed reader only. No caller-supplied executable, method or filesystem path.
    let checkout = runtime::root(&app)?;
    let reader = runtime::bridge(&app, "read_snapshot.py")?;
    let mut command = runtime::python_command(&app)?;
    command.arg("-B").arg(reader).arg("--root").arg(checkout);
    if let Some((id,role)) = artwork { command.arg("--artwork").arg(id).arg("--role").arg(role); }
    if let Some(appid) = background { command.arg(if gallery {"--background-list"} else {"--background"}).arg(appid); }
    if let Some(id) = screenshot { command.arg("--screenshot").arg(id); }
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let output = command.output().map_err(|_| "Python is unavailable. Set RTXFORGE_PYTHON to Python 3.11+ and restart.")?;
    if !output.status.success() {
        if std::env::args().any(|arg|arg=="--verify-runtime") {
            eprintln!("Private reader exited {}: {}", output.status, String::from_utf8_lossy(&output.stderr));
        }
        return Err("The local reader could not read the checkout or library. Check RTXFORGE_ROOT and refresh.".into());
    }
    if output.stdout.len() > 16 * 1024 * 1024 { return Err("Library snapshot exceeded its display limit.".into()); }
    serde_json::from_slice(&output.stdout).map_err(|_| "The library reader returned an invalid snapshot.".into())
}

#[tauri::command]
async fn snapshot(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || read_snapshot(app,None,None,None,false)).await.map_err(|_| "The library reader stopped unexpectedly.".to_string())?
}

#[tauri::command]
async fn artwork(app: tauri::AppHandle, id: String, role: String) -> Result<serde_json::Value,String> {
    if id.len()>100 || !["poster","hero","capsule"].contains(&role.as_str()) { return Err("Invalid artwork selection.".into()); }
    tauri::async_runtime::spawn_blocking(move || read_snapshot(app,Some((id,role)),None,None,false)).await.map_err(|_| "Artwork reader stopped.".to_string())?
}

#[tauri::command]
async fn store_background(app: tauri::AppHandle, appid: String, screenshot_id: Option<String>) -> Result<serde_json::Value,String> {
    if appid.is_empty() || appid.len()>10 || !appid.bytes().all(|byte|byte.is_ascii_digit()) { return Err("Invalid Steam application ID.".into()); }
    tauri::async_runtime::spawn_blocking(move || read_snapshot(app,None,Some(appid),screenshot_id,false)).await.map_err(|_| "Store background reader stopped.".to_string())?
}

#[tauri::command]
async fn store_screenshots(app: tauri::AppHandle, appid: String) -> Result<serde_json::Value,String> {
    if appid.is_empty() || appid.len()>10 || !appid.bytes().all(|byte|byte.is_ascii_digit()) { return Err("Invalid Steam application ID.".into()); }
    tauri::async_runtime::spawn_blocking(move || read_snapshot(app,None,Some(appid),None,true)).await.map_err(|_| "Store screenshot list stopped.".to_string())?
}

fn preview_view(args: impl IntoIterator<Item = impl AsRef<str>>) -> Option<&'static str> {
    args.into_iter().find_map(|arg| match arg.as_ref() {
        "--preview-library" => Some("library"),
        "--preview-details" => Some("details"),
        _ => None,
    })
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut context = tauri::generate_context!();
    if preview_view(&args).is_some() {
        let config = context.config_mut();
        config.identifier.push_str(".preview");
        if let Some(window) = config.app.windows.first_mut() {
            window.title = "rtxForge · Game Mode Preview".into();
            window.fullscreen = false;
            window.center = true;
            window.decorations = true;
            window.width = 1440.0;
            window.height = 810.0;
            window.incognito = true;
        }
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            if args.iter().any(|arg|arg=="--desktop-mode") { close_safely(app); return; }
            if args.iter().any(|arg|arg=="--appearance") { let _ = app.emit("navigate-appearance", ()); }
            if let Some(view) = preview_view(&args) { let _ = app.emit("navigate-preview", view); }
            let state = app.state::<desktop_parent::DesktopParent>();
            if let Ok(mut parent) = state.0.lock() {
                if parent.is_none_or(|pid| !desktop_parent::alive(pid)) { *parent = desktop_parent::from_args(&args); }
            }
            if let Some(window) = app.get_webview_window("main") { let _ = window.show(); let _ = window.unminimize(); let _ = window.set_focus(); }
        }))
        .manage(desktop_parent::DesktopParent(std::sync::Mutex::new(desktop_parent::from_args(&args))))
        .manage(controller::ControllerState::default())
        .setup(move |app| {
            if args.iter().any(|arg|arg=="--desktop-mode") {
                close_safely(app.handle());
                return Ok(());
            }
            if args.iter().any(|arg| arg == "--verify-runtime") {
                let app = app.handle().clone();
                std::thread::spawn(move || {
                    let result = read_snapshot(app.clone(), None, None, None, false);
                    engine::drain(&app.state::<engine::EngineState>());
                    match result {
                        Ok(_) => { println!("{{\"runtimeVerified\":true}}"); app.exit(0); },
                        Err(error) => { eprintln!("Private runtime verification failed: {error}"); app.exit(1); }
                    }
                });
            }
            Ok(())
        })
        .plugin(tauri_plugin_dialog::init()).manage(engine::EngineState::default()).invoke_handler(tauri::generate_handler![controller::start_native_controller, appearance_read, appearance_write, system_accent, snapshot, artwork, store_background, store_screenshots, choose_path, desktop_mode, exit_app, toggle_fullscreen, minimize_app, engine::engine_status, engine::engine_request])
        .build(context).expect("Could not build Game Mode")
        .run(|app, event| match event {
            tauri::RunEvent::WindowEvent { event: tauri::WindowEvent::CloseRequested { api, .. }, .. } => {
                api.prevent_close(); close_safely(app);
            },
            tauri::RunEvent::WindowEvent { label, event: tauri::WindowEvent::Focused(focused), .. } if label == "main" => {
                app.state::<controller::ControllerState>().focus(focused);
            },
            tauri::RunEvent::ExitRequested { api, .. } => {
                if !app.state::<engine::EngineState>().drained.load(Ordering::SeqCst) {
                    api.prevent_exit(); close_safely(app);
                }
            },
            _ => ()
        });
}
