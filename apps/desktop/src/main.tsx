import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './app/App';
import './styles/global.css';

/** In the packaged desktop app, ask the Tauri shell where the core-api
 *  sidecar listens and which per-launch session token to use. In dev
 *  (`npm run dev` + scripts/dev.ps1) the invoke fails and we keep the
 *  default http://127.0.0.1:8765 endpoint without a token. */
async function discoverCore(): Promise<void> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    const runtime = await invoke<{ base_url: string; session_token: string } | null>(
      'core_endpoint',
    );
    if (runtime) {
      (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__ = {
        baseUrl: runtime.base_url,
        sessionToken: runtime.session_token,
      };
    }
  } catch {
    // Not running inside Tauri (or dev shell without sidecar): keep defaults.
  }
}

void discoverCore().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>,
  );
});
