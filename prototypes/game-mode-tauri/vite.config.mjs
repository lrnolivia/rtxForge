import { defineConfig } from 'vite';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { EngineClient } from './bridge/engine-client.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
export function collectSnapshot(extra = []) {
  return new Promise((resolve, reject) => {
    const executable = process.env.RTXFORGE_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    const child = spawn(executable, ['-B', path.join(root, 'bridge/read_snapshot.py'), '--root', path.resolve(root, '../..'), ...extra], {
      windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    const timeout = setTimeout(() => { child.kill(); reject(new Error('The library reader timed out. Try refreshing.')); }, 20000);
    timeout.unref();
    let data = '', errors = '';
    child.stdout.on('data', chunk => {
      data += chunk;
      if (data.length > 16 * 1024 * 1024) child.kill();
    });
    child.stderr.on('data', chunk => { errors = (errors + chunk).slice(-2000); });
    child.on('error', () => { clearTimeout(timeout); reject(new Error('Python is unavailable. Set RTXFORGE_PYTHON to a Python 3.11+ executable and restart this preview.')); });
    child.on('close', code => {
      clearTimeout(timeout);
      if (code !== 0) return reject(new Error(errors || 'Library reader could not complete.'));
      try { resolve(JSON.parse(data)); } catch { reject(new Error('Library reader returned an invalid snapshot.')); }
    });
  });
}
function bridge() {
  const engine = new EngineClient();
  const middleware = (server) => { server.middlewares.use(async (req, res, next) => {
    if (req.url === '/api/engine/status') { res.setHeader('Content-Type', 'application/json'); return res.end(JSON.stringify(engine.status())); }
    if (req.url === '/api/engine/events') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'keep-alive' });
      res.write(': engine progress\n\n');
      const listener = message => res.write(`data: ${JSON.stringify(message)}\n\n`);
      engine.on('progress', listener); req.on('close', () => engine.off('progress', listener)); return;
    }
    if (req.url === '/api/engine') {
      res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store');
      if (req.method !== 'POST' || req.headers.origin !== 'http://127.0.0.1:1420' || !req.headers['content-type']?.startsWith('application/json')) {
        res.statusCode = 403; return res.end(JSON.stringify({ error: 'Use the local application’s reviewed operation flow.' }));
      }
      try {
        let body = '';
        for await (const chunk of req) { body += chunk; if (body.length > 4 * 1024 * 1024) throw new Error('Engine request exceeds its limit.'); }
        const { method, params, id } = JSON.parse(body);
        res.end(JSON.stringify({ result: await engine.request(method, params || {}, id) }));
      } catch (error) { res.statusCode = 400; res.end(JSON.stringify({ error: error.message })); }
      return;
    }
    if (req.url?.split('?')[0] === '/api/artwork') {
      res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');
      const query=new URL(req.url,'http://127.0.0.1:1420').searchParams,id=query.get('id')||'',role=query.get('role')||'';
      if(req.method!=='GET'||id.length>100||!['poster','hero','capsule'].includes(role)){res.statusCode=400;return res.end('{}');}
      try {return res.end(JSON.stringify(await collectSnapshot(['--artwork',id,'--role',role])));}
      catch {res.statusCode=503;return res.end('{}');}
    }
    if (req.url?.split('?')[0] !== '/api/snapshot') return next();
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Cache-Control', 'no-store');
    if (req.method !== 'GET') { res.statusCode = 405; return res.end(JSON.stringify({ error: 'Read-only bridge.' })); }
    try { res.end(JSON.stringify(await collectSnapshot())); }
    catch (error) { res.statusCode = 503; res.end(JSON.stringify({ error: error.message })); }
  }); };
  return { name: 'rtxforge-read-only-bridge', configureServer: middleware, configurePreviewServer: middleware };
}
export default defineConfig({
  clearScreen: false,
  plugins: [bridge()],
  server: { host: '127.0.0.1', port: 1420, strictPort: true, watch: { ignored: ['**/src-tauri/**', '**/.tools/**'] } },
  preview: { host: '127.0.0.1', port: 1420, strictPort: true },
  build: { target: 'es2022' },
});
