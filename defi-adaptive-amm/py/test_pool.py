"""
    pytest py/test_pool.py -v

Runs against the actual compiled bytecode on a local eth-tester chain —
not a Python re-implementation of the contract logic. Covers LP
accounting, swap correctness against the constant-product formula,
the invariant that reserves' product net of fees never decreases, and
that the dynamic-fee pool's fee actually moves with realized volatility
rather than just existing as an equation nobody checked at runtime.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from chain import LocalChain  # noqa: E402

ONE = 10**18


@pytest.fixture
def chain():
    return LocalChain()


@pytest.fixture
def tokens(chain):
    lp = chain.w3.eth.accounts[1]
    t0 = chain.deploy_token("Token0", "TK0", lp, 10_000_000 * ONE)
    t1 = chain.deploy_token("Token1", "TK1", lp, 10_000_000 * ONE)
    return t0, t1


def seed_pool(chain, pool, t0, t1, provider, amount0, amount1):
    chain.approve(t0, provider, pool.address, amount0)
    chain.approve(t1, provider, pool.address, amount1)
    pool.functions.addLiquidity(amount0, amount1).transact({"from": provider})


def fund_trader(chain, token, trader, amount):
    chain.w3.eth.default_account
    token.functions.mint(trader, amount).transact({"from": chain.deployer})


class TestStaticFeePool:
    def test_add_liquidity_initial_shares_is_sqrt(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        pool = chain.deploy("StaticFeePool", t0.address, t1.address, 30)  # 0.30%
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        assert pool.functions.totalShares().call() == 1_000_000 * ONE
        assert pool.functions.sharesOf(lp).call() == 1_000_000 * ONE

    def test_swap_matches_constant_product_formula(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        trader = chain.w3.eth.accounts[2]
        pool = chain.deploy("StaticFeePool", t0.address, t1.address, 30)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        amount_in = 1_000 * ONE
        r0, r1 = pool.functions.getReserves().call()
        expected_out = (r1 * (amount_in * 9970 // 10000)) // (r0 + (amount_in * 9970 // 10000))

        fund_trader(chain, t0, trader, amount_in)
        chain.approve(t0, trader, pool.address, amount_in)
        pool.functions.swap(True, amount_in, 0).transact({"from": trader})

        assert t1.functions.balanceOf(trader).call() == expected_out

    def test_k_never_decreases_across_swaps(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        trader = chain.w3.eth.accounts[2]
        pool = chain.deploy("StaticFeePool", t0.address, t1.address, 30)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        fund_trader(chain, t0, trader, 100_000 * ONE)
        fund_trader(chain, t1, trader, 100_000 * ONE)
        chain.approve(t0, trader, pool.address, 100_000 * ONE)
        chain.approve(t1, trader, pool.address, 100_000 * ONE)

        r0, r1 = pool.functions.getReserves().call()
        k_prev = r0 * r1
        import random
        random.seed(0)
        for _ in range(25):
            zero_for_one = random.random() < 0.5
            amount_in = random.randint(1, 5_000) * ONE
            pool.functions.swap(zero_for_one, amount_in, 0).transact({"from": trader})
            r0, r1 = pool.functions.getReserves().call()
            k = r0 * r1
            assert k >= k_prev, "constant product invariant violated net of fees"
            k_prev = k

    def test_remove_liquidity_returns_proportional_share(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        pool = chain.deploy("StaticFeePool", t0.address, t1.address, 30)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        shares = pool.functions.sharesOf(lp).call()
        pool.functions.removeLiquidity(shares // 2).transact({"from": lp})

        r0, r1 = pool.functions.getReserves().call()
        assert r0 == pytest.approx(500_000 * ONE, rel=1e-6)
        assert r1 == pytest.approx(500_000 * ONE, rel=1e-6)


class TestDynamicFeePool:
    def deploy_dynamic(self, chain, t0, t1):
        # base 5bps, floor 5bps, ceiling 100bps, sensitivity tuned so a
        # ~1% single-swap price move pushes the fee noticeably off the floor
        return chain.deploy(
            "DynamicFeePool",
            t0.address, t1.address,
            5,        # baseFeeBps
            5,        # minFeeBps
            100,      # maxFeeBps
            2_000,    # sensitivity: +2000 fee-bps per 1.0 (1e18) of EWMA vol
            3 * 10**17,  # ewmaAlpha = 0.3
        )

    def test_fee_at_floor_with_no_swap_history(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        pool = self.deploy_dynamic(chain, t0, t1)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        assert pool.functions.currentFeeBps().call() == 5

    def test_fee_rises_after_large_price_moving_swap(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        trader = chain.w3.eth.accounts[2]
        pool = self.deploy_dynamic(chain, t0, t1)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        fee_before = pool.functions.currentFeeBps().call()

        big_swap = 50_000 * ONE  # ~5% of pool depth, moves price materially
        fund_trader(chain, t0, trader, big_swap)
        chain.approve(t0, trader, pool.address, big_swap)
        pool.functions.swap(True, big_swap, 0).transact({"from": trader})

        fee_after = pool.functions.currentFeeBps().call()
        assert fee_after > fee_before

    def test_fee_decays_back_toward_floor_after_quiet_period(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        trader = chain.w3.eth.accounts[2]
        pool = self.deploy_dynamic(chain, t0, t1)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        fund_trader(chain, t0, trader, 300_000 * ONE)
        chain.approve(t0, trader, pool.address, 300_000 * ONE)
        pool.functions.swap(True, 50_000 * ONE, 0).transact({"from": trader})
        fee_spike = pool.functions.currentFeeBps().call()

        # a run of tiny swaps (near-zero price impact) should let the EWMA decay
        for _ in range(15):
            pool.functions.swap(True, 1 * ONE, 0).transact({"from": trader})
        fee_after_quiet = pool.functions.currentFeeBps().call()

        assert fee_after_quiet < fee_spike

    def test_fee_always_within_bounds(self, chain, tokens):
        t0, t1 = tokens
        lp = chain.w3.eth.accounts[1]
        trader = chain.w3.eth.accounts[2]
        pool = self.deploy_dynamic(chain, t0, t1)
        seed_pool(chain, pool, t0, t1, lp, 1_000_000 * ONE, 1_000_000 * ONE)

        fund_trader(chain, t0, trader, 2_100_000 * ONE)
        chain.approve(t0, trader, pool.address, 2_100_000 * ONE)

        import random
        random.seed(1)
        for _ in range(20):
            amount_in = random.randint(1, 100_000) * ONE
            pool.functions.swap(True, amount_in, 0).transact({"from": trader})
            fee = pool.functions.currentFeeBps().call()
            assert 5 <= fee <= 100
