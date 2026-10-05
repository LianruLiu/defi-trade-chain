"""
Monte Carlo: how do the static-fee and dynamic-fee pools actually perform
for an LP, once an external market and both informed (arbitrage) and
uninformed (retail) flow are simulated against them?

Model, per path:
  - External reference price follows a GBM with a two-state Markov
    volatility regime (calm / turbulent) — deliberately simple, not a
    recalibration of the GARCH model in the sibling on-chain-microstructure
    repo, since the point here is the fee mechanism, not the price process.
  - Each step, an arbitrageur checks both swap directions and executes
    the profit-maximizing trade size if — and only if — it's profitable
    net of the pool's current fee (ternary search over quote(), since
    profit is concave in trade size). This is what actually moves the
    pool price toward the external price and is the channel LVR comes
    from.
  - Retail flow trades a random size each step in a random direction,
    with a size that shrinks as the fee rises (elasticity_k below) — a
    simple stand-in for "traders route elsewhere when a pool gets
    expensive," which is the real-world force a fixed high fee fights
    and a fixed low fee doesn't.

Fee revenue is tracked directly at each swap (amount_in * fee_bps), not
backed out from a value difference — the only thing computed indirectly
is P&L, i.e. final pool value vs. a hold portfolio, marked at the path's
final external price.
"""

import random
from dataclasses import dataclass

from pool_sim import DynamicPoolSim, StaticPoolSim, quote

ONE = 10**18


@dataclass
class PathResult:
    label: str
    net_pnl_token1: float
    fees_token1: float
    retail_volume_token1: float
    arb_volume_token1: float
    mean_fee_bps: float
    n_arb_trades: int


def simulate_price_path(n_steps: int, rng: random.Random, s0: float = 1.0):
    sigma_calm, sigma_turb = 0.015, 0.09
    p_calm_to_turb, p_turb_to_calm = 0.01, 0.08

    prices = [s0]
    regime = "calm"
    for _ in range(n_steps):
        sigma = sigma_calm if regime == "calm" else sigma_turb
        shock = rng.gauss(0, sigma)
        prices.append(prices[-1] * (1 + shock))
        if regime == "calm" and rng.random() < p_calm_to_turb:
            regime = "turb"
        elif regime == "turb" and rng.random() < p_turb_to_calm:
            regime = "calm"
    return prices


def _arb_profit(pool, zero_for_one: bool, amount_in: int, ext_price: float) -> float:
    fee_bps = pool.current_fee_bps()
    amount_out = quote(pool.reserve0, pool.reserve1, fee_bps, zero_for_one, amount_in)
    if zero_for_one:
        return amount_out / ONE - (amount_in / ONE) * ext_price
    else:
        return (amount_out / ONE) * ext_price - amount_in / ONE


def _optimal_arb_amount(pool, zero_for_one: bool, ext_price: float, hi: int) -> int:
    lo = 0
    for _ in range(40):
        m1 = lo + (hi - lo) // 3
        m2 = hi - (hi - lo) // 3
        if _arb_profit(pool, zero_for_one, m1, ext_price) < _arb_profit(pool, zero_for_one, m2, ext_price):
            lo = m1
        else:
            hi = m2
    return (lo + hi) // 2


@dataclass
class _Ledger:
    fees_token1: float = 0.0
    arb_volume_token1: float = 0.0
    retail_volume_token1: float = 0.0
    n_arb_trades: int = 0


def _record_fee(ledger, amount_in_units, is_token0_in, ext_price, fee_bps):
    notional_token1 = amount_in_units * ext_price if is_token0_in else amount_in_units
    ledger.fees_token1 += notional_token1 * fee_bps / 10_000


def run_arbitrage_step(pool, ext_price, depth_cap, ledger) -> None:
    best_amount, best_profit, best_dir = 0, 0.0, True
    for zero_for_one in (True, False):
        amt = _optimal_arb_amount(pool, zero_for_one, ext_price, depth_cap)
        profit = _arb_profit(pool, zero_for_one, amt, ext_price)
        if profit > best_profit:
            best_amount, best_profit, best_dir = amt, profit, zero_for_one

    if best_amount > 0 and best_profit > 0:
        fee_bps = pool.current_fee_bps()
        pool.swap(best_dir, best_amount)
        amt_units = best_amount / ONE
        _record_fee(ledger, amt_units, best_dir, ext_price, fee_bps)
        ledger.arb_volume_token1 += amt_units * ext_price if best_dir else amt_units
        ledger.n_arb_trades += 1


