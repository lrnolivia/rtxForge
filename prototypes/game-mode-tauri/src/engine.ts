export interface EngineStatus { enabled: boolean; reason: string }
export type EngineRow = Record<string, unknown> & { name: string; game: string; installed?: boolean; blocked?: string; exe?: string };
export interface Review {
  token: string; title: string; action?: string; summary?: string; trust?: string; note?: string;
  rows?: Record<string, unknown>[]; items?: Record<string, unknown>[]; blocked?: Record<string, unknown>[]; warnings?: Record<string, unknown>[];
  supported?: {token: string; nr: boolean; mfg: boolean; reason: string; rows: Record<string, unknown>[]}[];
}
export async function engineStatus(): Promise<EngineStatus> {
  if ('__TAURI_INTERNALS__' in window) return (await import('@tauri-apps/api/core')).invoke('engine_status');
  return (await fetch('/api/engine/status')).json();
}
export async function engineRequest<T = unknown>(method: string, params: Record<string, unknown> = {}, progress?: (event: Record<string, unknown>) => void): Promise<T> {
  const id = crypto.randomUUID();
  let close = () => {};
  if (progress) {
    if ('__TAURI_INTERNALS__' in window) {
      close = await (await import('@tauri-apps/api/event')).listen<Record<string, unknown>>('engine-progress', event => { if (String(event.payload.id) === id) progress(event.payload); });
    } else {
      const events = new EventSource('/api/engine/events');
      events.onmessage = event => { const data = JSON.parse(event.data); if (String(data.id) === id) progress(data); };
      close = () => events.close();
      await new Promise<void>(resolve => { events.onopen = () => resolve(); events.onerror = () => resolve(); });
    }
  }
  try {
    if ('__TAURI_INTERNALS__' in window) return await (await import('@tauri-apps/api/core')).invoke<T>('engine_request', { method, params, id });
    const response = await fetch('/api/engine', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ method, params, id }) });
    const value = await response.json();
    if (!response.ok || value.error) throw new Error(value.error || 'The reviewed host could not complete this request.');
    return value.result as T;
  } finally { close(); }
}
