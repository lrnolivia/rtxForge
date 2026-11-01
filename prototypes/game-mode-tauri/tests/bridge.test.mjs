import test from 'node:test';
import assert from 'node:assert/strict';
import { collectSnapshot } from '../vite.config.mjs';
import { EngineClient } from '../bridge/engine-client.mjs';

test('missing Python produces a useful bridge error', async () => {
  const saved = process.env.RTXFORGE_PYTHON;
  process.env.RTXFORGE_PYTHON = 'rtxforge-intentionally-missing-python';
  try { await assert.rejects(collectSnapshot(), /Python is unavailable/); }
  finally { if (saved === undefined) delete process.env.RTXFORGE_PYTHON; else process.env.RTXFORGE_PYTHON = saved; }
});

test('read-only preview overrides opt-in and never starts an operation host', async () => {
  const saved = { engine: process.env.RTXFORGE_ENGINE_BRIDGE, readonly: process.env.RTXFORGE_PREVIEW_READ_ONLY };
  process.env.RTXFORGE_ENGINE_BRIDGE = '1'; process.env.RTXFORGE_PREVIEW_READ_ONLY = '1';
  try {
    const engine = new EngineClient();
    assert.equal(engine.status().enabled, false);
    await assert.rejects(engine.request('execute', { token: 'untrusted' }, 'readonly-check'), /Read-only preview/);
    assert.equal(engine.child, undefined);
  } finally {
    for (const [key, value] of [['RTXFORGE_ENGINE_BRIDGE', saved.engine], ['RTXFORGE_PREVIEW_READ_ONLY', saved.readonly]]) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
});
