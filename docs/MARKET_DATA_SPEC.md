# Market Data — Requirements Brief

**From:** Azain (QTW 2026 Trading Game backend)
**For:** Rick & Jason
**Status:** draft for discussion

This describes the **shape of time-series data the backend needs**. It is *not* a
fixed API contract — **you choose how to serve it** (REST, warehouse, file, stream).
The JSON below is illustrative, to make the shape concrete. System context:
[`BACKEND_DAG.md`](BACKEND_DAG.md).

---

## 1. What we do with the data

For each portfolio solve we estimate expected returns **μ** and a covariance
matrix **Σ** from hourly returns, and we continuously mark portfolios to market
against the latest price. So we need two things:

- **A. Historical hourly bars** → to compute μ and Σ.
- **B. A latest price per asset** → for live mark-to-market.

We compute returns / μ / Σ ourselves — please send **prices**, not returns or
indicators.

---

## 2. Universe

- A candidate universe of **~25 assets**: a mix of **US equities** and
  **cryptocurrencies** (final list coming from Brent). The spec is
  count-agnostic — we always query by an explicit list of assets.
- Users select a subset to trade at the booth, so we need data for **every**
  candidate asset.
- All prices in **USD**.
- Each asset is identified by `symbol` (e.g. `BTC`, `AAPL`) and `asset_class`
  (`crypto` | `equity`). If your canonical IDs differ from the ticker symbols,
  please also share a one-time **reference map** (`symbol → your id`).

---

## 3. Query A — Historical hourly bars (for μ, Σ)

Given a list of assets, an interval, and a lookback, return hourly bars per asset.

| Field | Value |
|---|---|
| Interval | `1h` |
| History depth | **90 days** available (we slice shorter windows — a 30-day covariance window and shorter μ lookbacks — from it) |
| Crypto | continuous, 24/7 |
| Equities | **regular trading-hours bars only** — no synthetic overnight/weekend bars; gaps are expected and we align the mixed grid on our side |
| Equity prices | **split/dividend-adjusted** (adjusted close) so returns aren't corrupted by corporate actions |
| Timestamps | **UTC** (ISO-8601 or epoch-ms); please state whether a bar's timestamp marks its **open** or **close** |
| Fields per bar | *to be decided* — **close** is required; full **OHLCV** (open, high, low, close, volume) preferred. Volume also helps rank liquidity for the asset list. |

Illustrative shape:

```json
// request (logical)
{ "assets": ["BTC", "AAPL"], "interval": "1h", "range": "90d" }

// response (logical)
{
  "interval": "1h",
  "bars": {
    "BTC":  [ { "t": "2026-06-01T00:00:00Z", "o": 65010.2, "h": 65240.0, "l": 64880.5, "c": 65120.7, "v": 1234.5 }, "..." ],
    "AAPL": [ { "t": "2026-06-01T13:30:00Z", "o": 196.10,  "h": 196.80,  "l": 195.90,  "c": 196.55,  "v": 480200 }, "..." ]
  }
}
```

`AAPL` shows gaps overnight and on weekends — expected; we forward-fill/align.

---

## 4. Query B — Latest price (for live mark-to-market)

Given a list of assets, return the current price.

- One **batched** call covering all assets. We poll it for the live ticker;
  every few seconds is plenty — it's a single shared snapshot, independent of how
  many users are online.
- When an equity's market is closed, return the **last trade/close**. An
  `as_of` timestamp (and optional `stale` flag) is welcome but not required.

```json
// request (logical)
{ "assets": ["BTC", "AAPL"] }

// response (logical)
{
  "as_of": "2026-06-25T14:32:10Z",
  "prices": {
    "BTC":  { "price": 65180.4, "t": "2026-06-25T14:32:09Z" },
    "AAPL": { "price": 196.62,  "t": "2026-06-25T14:32:08Z", "stale": false }
  }
}
```

---

## 5. Serving — your call

The two logical queries above are all we need. **How** you expose them is up to
you; any of these is fine as long as both are answerable:

- **REST** *(our mild preference)* — a bars endpoint + a quote endpoint, JSON.
  Easiest for us to integrate and for you to document.
- **Warehouse table** — a bars table + a latest-quote view (BigQuery / Snowflake
  / Postgres); we'll write the SQL.
- **File drop** — CSV/Parquet history to S3/GCS, plus a small quote endpoint or
  stream for live.
- **Stream** — WS/Kafka for live, REST/file for history.

---

## 6. Open for discussion

- Exact **fields** (OHLCV vs close-only) and serialization (JSON / CSV / Parquet).
- **Transport, auth** (API key, endpoint URLs) and **rate limits**.
- **Refresh cadence** for new hourly bars, and acceptable **spot latency**.
- **Corporate-actions** method for equity adjustment (confirm adjusted close).
- The **symbol ↔ id** reference map and any assets that are hard to source.
