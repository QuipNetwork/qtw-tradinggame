// The 25-asset tradable universe (14 crypto + 11 stocks), sourced from the
// QTW oracle routing table (qtw-oracles / data/oracle-routing.json).
// Order here is display order in the sign-up asset selector.
// Icons live in shared-design/asset-icons/ (see design doc §05 for the audit);
// `color` is the asset's mark color, used in the portfolio allocation bar.

import type { AssetInfo, AssetTicker } from './types';

export const ASSETS: AssetInfo[] = [
  // ── Crypto (14) — CoinGecko primary oracle ──
  { ticker: 'BTC',    name: 'Bitcoin',             class: 'crypto', icon: 'btc.svg',    color: '#F7931A' },
  { ticker: 'ETH',    name: 'Ethereum',            class: 'crypto', icon: 'eth.svg',    color: '#627EEA' },
  { ticker: 'BNB',    name: 'BNB',                 class: 'crypto', icon: 'bnb.svg',    color: '#F3BA2F' },
  { ticker: 'USDC',   name: 'USD Coin',            class: 'crypto', icon: 'usdc.svg',   color: '#2775CA' },
  { ticker: 'XRP',    name: 'XRP',                 class: 'crypto', icon: 'xrp.svg',    color: '#23292F' },
  { ticker: 'SOL',    name: 'Solana',              class: 'crypto', icon: 'sol.svg',    color: '#14F195' },
  { ticker: 'HYPE',   name: 'Hyperliquid',         class: 'crypto', icon: 'hype.png',   color: '#4FD1B5' },
  { ticker: 'DOGE',   name: 'Dogecoin',            class: 'crypto', icon: 'doge.svg',   color: '#C2A633' },
  { ticker: 'USDT',   name: 'Tether',              class: 'crypto', icon: 'usdt.svg',   color: '#26A17B' },
  { ticker: 'ZEC',    name: 'Zcash',               class: 'crypto', icon: 'zec.svg',    color: '#F4B728' },
  { ticker: 'ALGO',   name: 'Algorand',            class: 'crypto', icon: 'algo.svg',   color: '#18181B' },
  { ticker: 'STRK',   name: 'Starknet',            class: 'crypto', icon: 'strk.png',   color: '#EC796B' },
  { ticker: 'FIL',    name: 'Filecoin',            class: 'crypto', icon: 'fil.svg',    color: '#0090FF' },
  { ticker: 'RENDER', name: 'Render',              class: 'crypto', icon: 'render.png', color: '#E11D2E' },
  // ── Stocks (11) — Alpaca primary oracle ──
  { ticker: 'IONQ',   name: 'IonQ',                class: 'stock',  icon: 'ionq.png',   color: '#FF8200' },
  { ticker: 'QBTS',   name: 'D-Wave Quantum',      class: 'stock',  icon: 'qbts.png',   color: '#008CD7' },
  { ticker: 'RGTI',   name: 'Rigetti Computing',   class: 'stock',  icon: 'rgti.png',   color: '#00A7B5' },
  { ticker: 'QUBT',   name: 'Quantum Computing',   class: 'stock',  icon: 'qubt.png',   color: '#1E6FD9' },
  { ticker: 'QNT',    name: 'Quantinuum',          class: 'stock',  icon: 'qnt.png',    color: '#101820' },
  { ticker: 'SAF',    name: 'Safran',              class: 'stock',  icon: 'saf.png',    color: '#002F87' },
  { ticker: 'INDI',   name: 'indie Semiconductor', class: 'stock',  icon: 'indi.png',   color: '#7C3AED' },
  { ticker: 'BTQ',    name: 'BTQ Technologies',    class: 'stock',  icon: 'btq.png',    color: '#18181B' },
  { ticker: 'LAES',   name: 'SEALSQ',              class: 'stock',  icon: 'laes.png',   color: '#2AA8E0' },
  { ticker: 'ARQQ',   name: 'Arqit Quantum',       class: 'stock',  icon: 'arqq.png',   color: '#00C2CB' },
  { ticker: 'SPCX',   name: 'SpaceX',              class: 'stock',  icon: 'spcx.png',   color: '#005288' },
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
