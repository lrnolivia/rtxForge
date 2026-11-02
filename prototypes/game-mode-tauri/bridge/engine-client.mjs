import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { EventEmitter } from 'node:events';

export const allowedMethods = new Set(['hello', 'hardware', 'scan', 'prepare', 'execute', 'cancel', 'discard_operation', 'prepare_dlss', 'update_dlss', 'packages', 'extras_list', 'extra_review', 'extra_restore_review', 'run', 'discard', 'steam_status', 'steam_review', 'steam_install', 'steam_remove', 'recoveries', 'recovery_review', 'diagnose', 'dlss_inventory', 'dlss_restore_review']);
['launch_game', 'settings_get', 'settings_review', 'notes_save'].forEach(method => allowedMethods.add(method));
['package_inspect', 'package_use'].forEach(method => allowedMethods.add(method));
allowedMethods.add('scan_game');
['test_start', 'test_finish', 'hdr_status', 'hdr_review'].forEach(method => allowedMethods.add(method));
['notes_get', 'report_draft', 'report_preview'].forEach(method => allowedMethods.add(method));
['global_review', 'overlay_ui_review', 'overlay_package_review', 'storage_inventory', 'storage_review', 'update_check'].forEach(method => allowedMethods.add(method));
allowedMethods.add('executable_review');
['sgdb_status', 'sgdb_connect', 'sgdb_disconnect', 'sgdb_search', 'sgdb_artwork', 'sgdb_download', 'art_store', 'art_reset', 'art_sync_review', 'art_profiles', 'art_set_profile', 'media', 'feeder_storage'].forEach(method => allowedMethods.add(method));
['prepare_routes', 'execute_routes', 'cancel_routes', 'discard_routes'].forEach(method => allowedMethods.add(method));
allowedMethods.add('cleanup_review');
allowedMethods.add('open_game_folder');
const root = path.dirname(fileURLToPath(import.meta.url));
export class EngineClient extends EventEmitter {
  child;
  pending = new Map();
  status() {
    const enabled = process.env.RTXFORGE_PREVIEW_READ_ONLY !== '1' && process.env.RTXFORGE_ENGINE_BRIDGE === '1';
    return { enabled, reason: enabled ? 'Reviewed operations are available.' : 'Read-only preview. Game, Steam and shared settings actions are disabled.' };
  }
  start() {
    if (this.child) return;
    const python = process.env.RTXFORGE_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    this.child = spawn(python, ['-u', '-B', path.join(root, 'engine_host.py')], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    createInterface({ input: this.child.stdout }).on('line', line => {
      try {
        const message = JSON.parse(line);
        if (message.event) this.emit('progress', message);
        else if (this.pending.has(String(message.id))) {
          const { resolve, reject, timer } = this.pending.get(String(message.id));
          clearTimeout(timer); this.pending.delete(String(message.id));
          if (message.error) reject(new Error(message.error)); else resolve(message.result);
        }
      } catch { /* Non-protocol output cannot be used as operation evidence. */ }
    });
    this.child.stderr.resume();
    const stopped = () => {
      for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(new Error('The reviewed host stopped. Reconnect and review again.')); }
      this.pending.clear(); this.child = null;
    };
    this.child.once('error', stopped); this.child.once('close', stopped);
  }
  request(method, params, id) {
    if (!this.status().enabled) return Promise.reject(new Error(this.status().reason));
    if (!allowedMethods.has(method)) return Promise.reject(new Error('Unsupported engine method.'));
    if (!id || this.pending.has(id)) return Promise.reject(new Error('A unique request ID is required.'));
    this.start();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('The host is still working or disconnected. Check the existing app before retrying an operation.')); }, 30 * 60 * 1000);
      timer.unref();
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(JSON.stringify({ id, method, params }) + '\n', error => {
        if (error) { clearTimeout(timer); this.pending.delete(id); reject(new Error('The reviewed host could not accept this request.')); }
      });
    });
  }
}
