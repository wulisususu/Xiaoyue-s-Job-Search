import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

interface TauriConf {
  bundle: { active: boolean; targets: string[]; resources: Record<string, string> | string[] };
  app: { security: { csp: string } };
}

// vitest runs with cwd = apps/desktop; src-tauri lives next to it.
const confPath = resolve(process.cwd(), 'src-tauri/tauri.conf.json');
const conf: TauriConf = JSON.parse(readFileSync(confPath, 'utf-8'));

describe('tauri.conf.json (packaging contract)', () => {
  it('bundles with NSIS and carries the PyInstaller onedir output', () => {
    expect(conf.bundle.active).toBe(true);
    expect(conf.bundle.targets).toContain('nsis');
    const resources = Array.isArray(conf.bundle.resources) ? {} : conf.bundle.resources;
    expect(resources['../../services/core-api/dist/xiaoyue-core-api']).toBe('core-api/');
  });

  it('allows the webview to reach any loopback port (dynamic sidecar port)', () => {
    expect(conf.app.security.csp).toMatch(/connect-src[^;]*http:\/\/127\.0\.0\.1:\*/);
  });
});
