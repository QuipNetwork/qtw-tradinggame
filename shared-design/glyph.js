// Canvas rendering primitives shared by design-doc.html mocks and the MVP app.
// Pure, deterministic: identical inputs → identical pixels. Visual changes here
// propagate to both consumers automatically.
//
// Consumers:
//   • design-doc.html loads this as <script type="module" src="shared-design/glyph.js">
//     and accesses functions via window.QuipGlyph.{strHash,renderGlyph,…}
//   • mvp app imports it via the `@shared` Vite alias: import * as Glyph from '@shared/glyph.js'

export function strHash(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

let _ns = 0;
function setSeed(s) { _ns = s; }
function _hash(x, y) {
  const n = Math.sin(x * 127.1 + y * 311.7 + _ns * 74.3) * 43758.5453;
  return n - Math.floor(n);
}
function _fade(t) { return t * t * t * (t * (t * 6 - 15) + 10); }
function noise2(x, y) {
  const ix = Math.floor(x), iy = Math.floor(y);
  const fx = x - ix, fy = y - iy;
  const ux = _fade(fx), uy = _fade(fy);
  const a = _hash(ix, iy), b = _hash(ix + 1, iy);
  const c = _hash(ix, iy + 1), d = _hash(ix + 1, iy + 1);
  return (a + (b - a) * ux) + ((c + (d - c) * ux) - (a + (b - a) * ux)) * uy;
}

export const PALETTES = {
  coral:    ['#27272a', '#52525b', '#ff6467', '#fb7185'],
  cyan:     ['#0c4a6e', '#0891b2', '#4BE0FF', '#BCF4FF'],
  yellow:   ['#52525b', '#a16207', '#FEF278', '#FFDE53'],
  purple:   ['#27272a', '#7c3aed', '#E6D7FF', '#a78bfa'],
  mixed:    ['#27272a', '#ff6467', '#FEF278', '#4BE0FF', '#E6D7FF'],
  light:    ['#fafafa', '#e4e4e7', '#a1a1aa', '#52525b'],
  aurora:   ['#0c4a6e', '#0e7490', '#67e8f9', '#a78bfa'],
  flare:    ['#7c2d12', '#ea580c', '#facc15', '#fde047'],
  forest:   ['#14532d', '#16a34a', '#84cc16', '#bef264'],
  ember:    ['#7f1d1d', '#dc2626', '#ff6467', '#fda4af'],
  electric: ['#1e1b4b', '#7c3aed', '#a78bfa', '#67e8f9'],
  sunset:   ['#831843', '#db2777', '#f472b6', '#fbcfe8']
};
export const PALETTE_NAMES = ['coral', 'cyan', 'yellow', 'purple', 'mixed', 'aurora', 'flare', 'forest', 'ember', 'electric', 'sunset'];
export const MODES = ['noise', 'waves', 'mandala'];

// Derive a varied style from a name's hash so different players → different look.
// Used for public views (leaderboard, spotlight) where we don't want sliders
// to leak the player's strategy.
export function pickStyle(seed, opts) {
  const s = Math.abs(seed | 0);
  const dflt = {
    palette: PALETTE_NAMES[s % PALETTE_NAMES.length],
    mode:    MODES[Math.floor(s / 13) % MODES.length],
    radial:  (Math.floor(s / 41) % 2) === 1,
    rays:    3 + (Math.floor(s / 71) % 4) * 2  // 3, 5, 7, 9
  };
  return Object.assign(dflt, opts || {});
}

// Slider-driven style derivation.
//   p2 Risk         → palette family (cool / neutral / warm)
//   p3 Trade size   → mode (noise / waves / mandala)
//   p4 Holding      → radial symmetry (off / on)
//   p5 Diversify    → ray count if radial (3 / 5 / 7 / 9)
// The name's seed picks the SPECIFIC palette inside the slider's family.
export function styleFromSliders(seed, p1, p2, p3, p4, p5) {
  const s = Math.abs(seed | 0);
  const COOL    = ['cyan', 'aurora', 'electric', 'forest'];
  const NEUTRAL = ['mixed', 'purple', 'sunset'];
  const WARM    = ['coral', 'flare', 'ember', 'yellow'];
  const pool = p2 < 0.33 ? COOL : (p2 < 0.66 ? NEUTRAL : WARM);
  const palette = pool[s % pool.length];
  const mode = p3 < 0.33 ? 'noise' : (p3 < 0.66 ? 'waves' : 'mandala');
  const radial = p4 > 0.5;
  const rays = 3 + Math.floor(Math.min(p5, 0.999) * 4) * 2;
  return { palette, mode, radial, rays };
}

export function renderGlyph(canvas, opts) {
  const o = Object.assign({
    seed: 0, p1: 0.5, p2: 0.5, p3: 0.5, p4: 0.5, p5: 0.5,
    palette: 'coral', cell: 6, bg: '#fafafa',
    mode: 'noise', radial: false, rays: 5
  }, opts);
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  setSeed(o.seed);

  ctx.fillStyle = o.bg;
  ctx.fillRect(0, 0, W, H);

  const cell = o.cell;
  const cols = Math.ceil(W / cell);
  const rows = Math.ceil(H / cell);
  const scale  = 0.14 + o.p1 * 0.18;
  const thresh = 0.55 + o.p2 * 0.32;
  const shapeMode = o.p3;
  const colorDrift = 0.25 + o.p4 * 0.75;
  const cs = PALETTES[o.palette] || PALETTES.coral;
  const cx = cols / 2, cy = rows / 2;

  function valNoise(mx, my) {
    const a = noise2(mx * scale, my * scale);
    const b = noise2(mx * scale * 2.4 + 7.3, my * scale * 2.4 + 11.7);
    return a * 0.7 + b * 0.3;
  }
  function valWaves(mx, my) {
    const f1 = 0.14 + o.p1 * 0.20;
    const f2 = 0.12 + o.p2 * 0.16;
    const v = Math.sin(mx * f1 + o.p4 * 6)
            + Math.cos(my * f2 + o.p5 * 4)
            + Math.sin((mx + my) * 0.06 + o.p3 * 3);
    return (v + 3) / 6;
  }
  function valMandala(x, y) {
    const dx = x - cx, dy = y - cy;
    const r = Math.sqrt(dx * dx + dy * dy);
    const ang = Math.atan2(dy, dx);
    const v1 = Math.sin(r * (0.16 + o.p1 * 0.22));
    const v2 = Math.cos(ang * o.rays + o.p4 * 4);
    const v3 = Math.sin(r * 0.06 + o.p5 * 5);
    return (v1 + v2 + v3 + 3) / 6;
  }

  for (let x = 0; x < cols; x++) {
    for (let y = 0; y < rows; y++) {
      const mx = Math.min(x, cols - 1 - x);
      const my = Math.min(y, rows - 1 - y);
      let v;

      if (o.mode === 'mandala') {
        v = valMandala(x, y);
      } else if (o.mode === 'waves') {
        v = valWaves(mx, my);
        if (o.radial) {
          const dx = x - cx, dy = y - cy;
          const r = Math.sqrt(dx * dx + dy * dy);
          const ang = Math.atan2(dy, dx);
          const radialV = (Math.sin(r * scale * 2 + ang * o.rays + o.p5 * 4) + 1) / 2;
          v = (v + radialV) / 2;
        }
      } else {
        v = valNoise(mx, my);
        if (o.radial) {
          const dx = x - cx, dy = y - cy;
          const r = Math.sqrt(dx * dx + dy * dy);
          const ang = Math.atan2(dy, dx);
          const radialV = (Math.sin(r * scale * (1 + o.p5 * 4) + ang * (o.rays + o.p5 * 2)) + 1) / 2;
          v = (v + radialV) / 2;
        }
      }

      if (v > 1 - thresh) {
        const cIdx = Math.floor(
          ((noise2(mx * 0.4 + 33, my * 0.4 + 71) * 0.7) + colorDrift * 0.3) * cs.length
        );
        ctx.fillStyle = cs[Math.min(cs.length - 1, Math.max(0, cIdx))];
        const px = x * cell, py = y * cell;
        if (shapeMode > 0.66) {
          ctx.beginPath();
          ctx.moveTo(px + cell / 2, py);
          ctx.lineTo(px + cell, py + cell / 2);
          ctx.lineTo(px + cell / 2, py + cell);
          ctx.lineTo(px, py + cell / 2);
          ctx.closePath();
          ctx.fill();
        } else if (shapeMode > 0.33) {
          ctx.beginPath();
          ctx.arc(px + cell / 2, py + cell / 2, cell / 2 - 0.4, 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.fillRect(px, py, cell - 0.5, cell - 0.5);
        }
      }
    }
  }
}

// Fake QR code renderer (looks like a real QR; doesn't decode).
// Production swap: encode the player's actual profile URL with a real lib.
export function renderFakeQR(canvas, seedStr) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, W, H);

  const N = 29; // QR Version 3
  const quietZone = 2;
  const total = N + 2 * quietZone;
  const m = Math.floor(Math.min(W, H) / total);
  const drawSize = m * total;
  const startX = Math.floor((W - drawSize) / 2) + quietZone * m;
  const startY = Math.floor((H - drawSize) / 2) + quietZone * m;
  const seed = strHash(seedStr || 'qtw');

  const g = [];
  for (let y = 0; y < N; y++) g.push(new Array(N).fill(-1));

  function placeFinder(gx, gy) {
    for (let dy = -1; dy <= 7; dy++) {
      for (let dx = -1; dx <= 7; dx++) {
        const x = gx + dx, y = gy + dy;
        if (x < 0 || x >= N || y < 0 || y >= N) continue;
        if (dx === -1 || dx === 7 || dy === -1 || dy === 7) {
          g[y][x] = 0;
          continue;
        }
        const inOuter = (dx === 0 || dx === 6 || dy === 0 || dy === 6);
        const inInner = (dx >= 2 && dx <= 4 && dy >= 2 && dy <= 4);
        g[y][x] = (inOuter || inInner) ? 1 : 0;
      }
    }
  }
  placeFinder(0, 0);
  placeFinder(N - 7, 0);
  placeFinder(0, N - 7);

  function placeAlignment(cx, cy) {
    for (let dy = -2; dy <= 2; dy++) {
      for (let dx = -2; dx <= 2; dx++) {
        const x = cx + dx, y = cy + dy;
        if (x < 0 || x >= N || y < 0 || y >= N) continue;
        const inOuter = (Math.abs(dx) === 2 || Math.abs(dy) === 2);
        const isCenter = (dx === 0 && dy === 0);
        g[y][x] = (inOuter || isCenter) ? 1 : 0;
      }
    }
  }
  placeAlignment(22, 22);

  for (let i = 8; i < N - 8; i++) {
    if (g[6][i] === -1) g[6][i] = (i % 2 === 0) ? 1 : 0;
    if (g[i][6] === -1) g[i][6] = (i % 2 === 0) ? 1 : 0;
  }

  g[N - 8][8] = 1;

  for (let i = 0; i <= 8; i++) {
    if (g[8][i] === -1) g[8][i] = (seed >> (i & 31)) & 1;
    if (g[i][8] === -1) g[i][8] = (seed >> ((i + 7) & 31)) & 1;
  }
  for (let i = 0; i < 8; i++) {
    if (g[8][N - 1 - i] === -1) g[8][N - 1 - i] = (seed >> ((i + 14) & 31)) & 1;
  }
  for (let i = 0; i < 7; i++) {
    if (g[N - 1 - i][8] === -1) g[N - 1 - i][8] = (seed >> ((i + 21) & 31)) & 1;
  }

  function hashXY(x, y, s) {
    const n = Math.sin(x * 31.7 + y * 17.3 + s * 23.1) * 43758.5453;
    return n - Math.floor(n);
  }
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      if (g[y][x] === -1) {
        const h = hashXY(x, y, seed);
        const h2 = hashXY(Math.floor(x / 2), Math.floor(y / 2), seed * 7) * 0.25;
        g[y][x] = (h + h2) > 0.55 ? 1 : 0;
      }
    }
  }

  ctx.fillStyle = '#0a0a10';
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      if (g[y][x] === 1) {
        ctx.fillRect(startX + x * m, startY + y * m, m, m);
      }
    }
  }
}

// Browser-side globals: lets design-doc.html consume this as a plain <script>
// (without ESM imports) by reading window.QuipGlyph.
if (typeof window !== 'undefined') {
  window.QuipGlyph = {
    strHash, pickStyle, styleFromSliders,
    renderGlyph, renderFakeQR,
    PALETTES, PALETTE_NAMES, MODES,
  };
}
