"""The 25-asset tradable universe — single source of truth for ticker metadata.

Mirrors mvp/src/api/assets.ts (14 crypto + 11 stocks) and the assets-api
registry (assets.yaml). Players select a subset of this universe at sign-up;
the optimizer runs over their selection.

Note: QNT (Quantinuum) recently went public and is included. SPCX (SpaceX) is
still private — assets-api cannot price it yet; drop/substitute/synthesize
before booth (tracked in TODO.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .. import config

AssetClass = Literal["crypto", "stock"]


@dataclass(frozen=True)
class AssetMeta:
    ticker: str
    name: str
    asset_class: AssetClass


BASKET: tuple[AssetMeta, ...] = (
    # ── Crypto (14) ──
    AssetMeta("BTC", "Bitcoin", "crypto"),
    AssetMeta("ETH", "Ethereum", "crypto"),
    AssetMeta("BNB", "BNB", "crypto"),
    AssetMeta("USDC", "USD Coin", "crypto"),
    AssetMeta("XRP", "XRP", "crypto"),
    AssetMeta("SOL", "Solana", "crypto"),
    AssetMeta("HYPE", "Hyperliquid", "crypto"),
    AssetMeta("DOGE", "Dogecoin", "crypto"),
    AssetMeta("USDT", "Tether", "crypto"),
    AssetMeta("ZEC", "Zcash", "crypto"),
    AssetMeta("ALGO", "Algorand", "crypto"),
    AssetMeta("STRK", "Starknet", "crypto"),
    AssetMeta("FIL", "Filecoin", "crypto"),
    AssetMeta("RENDER", "Render", "crypto"),
    # ── Stocks (11) ──
    AssetMeta("IONQ", "IonQ", "stock"),
    AssetMeta("QBTS", "D-Wave Quantum", "stock"),
    AssetMeta("RGTI", "Rigetti Computing", "stock"),
    AssetMeta("QUBT", "Quantum Computing", "stock"),
    AssetMeta("QNT", "Quantinuum", "stock"),
    AssetMeta("SAF", "Safran", "stock"),
    AssetMeta("INDI", "indie Semiconductor", "stock"),
    AssetMeta("BTQ", "BTQ Technologies", "stock"),
    AssetMeta("LAES", "SEALSQ", "stock"),
    AssetMeta("ARQQ", "Arqit Quantum", "stock"),
    AssetMeta("SPCX", "SpaceX", "stock"),
)

TICKERS: tuple[str, ...] = tuple(a.ticker for a in BASKET)
STABLECOINS: frozenset[str] = frozenset({"USDC", "USDT"})


def get_asset(ticker: str) -> AssetMeta:
    for a in BASKET:
        if a.ticker == ticker:
            return a
    raise KeyError(f"Unknown ticker: {ticker}")


def validate_basket(assets: list[str] | None) -> list[str]:
    """Resolve a player's basket: validate tickers, default to the full universe.

    Preserves the player's selection order. Raises ValueError on unknown
    tickers or a basket smaller than MIN_BASKET_SIZE.
    """
    if not assets:
        return list(TICKERS)
    unknown = [t for t in assets if t not in TICKERS]
    if unknown:
        raise ValueError(f"unknown tickers in basket: {unknown}")
    seen: set[str] = set()
    basket = [t for t in assets if not (t in seen or seen.add(t))]
    if len(basket) < config.MIN_BASKET_SIZE:
        raise ValueError(
            f"basket needs at least {config.MIN_BASKET_SIZE} assets, got {len(basket)}"
        )
    return basket
