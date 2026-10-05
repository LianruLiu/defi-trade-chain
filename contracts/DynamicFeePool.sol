// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./AMMPool.sol";

/// Fee scales with a rolling estimate of realized price volatility of the
/// pool itself, in place of a single fixed fee.
///
/// Motivation: under a constant-product AMM with a fixed fee, LPs lose
/// systematically to arbitrageurs whenever the external reference price
/// moves faster than the fee compensates for — the LVR problem (Milionis,
/// Moallemi, Roughgarden & Zhang, 2022/2023, "Automated Market Making and
/// Loss-Versus-Rebalancing"). A large, fast sequence of same-direction
/// swaps is exactly the arbitrageur's footprint: it moves the pool price
/// toward the external price in a way uninformed/retail flow doesn't.
/// Raising the fee when recent swaps have been moving the price a lot,
/// and lowering it when they haven't, taxes that footprint specifically
/// instead of taxing all volume at the same flat rate.
///
/// Mechanism: after every swap, compute the absolute relative change in
/// the pool's marginal price and fold it into an EWMA (`volEwma`, 1e18
/// fixed point). The fee is baseFeeBps + sensitivity * volEwma, clamped
/// to [minFeeBps, maxFeeBps]. This is a simple, auditable rule — not a
/// claim that it's the optimal one; see reports/research_note.md for
/// where it wins and where it doesn't, quantified in simulation.
contract DynamicFeePool is AMMPool {
    uint256 public immutable baseFeeBps;
    uint256 public immutable minFeeBps;
    uint256 public immutable maxFeeBps;
    uint256 public immutable sensitivity;   // fee bps added per 1e18 of volEwma
    uint256 public immutable ewmaAlpha;     // 1e18-scaled smoothing weight on the new observation

    uint256 public volEwma;    // 1e18-scaled EWMA of |relative price change| per swap
    uint256 public priceLast;  // 1e18-scaled, price() as of the last swap

    constructor(
        address _token0,
        address _token1,
        uint256 _baseFeeBps,
        uint256 _minFeeBps,
        uint256 _maxFeeBps,
        uint256 _sensitivity,
        uint256 _ewmaAlpha
    ) AMMPool(_token0, _token1) {
        require(_minFeeBps <= _baseFeeBps && _baseFeeBps <= _maxFeeBps, "fee bounds");
        require(_maxFeeBps < 10_000, "fee too high");
        require(_ewmaAlpha <= 1e18, "alpha > 1");
        baseFeeBps = _baseFeeBps;
        minFeeBps = _minFeeBps;
        maxFeeBps = _maxFeeBps;
        sensitivity = _sensitivity;
        ewmaAlpha = _ewmaAlpha;
    }

    function currentFeeBps() public view override returns (uint256) {
        uint256 fee = baseFeeBps + (sensitivity * volEwma) / 1e18;
        if (fee < minFeeBps) return minFeeBps;
        if (fee > maxFeeBps) return maxFeeBps;
        return fee;
    }

    function _afterFirstLiquidity() internal override {
        priceLast = price();
    }

    function _afterSwap() internal override {
        uint256 p = price();
        uint256 diff = p > priceLast ? p - priceLast : priceLast - p;
        uint256 relChange = (diff * 1e18) / priceLast;

        volEwma = (ewmaAlpha * relChange + (1e18 - ewmaAlpha) * volEwma) / 1e18;
        priceLast = p;
    }
}
