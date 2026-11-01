# btcmm: measuring edge in BTC Up/Down contracts

`btcmm` is a research and market-making system for short-dated (5- and 15-minute) BTC Up/Down contracts on **Kalshi**, **Polymarket US** and **Gemini Predictions**.

Its main job is to **measure** whether a lasting edge exists on each venue after fees and adverse selection. When no edge exists, it must refuse to trade. Making money is never assumed. Most participants in these markets lose money.

> **Status: Phase 1 of 6.** Only data collection works: config, adapter interface, read-only adapters, recorder, clock check and tests. The system **cannot place orders**. Every write path raises `WritePathDisabled`, and the config loader refuses the `shadow`, `paper` and `live` modes.

---

## Layout (PLOT mapping)

| PLOT layer | Location | Contents |
|---|---|---|
| Plan | `plans/` | None yet. AGENTS.md says plans are created only on explicit instruction. |
| Logic | the agent / operator | Decides what to run. |
| Operations | `operations/` | `run_recorder.py`, `clock_check.py`, `discover_markets.py` |
| Tools / core library | `btcmm/` | Reusable code: fee math, book integrity, transport/backoff, parsers, clock, health |

```
btcmm/
  config.py             pydantic config; YAML for parameters, env vars for secrets
  adapters/
    base.py             ExchangeAdapter interface (read paths live, write paths disabled)
    transport.py        REST w/ safe retries, reconnecting websocket w/ backoff + jitter
    kalshi.py           KalshiAdapter
    polymarket_us.py    PolymarketUSAdapter
    gemini.py           GeminiAdapter
    simulated.py        SimulatedAdapter (in-memory / replays recorder output)
  data/
    models.py           venue-agnostic model (Decimal prices, Up-normalised books, UTC dual timestamps)
    book.py             L2 book with seq-gap / crossed-book detection
    parse.py            tolerant field/timestamp parsing
    spot.py             Coinbase, Kraken, Bitstamp, Gemini spot feeds
    recorder.py         multi-venue recorder
  model/fees.py         exact per-venue fee, rebate and rounding arithmetic
  monitoring/clock.py   SNTP + chrony clock verification
  monitoring/health.py  feed staleness and exchange-to-receive latency
  cli.py                `btcmm record | discover | clock-check`
  strategy/ risk/ execution/ sim/   placeholders for Phases 3-4
config/default.yaml     conservative defaults
tests/                  48 unit/integration tests
```

## Quick start

```bash
pip install -e '.[dev]'
pytest -q                                   # 48 tests
btcmm clock-check                           # exit 1 if drift > 100 ms or unknown
btcmm discover                              # list markets and fee schedules per venue
btcmm record                                # start collecting data (Ctrl-C to stop cleanly)
```

The recorder writes gzip JSONL files to `data/recordings/<date>/<venue>/<stream>/<HHMM>.jsonl.gz`. The streams are:

* `markets`: each market with its parsed settlement rule
* `fees`
* `book`: the top 10 levels, normalised to the Up contract
* `trades`
* `book_reconcile`: periodic REST snapshots
* `settlements`
* `status`: connects, gaps, mismatches, unverified rules, fee errors

There are also `spot/<feed>`, `system/clock` and `system/health` streams.

## Environment variables (secrets only)

| Variable | Venue | Notes |
|---|---|---|
| `KALSHI_API_KEY_ID` | Kalshi | |
| `KALSHI_PRIVATE_KEY_PATH` *or* `KALSHI_PRIVATE_KEY_PEM` | Kalshi | RSA (RSA-PSS) or Ed25519 PEM |
| `POLYMARKET_US_KEY_ID`, `POLYMARKET_US_SECRET_KEY` | Polymarket US | base64 Ed25519 key |
| `GEMINI_API_KEY`, `GEMINI_API_SECRET` | Gemini | HMAC; not used until Phase 4 |

