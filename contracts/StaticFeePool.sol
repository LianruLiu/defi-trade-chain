// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./AMMPool.sol";

/// Fixed fee on every swap, regardless of flow — the Uniswap V2 baseline
/// this repo compares the adaptive pool against.
contract StaticFeePool is AMMPool {
    uint256 public immutable feeBps;

    constructor(address _token0, address _token1, uint256 _feeBps) AMMPool(_token0, _token1) {
        require(_feeBps < 10_000, "fee too high");
        feeBps = _feeBps;
    }

    function currentFeeBps() public view override returns (uint256) {
        return feeBps;
    }
}
