import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import symbolsSvg from '../../shared-design/symbols.svg.html?raw';

// Inject the shared SVG symbol library so <use href="#crypto-btc"/> etc. work
// across the whole app. Same file design-doc.html consumes.
const symbolsHost = document.createElement('div');
symbolsHost.innerHTML = symbolsSvg;
symbolsHost.style.position = 'absolute';
symbolsHost.style.width = '0';
symbolsHost.style.height = '0';
symbolsHost.style.overflow = 'hidden';
document.body.prepend(symbolsHost);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
