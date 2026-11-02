use std::sync::Mutex;

pub struct DesktopParent(pub Mutex<Option<u32>>);

pub fn from_args(args: &[String]) -> Option<u32> {
    args.windows(2).find(|pair| pair[0] == "--desktop-parent")
        .and_then(|pair| pair[1].parse::<u32>().ok())
        .filter(|pid| *pid != 0 && *pid != std::process::id())
}

pub fn alive(pid: u32) -> bool {
    #[cfg(windows)] {
        #[link(name = "kernel32")]
        extern "system" {
            fn OpenProcess(access: u32, inherit: i32, pid: u32) -> *mut std::ffi::c_void;
            fn GetExitCodeProcess(handle: *mut std::ffi::c_void, code: *mut u32) -> i32;
            fn CloseHandle(handle: *mut std::ffi::c_void) -> i32;
        }
        unsafe {
            let handle = OpenProcess(0x1000, 0, pid);
            if handle.is_null() { return false; }
            let mut code = 0;
            let running = GetExitCodeProcess(handle, &mut code) != 0 && code == 259;
            CloseHandle(handle);
            running
        }
    }
    #[cfg(not(windows))] { std::path::Path::new("/proc").join(pid.to_string()).exists() }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn explicit_parent_only() {
        assert_eq!(from_args(&["app".into(), "--desktop-parent".into(), "123".into()]), Some(123));
        for value in ["0", "bad", "-1"] {
            assert_eq!(from_args(&["--desktop-parent".into(), value.into()]), None);
        }
        assert!(alive(std::process::id()));
    }
}
