"""Process checks the Flatpak runs on the host (flatpak_host.probe).

Started as ``python3 -I -B host_probe.py <query> [args]`` by flatpak-spawn
--host, so it reads the host's real /proc with the very same functions the
AppImage uses. Prints one JSON line: {"ok": true, "result": ...}. Queries are a
fixed list; nothing here writes.
"""
from pathlib import Path
import importlib.util
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
# -I leaves the script's directory off sys.path.
sys.path.insert(0, str(ROOT / 'scripts'))


def engine():
    spec = importlib.util.spec_from_file_location('rtxengine_probe', ROOT / 'engine/rtxengine.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prefix_in_use(prefix):
    import proton_prefix
    return proton_prefix.prefix_in_use(prefix)


def processes_under_root(root):
    return engine()._running_processes_under_root(Path(root))


def steam_processes():
    return engine()._steam_process_names()


def protected_running():
    import offline_routes
    return offline_routes.protected_running()


def mapped_process(prefix, exe, channel):
    import linux_overlay_host
    return linux_overlay_host.mapped_process(prefix, exe, channel)


def exe_processes():
    import linux_overlay_host
    return linux_overlay_host.exe_processes()


QUERIES = {
    'prefix-in-use': prefix_in_use,
    'processes-under-root': processes_under_root,
    'steam-processes': steam_processes,
    'protected-running': protected_running,
    'mapped-process': mapped_process,
    'exe-processes': exe_processes,
}


def main(argv):
    if os.path.exists('/.flatpak-info'):
        # Run inside the sandbox this would answer from the wrong /proc.
        answer = {'ok': False, 'error': 'host_probe.py must run on the host'}
    elif not argv or argv[0] not in QUERIES:
        answer = {'ok': False, 'error': 'unknown query'}
    else:
        try:
            answer = {'ok': True, 'result': QUERIES[argv[0]](*argv[1:])}
        except Exception as error:  # Reported to the sandbox, which refuses.
            answer = {'ok': False, 'error': f'{type(error).__name__}: {error}'}
    print(json.dumps(answer))
    return 0 if answer['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
