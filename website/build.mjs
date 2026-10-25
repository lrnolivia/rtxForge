import { cp, mkdir, rm } from 'node:fs/promises';
import { basename } from 'node:path';

// Mirror the public URL path in the static output; public/ remains the editable source.
const output = new URL('./.site/', import.meta.url);
await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(new URL('./public/', import.meta.url), new URL('rtxforge/', output), {
  recursive: true, filter: source => basename(source) !== '_headers'
});
await cp(new URL('./public/_headers', import.meta.url), new URL('_headers', output));