Kalshi and Polymarket US **require auth even for market-data websockets**. Without keys, the adapter falls back to slow REST polling (`rest_poll_interval_s`, default 2 s) and records a `degraded` status. That data is much coarser, so get read-only keys before relying on the recordings.

## Per-venue setup

* **Kalshi.** Create an API key in account settings. Download the private key and set the two env vars. For integration tests (Phase 4), use the demo environment (`demo-api.kalshi.co`, URLs are commented in the config).
* **Polymarket US.** Create keys on the polymarket.us developer page. Fill in `venues.polymarket_us.fees` from the **currently published** schedule and set `verified: true` (see A6 below).
* **Gemini.** Start with a sandbox account (`api.sandbox.gemini.com`). Accepting the prediction-market terms (`POST /v1/prediction-markets/terms/accept`) is a Phase 4 step and is not done yet.

## Modes

Each venue is set independently to `off`, `record`, `shadow`, `paper` or `live`. In Phase 1 only `off` and `record` are accepted. The other three are rejected at startup, because the risk, gate and simulation code they depend on does not exist yet.

---

## Assumptions in the brief that were wrong, changed or are still unverified

During this build, the venues' API and doc hosts (`docs.kalshi.com`, `developer.gemini.com`, `api.*`) were **blocked by the sandbox network policy**. I verified what I could from the official SDK source code on PyPI: `kalshi_python_async` 3.35.0 and `polymarket-us` 2.4.1. Everything else is listed as unverified and needs checking against a live connection before Phase 2 calibration.

**Kalshi**

1. **Changed.** Prices are now fixed-point **dollar strings** (`*_dollars`). Contract counts are fixed-point strings (`*_fp`) with **0.01-contract granularity**. Integer-cent fields are gone from the current schema; the adapter still parses them as a fallback.
2. **Changed.** Tick size varies by market (`price_ranges`, `price_level_structure`). It is recorded per market, not assumed to be 1 cent.
3. **Changed.** `fee_type` has four values: `quadratic`, `quadratic_with_maker_fees` (maker fee = 0.25 × taker coefficient, i.e. 0.0175), `quadratic_with_combo_maker_fees` (0.5 ×) and `flat`. `flat` is **refused** rather than guessed.
4. **Changed.** The SDK's default host is now `external-api.kalshi.com/trade-api/v2`. The config uses the long-standing `api.elections.kalshi.com` host; both are configurable. API keys may also be **Ed25519**, which is supported.
5. **Unverified.** Fee rounding: the default is round up to $0.01 per order, as the brief states. Kalshi has a dedicated fee-rounding doc page I couldn't reach, so `fees.verified` is `false`. The websocket shapes for `orderbook_snapshot`, `orderbook_delta` and `trade` are not confirmed either; the parser accepts both the dollar and cent spellings. Kalshi's websocket **sequence numbers are per subscription (`sid`), not per market**, so any gap triggers a full resubscribe.

**Polymarket US**

6. **Wrong.** The SDK exposes **no fee-schedule endpoint**. Orders report `commissionsBasisPoints` and `makerCommissionsBasisPoints`, and fills report `commissionNotionalCollected`. That points to a bps-of-notional fee model, not necessarily `coef × C × P(1−P)`. Until this is resolved:
   * fees come from config (marked `verified: false`), and every edge report will flag them;
   * Phase 4 will reconcile modelled fees against the commission actually collected on each fill.
7. **Confirmed.** Intents are `BUY_LONG`, `SELL_LONG`, `BUY_SHORT` and `SELL_SHORT`, and long and short **share one book** per market slug. The book is quoted on the long side. Whether long means "Up" is inferred from the market's `outcome` field. If that can't be determined, `meta.up_side_confident=false` is recorded and prices are not inverted.
8. **Wrong.** Market-data websockets **require auth** (the brief implied public data). Messages carry the **full book with no sequence numbers**, so integrity checking means treating each message as a fresh snapshot, plus REST reconciliation.
9. **Confirmed.** The SDK never auto-retries POSTs because there is no idempotency key. Ambiguous order responses must be reconciled before resending (Phase 4).
10. **Unverified.** Tick size isn't in the schema; 1 cent is assumed (`meta.tick_verified=false`). The exact title and description wording for BTC Up/Down events is also unconfirmed, so discovery uses a regex on the title.

