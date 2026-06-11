// The 25-asset tradable universe (14 crypto + 11 stocks), sourced from the
// QTW oracle routing table (qtw-oracles / data/oracle-routing.json).
// Order here is display order in the sign-up asset selector.
// Icons live in shared-design/asset-icons/ (see design doc §05 for the audit);
// `color` is the asset's mark color, used in the portfolio allocation bar.

import type { AssetInfo, AssetTicker } from './types';

export const ASSETS: AssetInfo[] = [
  // ── Crypto (14) — CoinGecko primary oracle ──
  { ticker: 'BTC',    name: 'Bitcoin',             class: 'crypto', icon: 'btc.svg',    color: '#F7931A', vol: 0.45 },
  { ticker: 'ETH',    name: 'Ethereum',            class: 'crypto', icon: 'eth.svg',    color: '#627EEA', vol: 0.55 },
  { ticker: 'BNB',    name: 'BNB',                 class: 'crypto', icon: 'bnb.svg',    color: '#F3BA2F', vol: 0.50 },
  { ticker: 'USDC',   name: 'USD Coin',            class: 'crypto', icon: 'usdc.svg',   color: '#2775CA', vol: 0.02 },
  { ticker: 'XRP',    name: 'XRP',                 class: 'crypto', icon: 'xrp.svg',    color: '#23292F', vol: 0.65 },
  { ticker: 'SOL',    name: 'Solana',              class: 'crypto', icon: 'sol.png',    color: '#9945FF', vol: 0.70 },
  { ticker: 'HYPE',   name: 'Hyperliquid',         class: 'crypto', icon: 'hype.png',   color: '#4FD1B5', vol: 0.90 },
  { ticker: 'DOGE',   name: 'Dogecoin',            class: 'crypto', icon: 'doge.svg',   color: '#C2A633', vol: 0.85 },
  { ticker: 'USDT',   name: 'Tether',              class: 'crypto', icon: 'usdt.svg',   color: '#26A17B', vol: 0.02 },
  { ticker: 'ZEC',    name: 'Zcash',               class: 'crypto', icon: 'zec.svg',    color: '#F4B728', vol: 0.75 },
  { ticker: 'ALGO',   name: 'Algorand',            class: 'crypto', icon: 'algo.svg',   color: '#18181B', vol: 0.70 },
  { ticker: 'STRK',   name: 'Starknet',            class: 'crypto', icon: 'strk.png',   color: '#EC796B', vol: 0.80 },
  { ticker: 'FIL',    name: 'Filecoin',            class: 'crypto', icon: 'fil.svg',    color: '#0090FF', vol: 0.70 },
  { ticker: 'RENDER', name: 'Render',              class: 'crypto', icon: 'render.png', color: '#E11D2E', vol: 0.80 },
  // ── Stocks (11) — Alpaca primary oracle ──
  { ticker: 'IONQ',   name: 'IonQ',                class: 'stock',  icon: 'ionq.png',   color: '#FF8200', vol: 0.75 },
  { ticker: 'QBTS',   name: 'D-Wave Quantum',      class: 'stock',  icon: 'qbts.png',   color: '#008CD7', vol: 0.85 },
  { ticker: 'RGTI',   name: 'Rigetti Computing',   class: 'stock',  icon: 'rgti.png',   color: '#17A2A6', vol: 0.90 },
  { ticker: 'QUBT',   name: 'Quantum Computing',   class: 'stock',  icon: 'qubt.png',   color: '#1E6FD9', vol: 0.95 },
  { ticker: 'QNT',    name: 'Quantinuum',          class: 'stock',  icon: 'qnt.png',    color: '#101820', vol: 0.60 },
  { ticker: 'SAF',    name: 'Safran',              class: 'stock',  icon: 'saf.png',    color: '#002F87', vol: 0.25 },
  { ticker: 'INDI',   name: 'indie Semiconductor', class: 'stock',  icon: 'indi.png',   color: '#7C3AED', vol: 0.70 },
  { ticker: 'BTQ',    name: 'BTQ Technologies',    class: 'stock',  icon: 'btq.png',    color: '#18181B', vol: 0.85 },
  { ticker: 'LAES',   name: 'SEALSQ',              class: 'stock',  icon: 'laes.png',   color: '#2AA8E0', vol: 0.90 },
  { ticker: 'ARQQ',   name: 'Arqit Quantum',       class: 'stock',  icon: 'arqq.png',   color: '#00C2CB', vol: 0.85 },
  { ticker: 'SPCX',   name: 'SpaceX',              class: 'stock',  icon: 'spcx.png',   color: '#005288', vol: 0.50 },
];

export const CRYPTO_ASSETS = ASSETS.filter(a => a.class === 'crypto');
export const STOCK_ASSETS = ASSETS.filter(a => a.class === 'stock');

export const ASSET_BY_TICKER: Record<AssetTicker, AssetInfo> =
  Object.fromEntries(ASSETS.map(a => [a.ticker, a])) as Record<AssetTicker, AssetInfo>;

export function assetIconSrc(ticker: AssetTicker): string {
  return '/shared-design/asset-icons/' + ASSET_BY_TICKER[ticker].icon;
}

export function assetColor(ticker: AssetTicker): string {
  return ASSET_BY_TICKER[ticker].color;
}
