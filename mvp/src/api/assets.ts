// The 25-asset tradable universe (14 crypto + 11 stocks), sourced from the
// QTW oracle routing table (qtw-oracles / data/oracle-routing.json).
// Order here is display order in the sign-up asset selector.

import type { AssetInfo } from './types';

export const ASSETS: AssetInfo[] = [
  // ── Crypto (14) — CoinGecko primary oracle ──
  { ticker: 'BTC',    name: 'Bitcoin',             class: 'crypto' },
  { ticker: 'ETH',    name: 'Ethereum',            class: 'crypto' },
  { ticker: 'BNB',    name: 'BNB',                 class: 'crypto' },
  { ticker: 'USDC',   name: 'USD Coin',            class: 'crypto' },
  { ticker: 'XRP',    name: 'XRP',                 class: 'crypto' },
  { ticker: 'SOL',    name: 'Solana',              class: 'crypto' },
  { ticker: 'HYPE',   name: 'Hyperliquid',         class: 'crypto' },
  { ticker: 'DOGE',   name: 'Dogecoin',            class: 'crypto' },
  { ticker: 'USDT',   name: 'Tether',              class: 'crypto' },
  { ticker: 'ZEC',    name: 'Zcash',               class: 'crypto' },
  { ticker: 'ALGO',   name: 'Algorand',            class: 'crypto' },
  { ticker: 'STRK',   name: 'Starknet',            class: 'crypto' },
  { ticker: 'FIL',    name: 'Filecoin',            class: 'crypto' },
  { ticker: 'RENDER', name: 'Render',              class: 'crypto' },
  // ── Stocks (11) — Alpaca primary oracle ──
  { ticker: 'IONQ',   name: 'IonQ',                class: 'stock' },
  { ticker: 'QBTS',   name: 'D-Wave Quantum',      class: 'stock' },
  { ticker: 'RGTI',   name: 'Rigetti Computing',   class: 'stock' },
  { ticker: 'QUBT',   name: 'Quantum Computing',   class: 'stock' },
  { ticker: 'QNT',    name: 'Quantinuum',          class: 'stock' },
  { ticker: 'SAF',    name: 'Safran',              class: 'stock' },
  { ticker: 'INDI',   name: 'indie Semiconductor', class: 'stock' },
  { ticker: 'BTQ',    name: 'BTQ Technologies',    class: 'stock' },
  { ticker: 'LAES',   name: 'SEALSQ',              class: 'stock' },
  { ticker: 'ARQQ',   name: 'Arqit Quantum',       class: 'stock' },
  { ticker: 'SPCX',   name: 'SpaceX',              class: 'stock' },
];

export const CRYPTO_ASSETS = ASSETS.filter(a => a.class === 'crypto');
export const STOCK_ASSETS = ASSETS.filter(a => a.class === 'stock');
