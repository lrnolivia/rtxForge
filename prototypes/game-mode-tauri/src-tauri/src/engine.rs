use std::{collections::HashMap, io::{BufRead, BufReader, Write}, process::{Child, ChildStdin, Command, Stdio}, sync::{Arc, Mutex, mpsc, atomic::{AtomicBool, Ordering}}, time::Duration};
use tauri::Emitter;

type Reply = Result<serde_json::Value, String>;
type Pending = Arc<Mutex<HashMap<String, mpsc::Sender<Reply>>>>;
pub struct Session { _child: Mutex<Child>, input: Mutex<ChildStdin>, pending: Pending, alive: Arc<AtomicBool> }
#[derive(Default)]
pub struct EngineState { session: Mutex<Option<Arc<Session>>> }

pub fn enabled() -> bool { std::env::var("RTXFORGE_PREVIEW_READ_ONLY").as_deref() != Ok("1") && std::env::var("RTXFORGE_ENGINE_BRIDGE").as_deref() == Ok("1") }
#[tauri::command]
pub fn engine_status() -> serde_json::Value {
    serde_json::json!({"enabled": enabled(), "reason": if enabled() { "Reviewed operations are available." } else { "Read-only preview. Game, Steam and shared settings actions are disabled." }})
}

fn session(app: &tauri::AppHandle, state: &EngineState) -> Result<Arc<Session>, String> {
    let mut current = state.session.lock().map_err(|_| "Engine session lock failed.")?;
    if let Some(found) = current.as_ref() { if found.alive.load(Ordering::Relaxed) { return Ok(found.clone()); } }
    let reader = crate::runtime::bridge(app, "engine_host.py")?;
    let python = crate::runtime::python();
    let mut command = Command::new(python);
    command.env("RTXFORGE_ROOT", crate::runtime::root()).arg("-u").arg("-B").arg(reader).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
    #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(0x08000000); }
    let mut child = command.spawn().map_err(|_| "Could not start Python for the reviewed host.")?;
    let input = child.stdin.take().ok_or("Host input is unavailable.")?;
    let output = child.stdout.take().ok_or("Host output is unavailable.")?;
    let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
    let alive = Arc::new(AtomicBool::new(true));
    let reader_alive = alive.clone();
    let reader_pending = pending.clone(); let emitter = app.clone();
    std::thread::spawn(move || {
        for line in BufReader::new(output).lines().map_while(Result::ok) {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&line) {
                if value.get("event").is_some() { let _ = emitter.emit("engine-progress", &value); }
                else if let Some(id) = value.get("id").and_then(|id| id.as_str()) {
                    if let Ok(mut requests) = reader_pending.lock() {
                        if let Some(reply) = requests.remove(id) {
                            let result = if let Some(error) = value.get("error") { Err(error.as_str().unwrap_or("Engine operation failed.").to_string()) } else { Ok(value.get("result").cloned().unwrap_or(serde_json::Value::Null)) };
                            let _ = reply.send(result);
                        }
                    }
                }
            }
        }
        reader_alive.store(false, Ordering::Relaxed);
        if let Ok(mut requests) = reader_pending.lock() { for (_, reply) in requests.drain() { let _ = reply.send(Err("The reviewed host stopped. Review again before retrying.".into())); } }
    });
    let result = Arc::new(Session { _child: Mutex::new(child), input: Mutex::new(input), pending, alive });
    *current = Some(result.clone()); Ok(result)
}

#[tauri::command]
pub async fn engine_request(app: tauri::AppHandle, state: tauri::State<'_, EngineState>, method: String, params: serde_json::Value, id: String) -> Reply {
    if !enabled() { return Err("The reviewed host adapter is disabled. Library and appearance remain available.".into()); }
    let allowed = ["hello", "hardware", "scan", "prepare", "execute", "cancel", "discard_operation", "prepare_dlss", "update_dlss", "packages", "extras_list", "extra_review", "extra_restore_review", "run", "discard", "steam_status", "steam_review", "steam_install", "steam_remove", "recoveries", "recovery_review", "diagnose", "dlss_inventory", "dlss_restore_review", "launch_game", "settings_get", "settings_review", "notes_save"];
    let additional = ["package_inspect", "package_use", "scan_game", "test_start", "test_finish", "hdr_status", "hdr_review", "notes_get", "report_draft", "report_preview", "global_review", "overlay_ui_review", "overlay_package_review", "storage_inventory", "storage_review", "update_check", "executable_review", "sgdb_status", "sgdb_connect", "sgdb_disconnect", "sgdb_search", "sgdb_artwork", "sgdb_download", "art_store", "art_reset", "art_sync_review", "art_profiles", "art_set_profile", "media", "feeder_storage", "cleanup_review", "open_game_folder"];
    if !allowed.contains(&method.as_str()) && !additional.contains(&method.as_str()) && !["prepare_routes", "execute_routes", "cancel_routes", "discard_routes"].contains(&method.as_str()) { return Err("Unsupported engine method.".into()); }
    if method == "update_dlss" && params.get("token").is_none() { return Err("A fresh exact review token is required.".into()); }
    let session = session(&app, &state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let (sender, receiver) = mpsc::channel();
        { let mut requests = session.pending.lock().map_err(|_| "Engine request lock failed.")?;
          if requests.contains_key(&id) { return Err("Duplicate engine request.".into()); } requests.insert(id.clone(), sender); }
        let message = serde_json::json!({"id": id, "method": method, "params": params});
        let written = session.input.lock().map_err(|_| "Engine input lock failed.").and_then(|mut input| writeln!(input, "{}", message).map_err(|_| "The reviewed host disconnected."));
        if let Err(error) = written { if let Ok(mut requests) = session.pending.lock() { requests.remove(&id); } return Err(error.into()); }
        match receiver.recv_timeout(Duration::from_secs(1800)) {
            Ok(result) => result,
            Err(_) => { if let Ok(mut requests) = session.pending.lock() { requests.remove(&id); } Err("The host is still working or disconnected. Check its state before retrying.".to_string()) }
        }
    }).await.map_err(|_| "The engine request stopped unexpectedly.".to_string())?
}
