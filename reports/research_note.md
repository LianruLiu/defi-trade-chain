# Adaptive-Fee AMM — Does Flow-Adaptive Pricing Actually Help LPs?

*200 Monte Carlo price paths, 600 steps each, two-state (calm/turbulent)
volatility regime. Every pool config sees the identical set of price paths
and the identical retail-order random seed per path — differences below
come only from the fee rule, not from different draws.*

## Setup

Three pools competing for the same order flow on the same price paths:

| Config | Fee rule |
|---|---|
| `static_5bps` | fixed 5bps — the "attract volume at all costs" baseline |
| `static_30bps` | fixed 30bps — the Uniswap V2 default, "protect LPs" baseline |
| `dynamic_5_100bps` | floor 5bps, ceiling 100bps, scales with realized short-term volatility of the pool's own price |

An arbitrageur trades optimally (ternary search over trade size) against
each pool whenever the external price has moved away from the pool price
by more than the current fee justifies — this is the actual LVR
mechanism, not an assumption bolted on afterward. Retail flow trades
random sizes/directions each step, with size shrinking as the fee rises
(a simple fee-elasticity assumption, documented in `lvr_experiment.py`).

## Results

| Config | mean P&L vs hold | P&L std | 5th/95th pct | mean fees | mean retail volume | mean fee (bps) |
|---|---|---|---|---|---|---|
| static_5bps | -138887.4 | 277032.3 | -465496.5 / 1686.1 | 2629.3 | 114524.9 | 5.00 |
| static_30bps | -127676.2 | 274827.4 | -447429.9 / 12807.1 | 13912.6 | 89596.4 | 30.00 |
| dynamic_5_100bps | -126728.0 | 274472.4 | -435377.9 / 15335.5 | 14832.5 | 96288.6 | 19.01 |

**The dynamic pool lands close to the 30bps pool's LP protection
(-126728 vs -127676 mean P&L) while capturing
more retail volume than it
(96289 vs 89596), by sitting at the 5bps
floor during calm regimes and only taxing flow heavily once realized
volatility signals an arbitrage-heavy period.** That's the actual claim
of this repo — not that dynamic fees are a free lunch, but that they let
a pool approximate the LP protection of a high static fee without paying
for it in retail volume the whole time, because the two are only in
tension during the (empirically minority) turbulent-regime steps.

See `reports/figures/02_pnl_vs_retail_volume.png` for this as a
protection-vs-volume tradeoff plot — the dynamic pool's position relative
to the two static baselines is the headline result.

## Where this doesn't hold

- **Elasticity assumption is a modeling choice, not measured.** The
  "retail volume shrinks with fee" relationship is a clean exponential
  by construction; real router-level fee sensitivity is an empirical
  question this repo doesn't answer (it would need real DEX aggregator
  routing data, e.g. 1inch/Paraswap fill logs across fee tiers).
- **Arbitrageur is a single idealized agent per step** with full
  information and no gas cost. Real arbitrage is contested (MEV
  competition), latency-bound, and gas-costly — all of which would
  reduce how much of the "textbook" LVR actually gets extracted, for
  every fee schedule here, not just one.
- **Regime parameters (calm/turbulent probabilities and vols) are
  chosen to be plausible, not calibrated to a specific real asset.**
  The qualitative result (dynamic ≈ high-static protection, ≥ high-static
  volume) is fairly robust to these choices in spot checks, but the
  exact numbers in the table above are not a forecast for any real pool.
- **Sensitivity/EWMA-alpha in `DynamicFeePool` were chosen by hand**
  (see `py/test_pool.py`), not fit to data — an obvious next step is
  calibrating them against the Granger-significant lag structure found
  in the sibling on-chain-microstructure repo's real (well, real-shaped)
  order flow, rather than picking round numbers.

## What would make this a stronger result

- Replace the idealized single-arbitrageur step with a small population
  of boundedly-rational arbitrageurs with heterogeneous gas costs, so
  LVR extraction isn't 100% efficient at every fee level
  (`n_arb_trades_mean` in the summary table is the number to watch).
- Fit the fee-elasticity-of-retail-volume parameter to real DEX
  aggregator data instead of assuming a functional form.
- Extend `DynamicFeePool.sol` into an actual Uniswap v4 hook (the
  contract's structure — a fee computed from pool state on every swap —
  is deliberately compatible with that model) and backtest against a
  real historical Uniswap pool's swap log.