def run_retail_step(pool, rng, base_size, elasticity_k, ext_price, ledger) -> None:
    fee_bps = pool.current_fee_bps()
    size = base_size * rng.expovariate(1.0) * (2.718281828 ** (-elasticity_k * fee_bps))
    if size < 1e-6:
        return
    zero_for_one = rng.random() < 0.5
    amount_in = int(size * ONE)
    reserve_in = pool.reserve0 if zero_for_one else pool.reserve1
    amount_in = min(amount_in, reserve_in // 20)
    if amount_in <= 0:
        return

    fee_bps_now = pool.current_fee_bps()
    pool.swap(zero_for_one, amount_in)
    amt_units = amount_in / ONE
    _record_fee(ledger, amt_units, zero_for_one, ext_price, fee_bps_now)
    ledger.retail_volume_token1 += amt_units * ext_price if zero_for_one else amt_units


def run_path(make_pool, label, price_path, rng, base_reserve=1_000_000) -> PathResult:
    pool = make_pool()
    ledger = _Ledger()
    fee_history = []
    reserve0_start, reserve1_start = pool.reserve0 / ONE, pool.reserve1 / ONE

    for t in range(1, len(price_path)):
        ext_price = price_path[t]
        fee_history.append(pool.current_fee_bps())
        run_arbitrage_step(pool, ext_price, depth_cap=int(0.2 * base_reserve * ONE), ledger=ledger)
        run_retail_step(pool, rng, base_size=200.0, elasticity_k=0.01, ext_price=ext_price, ledger=ledger)

    final_price = price_path[-1]
    reserve0_end, reserve1_end = pool.reserve0 / ONE, pool.reserve1 / ONE
    pool_value_end = reserve0_end * final_price + reserve1_end
    hold_value_end = reserve0_start * final_price + reserve1_start

    return PathResult(
        label=label,
        net_pnl_token1=pool_value_end - hold_value_end,
        fees_token1=ledger.fees_token1,
        retail_volume_token1=ledger.retail_volume_token1,
        arb_volume_token1=ledger.arb_volume_token1,
        mean_fee_bps=sum(fee_history) / len(fee_history),
        n_arb_trades=ledger.n_arb_trades,
    )


def make_static(fee_bps, base_reserve=1_000_000):
    return lambda: StaticPoolSim(reserve0=int(base_reserve * ONE), reserve1=int(base_reserve * ONE), fee_bps=fee_bps)


def make_dynamic(base_reserve=1_000_000):
    return lambda: DynamicPoolSim(
        reserve0=int(base_reserve * ONE), reserve1=int(base_reserve * ONE),
        base_fee_bps=5, min_fee_bps=5, max_fee_bps=100,
        sensitivity=2_000, ewma_alpha=3 * 10**17,
    )


def run_monte_carlo(n_paths=200, n_steps=600, seed=11):
    configs = {
        "static_5bps": make_static(5),
        "static_30bps": make_static(30),
        "dynamic_5_100bps": make_dynamic(),
    }
    results = {name: [] for name in configs}

    master_rng = random.Random(seed)
    for _ in range(n_paths):
        path_rng = random.Random(master_rng.randint(0, 2**31))
        price_path = simulate_price_path(n_steps, rng=path_rng)
        for name, factory in configs.items():
            step_rng = random.Random(master_rng.randint(0, 2**31))
            results[name].append(run_path(factory, name, price_path, step_rng))

    return results


if __name__ == "__main__":
    results = run_monte_carlo(n_paths=20, n_steps=200)
    for name, paths in results.items():
        pnl = sum(p.net_pnl_token1 for p in paths) / len(paths)
        fees = sum(p.fees_token1 for p in paths) / len(paths)
        vol = sum(p.retail_volume_token1 for p in paths) / len(paths)
        fee_bps = sum(p.mean_fee_bps for p in paths) / len(paths)
        print(f"{name:20s} pnl={pnl:9.2f}  fees={fees:9.2f}  retail_vol={vol:9.1f}  mean_fee_bps={fee_bps:6.2f}")
