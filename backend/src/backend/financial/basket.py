"""The 15-asset crypto basket — single source of truth for ticker metadata.

Final basket to be locked closer to booth day; this placeholder uses top-15
liquid crypto assets plus one stablecoin (USDC) to give the optimizer a
risk-off option.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetMeta:
    ticker: str
    coingecko_id: str  # query id for /coins/{id}/market_chart
    chain: str
    decimals: int


BASKET: tuple[AssetMeta, ...] = (
    AssetMeta("BTC", "bitcoin", "bitcoin", 8),
    AssetMeta("ETH", "ethereum", "ethereum", 18),
    AssetMeta("SOL", "solana", "solana", 9),
    AssetMeta("USDC", "usd-coin", "ethereum", 6),
    AssetMeta("LINK", "chainlink", "ethereum", 18),
    AssetMeta("UNI", "uniswap", "ethereum", 18),
    AssetMeta("ADA", "cardano", "cardano", 6),
    AssetMeta("DOT", "polkadot", "polkadot", 10),
    AssetMeta("AVAX", "avalanche-2", "avalanche", 18),
    AssetMeta("MATIC", "matic-network", "polygon", 18),
    AssetMeta("ATOM", "cosmos", "cosmos", 6),
    AssetMeta("NEAR", "near", "near", 24),
    AssetMeta("LTC", "litecoin", "litecoin", 8),
    AssetMeta("XRP", "ripple", "ripple", 6),
    AssetMeta("DOGE", "dogecoin", "dogecoin", 8),
)

TICKERS: tuple[str, ...] = tuple(a.ticker for a in BASKET)


def get_asset(ticker: str) -> AssetMeta:
    for a in BASKET:
        if a.ticker == ticker:
            return a
    raise KeyError(f"Unknown ticker: {ticker}")
