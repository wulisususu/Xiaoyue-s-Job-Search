import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/dom';

// CI runners (2-core windows-latest) run these React pages ~2.5x slower than
// dev machines; the 1000ms default waitFor budget has been observed to flake
// there even though the handled interaction is immediate. The timeout only
// bounds failure reporting, so raising it keeps passing tests just as fast.
configure({ asyncUtilTimeout: 5000 });