**Gemini**

11. **Unverified (most of this venue).** Confirmed from doc summaries: the events endpoint, `instrumentSymbol` as the only legitimate symbol source, the sandbox, terms acceptance, and the `recently-settled` endpoint. Assumed:
    * contract and event field names, parsed tolerantly;
    * books come from `GET /v1/book/{symbol}` and the v2 `l2` websocket, with prices on YES = Up;
    * `l2_updates` carry **no sequence numbers**, so the adapter resnapshots via REST on any integrity failure and on every reconnect;
    * the settlement rule's text location.

    Markets whose rule text doesn't confidently parse are flagged `settlement_rule_unverified` in the recordings.
12. **Unverified.** There is no fee endpoint wired. Config holds taker 0.07 and maker 0.0175. The maker waiver (through 2026-12-31) and the rebate program are recorded as **discretionary notes and excluded from edge**.

**Spot and settlement proxies**

13. **Gap.** Chainlink BTC/USD **Data Streams need paid credentials** and a report-decoding client. That isn't wired yet, so the Polymarket US proxy is the exchange composite for now. Measured basis versus official settlements will show how much this costs.
14. BRTI itself is licensed. The recorder captures its constituent exchanges (Coinbase, Kraken, Bitstamp, Gemini) so a proxy can be built and its basis measured in Phase 2.

## Design notes (the decisions that matter for edge)

* **Decimal everywhere.** Fee rounding is applied exactly per venue. At P = 0.50, a 1-contract Kalshi taker order owes $0.0175 raw but pays $0.02, a 14% surcharge on the fee. `min_size_for_overhead()` finds the smallest order size at which rounding overhead is acceptable.
* **Rebates are rounded down** (conservative). Only rebates that are paid deterministically per fill enter edge. Waivers, rebate programs and incentives are logged but never counted.
* **Every book is normalised to the Up contract.** A Kalshi NO bid at q becomes an Up ask at 1 − q. A Polymarket US market whose long side is "Down" is inverted.
* **Integrity first.** Books reject deltas that arrive before a snapshot, out-of-sequence deltas, negative sizes and crossed books. Each forces a resnapshot.
* **Clock.** The system checks clock offset with SNTP against three servers (median) and with `chronyc tracking`. If the clock state is unknown, it is treated as unsafe. Recording continues (offsets are logged so data can be corrected), but trading modes will refuse to start.

## Risk warnings

* These markets are competitive. Professional firms with lower latency are active on all three venues, and adverse selection near expiry is severe.
* The three venues settle on **different reference prices** (BRTI 60-second average, Chainlink point price, Gemini spot). Contracts on the same window are correlated, not identical. **Cross-venue price gaps are not arbitrage.**
* Gates before any live capital are: at least 500 windows, at least 2,000 fills, at least 30% of each from live paper trading, p < 0.05, and 48 hours of shadow mode after any change. These are enforced in code from Phase 3 onwards. Do not weaken them to get better-looking results.

## Delivery phases

1. ✅ Config, adapter interface, read-only adapters, recorder, clock check, tests
2. ⏳ Fair-value engine per settlement model, plus a calibration report (Brier score, log loss, reliability)
3. ⏳ Replay backtester (queue model, empirical fills), strategy, risk module
4. ⏳ Write paths, tested only on Kalshi demo, Gemini sandbox and SimulatedAdapter; shadow and paper modes; alerts
5. ⏳ Venue-selection report after 14 or more days of recordings
6. ⏳ Live trading behind the gates, one venue at a time, $25 cap
