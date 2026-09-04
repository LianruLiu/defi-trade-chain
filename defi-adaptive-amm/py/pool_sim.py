"""
Reimplements the exact integer arithmetic in AMMPool.sol / StaticFeePool.sol
/ DynamicFeePool.sol in pure Python. Not a separate model of "how an AMM
works" — every line here is the same formula as the Solidity, so that a
Monte Carlo run of a few hundred paths x a few thousand steps doesn't need
a few hundred thousand RPC calls into eth-tester. `validate_against_chain.py`
cross-checks this against the deployed bytecode on random swap sequences;
if that check ever fails, trust the chain, not this file.
"""

from dataclasses import dataclass, field

ONE = 10**18


def quote(reserve0: int, reserve1: int, fee_bps: int, zero_for_one: bool, amount_in: int) -> int:
    amount_in_after_fee = (amount_in * (10_000 - fee_bps)) // 10_000
    if zero_for_one:
        return (reserve1 * amount_in_after_fee) // (reserve0 + amount_in_after_fee)
    else:
        return (reserve0 * amount_in_after_fee) // (reserve1 + amount_in_after_fee)


@dataclass
class StaticPoolSim:
    reserve0: int
    reserve1: int
    fee_bps: int

    def current_fee_bps(self) -> int:
        return self.fee_bps

    def swap(self, zero_for_one: bool, amount_in: int) -> int:
        amount_out = quote(self.reserve0, self.reserve1, self.fee_bps, zero_for_one, amount_in)
        if zero_for_one:
            self.reserve0 += amount_in
            self.reserve1 -= amount_out
        else:
            self.reserve1 += amount_in
            self.reserve0 -= amount_out
        return amount_out

    def price(self) -> int:
        return (self.reserve1 * ONE) // self.reserve0


@dataclass
class DynamicPoolSim:
    reserve0: int
    reserve1: int
    base_fee_bps: int
    min_fee_bps: int
    max_fee_bps: int
    sensitivity: int
    ewma_alpha: int
    vol_ewma: int = 0
    price_last: int = field(default=0)

    def __post_init__(self):
        if self.price_last == 0:
            self.price_last = self.price()

    def current_fee_bps(self) -> int:
        fee = self.base_fee_bps + (self.sensitivity * self.vol_ewma) // ONE
        return max(self.min_fee_bps, min(self.max_fee_bps, fee))

    def swap(self, zero_for_one: bool, amount_in: int) -> int:
        fee_bps = self.current_fee_bps()
        amount_out = quote(self.reserve0, self.reserve1, fee_bps, zero_for_one, amount_in)
        if zero_for_one:
            self.reserve0 += amount_in
            self.reserve1 -= amount_out
        else:
            self.reserve1 += amount_in
            self.reserve0 -= amount_out

        p = self.price()
        diff = p - self.price_last if p > self.price_last else self.price_last - p
        rel_change = (diff * ONE) // self.price_last
        self.vol_ewma = (self.ewma_alpha * rel_change + (ONE - self.ewma_alpha) * self.vol_ewma) // ONE
        self.price_last = p
        return amount_out

    def price(self) -> int:
        return (self.reserve1 * ONE) // self.reserve0
