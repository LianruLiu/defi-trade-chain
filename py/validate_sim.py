"""
Runs identical random swap sequences through the deployed contract (via
web3 + eth-tester) and the pure-Python replica in pool_sim.py, and asserts
the reserves and fee state match exactly at every step. This is what
licenses using pool_sim.py for the Monte Carlo in lvr_experiment.py instead
of hitting the chain for every trade.

    pytest py/validate_sim.py -v
"""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from chain import LocalChain  # noqa: E402
from pool_sim import DynamicPoolSim, StaticPoolSim  # noqa: E402

ONE = 10**18


def test_static_pool_matches_chain():
    chain = LocalChain()
    lp = chain.w3.eth.accounts[1]
    trader = chain.w3.eth.accounts[2]
    t0 = chain.deploy_token("T0", "T0", lp, 10_000_000 * ONE)
    t1 = chain.deploy_token("T1", "T1", lp, 10_000_000 * ONE)
    pool = chain.deploy("StaticFeePool", t0.address, t1.address, 30)

    chain.approve(t0, lp, pool.address, 1_000_000 * ONE)
    chain.approve(t1, lp, pool.address, 1_000_000 * ONE)
    pool.functions.addLiquidity(1_000_000 * ONE, 1_000_000 * ONE).transact({"from": lp})

    sim = StaticPoolSim(reserve0=1_000_000 * ONE, reserve1=1_000_000 * ONE, fee_bps=30)

    t0.functions.mint(trader, 5_000_000 * ONE).transact({"from": chain.deployer})
    t1.functions.mint(trader, 5_000_000 * ONE).transact({"from": chain.deployer})
    chain.approve(t0, trader, pool.address, 5_000_000 * ONE)
    chain.approve(t1, trader, pool.address, 5_000_000 * ONE)

    random.seed(42)
    for _ in range(40):
        zero_for_one = random.random() < 0.5
        amount_in = random.randint(1, 20_000) * ONE
        chain_out = pool.functions.swap(zero_for_one, amount_in, 0).transact({"from": trader})
        sim_out = sim.swap(zero_for_one, amount_in)

        r0, r1 = pool.functions.getReserves().call()
        assert r0 == sim.reserve0
        assert r1 == sim.reserve1


def test_dynamic_pool_matches_chain():
    chain = LocalChain()
    lp = chain.w3.eth.accounts[1]
    trader = chain.w3.eth.accounts[2]
    t0 = chain.deploy_token("T0", "T0", lp, 10_000_000 * ONE)
    t1 = chain.deploy_token("T1", "T1", lp, 10_000_000 * ONE)

    params = (5, 5, 100, 2_000, 3 * 10**17)
    pool = chain.deploy("DynamicFeePool", t0.address, t1.address, *params)

    chain.approve(t0, lp, pool.address, 1_000_000 * ONE)
    chain.approve(t1, lp, pool.address, 1_000_000 * ONE)
    pool.functions.addLiquidity(1_000_000 * ONE, 1_000_000 * ONE).transact({"from": lp})

    sim = DynamicPoolSim(
        reserve0=1_000_000 * ONE, reserve1=1_000_000 * ONE,
        base_fee_bps=5, min_fee_bps=5, max_fee_bps=100,
        sensitivity=2_000, ewma_alpha=3 * 10**17,
    )

    t0.functions.mint(trader, 5_000_000 * ONE).transact({"from": chain.deployer})
    t1.functions.mint(trader, 5_000_000 * ONE).transact({"from": chain.deployer})
    chain.approve(t0, trader, pool.address, 5_000_000 * ONE)
    chain.approve(t1, trader, pool.address, 5_000_000 * ONE)

    random.seed(7)
    for i in range(40):
        zero_for_one = random.random() < 0.5
        amount_in = random.randint(1, 20_000) * ONE
        pool.functions.swap(zero_for_one, amount_in, 0).transact({"from": trader})
        sim.swap(zero_for_one, amount_in)

        r0, r1 = pool.functions.getReserves().call()
        assert r0 == sim.reserve0, f"reserve0 mismatch at step {i}"
        assert r1 == sim.reserve1, f"reserve1 mismatch at step {i}"
        assert pool.functions.currentFeeBps().call() == sim.current_fee_bps(), f"fee mismatch at step {i}"
        assert pool.functions.volEwma().call() == sim.vol_ewma, f"volEwma mismatch at step {i}"


if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", __file__, "-v"])
