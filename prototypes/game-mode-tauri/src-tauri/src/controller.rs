use sdl3::{gamepad::{Axis, Button, Gamepad}, joystick::JoystickId, EventPump, GamepadSubsystem};
use serde_json::{json, Value};
use std::{cell::RefCell, collections::BTreeMap, sync::{Arc, atomic::{AtomicBool, Ordering}}, time::{Duration, Instant}};
use tauri::{AppHandle, Emitter, Manager};

#[derive(Default)]
pub struct ControllerState {
    focused: AtomicBool,
    started: AtomicBool,
    has_pads: AtomicBool,
}

impl ControllerState {
    pub fn focus(&self, focused: bool) { self.focused.store(focused, Ordering::Relaxed); }
}

struct Input {
    events: EventPump,
    subsystem: GamepadSubsystem,
    pads: BTreeMap<JoystickId, Gamepad>,
    next_scan: Instant,
    last: Value,
    neutral_required: bool,
}

thread_local! { static INPUT: RefCell<Option<Input>> = const { RefCell::new(None) }; }

impl Input {
    fn new() -> Result<Self, String> {
        // SDL owns no window here. Tauri gates dispatch on its own foreground state.
        sdl3::hint::set("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
        let sdl = sdl3::init().map_err(|e| e.to_string())?;
        Ok(Self {
            events: sdl.event_pump().map_err(|e| e.to_string())?,
            subsystem: sdl.gamepad().map_err(|e| e.to_string())?,
            pads: BTreeMap::new(),
            next_scan: Instant::now(),
            last: Value::Null,
            neutral_required: true,
        })
    }

    fn tick(&mut self, app: &AppHandle) {
        let focused = app.state::<ControllerState>().focused.load(Ordering::Relaxed);
        if !focused {
            self.neutral_required = true;
            self.publish(app, json!([]));
            return;
        }
        // Pump on the UI thread as required by SDL. Drain events and sample the latest
        // state; browser and native input use the same positional button indices.
        for _ in self.events.poll_iter() {}
        self.pads.retain(|_, pad| pad.connected());
        if Instant::now() >= self.next_scan {
            if let Ok(ids) = self.subsystem.gamepads() {
                for id in ids {
                    if let std::collections::btree_map::Entry::Vacant(slot) = self.pads.entry(id) {
                        if let Ok(pad) = self.subsystem.open(id) { slot.insert(pad); }
                    }
                }
            }
            self.next_scan = Instant::now() + Duration::from_millis(350);
        }
        app.state::<ControllerState>().has_pads.store(!self.pads.is_empty(), Ordering::Relaxed);
        let mut neutral = true;
        let pads = self.pads.iter().map(|(id, pad)| {
            let (axes, buttons) = sample(pad);
            neutral &= !buttons.iter().any(|&pressed| pressed) && axes.iter().all(|value| value.abs() < 0.22);
            json!({"index":id.raw(),"id":pad.name().unwrap_or_else(|| "Gamepad".into()),"axes":axes,"buttons":buttons})
        }).collect::<Vec<_>>();
        if self.neutral_required {
            if !neutral { return; }
            self.neutral_required = false;
        }
        self.publish(app, Value::Array(pads));
    }

    fn publish(&mut self, app: &AppHandle, value: Value) {
        if self.last != value {
            let _ = app.emit_to("main", "native-controller-state", &value);
            self.last = value;
        }
    }
}

#[tauri::command]
pub async fn start_native_controller(app: AppHandle) -> Result<(), String> {
    let (tx, rx) = tauri::async_runtime::channel(1);
    let handle = app.clone();
    app.run_on_main_thread(move || {
        let state = handle.state::<ControllerState>();
        let result = INPUT.with(|cell| {
            if cell.borrow().is_none() { cell.replace(Some(Input::new()?)); }
            Ok(())
        });
        if result.is_ok() && !state.started.swap(true, Ordering::Relaxed) {
            let window_focused = handle.get_webview_window("main").and_then(|window| window.is_focused().ok()).unwrap_or(false);
            state.focus(window_focused);
            let app = handle.clone();
            std::thread::spawn(move || {
                let scheduled = Arc::new(AtomicBool::new(false));
                loop {
                    let focused = app.state::<ControllerState>().focused.load(Ordering::Relaxed);
                    if !scheduled.swap(true, Ordering::Relaxed) {
                        let handle = app.clone();
                        let pending = scheduled.clone();
                        if app.run_on_main_thread(move || {
                            INPUT.with(|cell| { if let Some(input) = cell.borrow_mut().as_mut() { input.tick(&handle); } });
                            pending.store(false, Ordering::Relaxed);
                        }).is_err() { break; }
                    }
                    std::thread::sleep(Duration::from_millis(if !focused { 200 } else if app.state::<ControllerState>().has_pads.load(Ordering::Relaxed) { 12 } else { 100 }));
                }
            });
        }
        let _ = tx.try_send(result);
    }).map_err(|e| e.to_string())?;
    let mut rx = rx;
    rx.recv().await.ok_or_else(|| "Controller initialization stopped".to_owned())?
}

fn sample(pad: &Gamepad) -> ([f32; 4], [bool; 16]) {
    let mut buttons = [false; 16];
    for (slot, button) in [(0, Button::South), (1, Button::East), (4, Button::LeftShoulder),
        (5, Button::RightShoulder), (12, Button::DPadUp), (13, Button::DPadDown),
        (14, Button::DPadLeft), (15, Button::DPadRight)] {
        buttons[slot] = pad.button(button);
    }
    let axes = [Axis::LeftX, Axis::LeftY, Axis::RightX, Axis::RightY]
        .map(|axis| (f32::from(pad.axis(axis)) / 32768.0 * 256.0).round() / 256.0);
    (axes, buttons)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sdl3::joystick::{JoystickType, VirtualJoystickDescription};

    #[test]
    fn virtual_pad_preserves_right_stick_and_dpad_independently() {
        sdl3::hint::set("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
        let sdl = sdl3::init().unwrap();
        let joysticks = sdl.joystick().unwrap();
        let gamepads = sdl.gamepad().unwrap();
        let mut events = sdl.event_pump().unwrap();
        let virtual_pad = joysticks.attach_virtual_joystick(VirtualJoystickDescription::new()
            .name("rtxForge input test").joystick_type(JoystickType::Gamepad)
            .with_axes([Axis::LeftX, Axis::LeftY, Axis::RightX, Axis::RightY])
            .with_button(Button::South).with_button(Button::DPadRight)).unwrap();
        let id = virtual_pad.id();
        let joystick = joysticks.open(id).unwrap();
        let pad = gamepads.open(id).unwrap();
        joystick.set_virtual_axis(Axis::RightY as u32, 24576).unwrap();
        // SDL packs the enabled virtual buttons: South is 0, D-pad Right is 1.
        joystick.set_virtual_button(1, true).unwrap();
        events.pump_events();
        let (axes, buttons) = sample(&pad);
        assert_eq!(axes, [0.0, 0.0, 0.0, 0.75]);
        assert!(buttons[15]);
        assert!(!buttons[0]);
        drop(virtual_pad);
        events.pump_events();
        assert!(!pad.connected());
    }
}
