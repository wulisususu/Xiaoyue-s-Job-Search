import { describe, expect, it } from 'vitest';

import tauriConf from '../../src-tauri/tauri.conf.json';

interface TauriConf {
  bundle: { active: boolean; targets: string[]; resources: Record<string, string> | string[] };
  app: { security: { csp: string } };
}

const conf = tauriConf as unknown as TauriConf;

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
