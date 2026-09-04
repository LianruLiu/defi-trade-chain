// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./IERC20.sol";

/// Constant-product (x*y=k) two-token pool, Uniswap-V2-style reserve
/// accounting and LP share math, minus the router/factory/ERC20-LP-token
/// machinery that isn't relevant to the fee-mechanism question this repo
/// is about. Fee is left as a hook (`currentFeeBps`) so a static and a
/// flow-adaptive pool can share every other line of logic — the fee rule
/// is the only thing that differs between the two contracts that matter.
abstract contract AMMPool {
    IERC20 public immutable token0;
    IERC20 public immutable token1;

    uint256 public reserve0;
    uint256 public reserve1;
    uint256 public totalShares;
    mapping(address => uint256) public sharesOf;

    uint256 private locked; // reentrancy guard, 1 = unlocked, 2 = locked

    event LiquidityAdded(address indexed provider, uint256 amount0, uint256 amount1, uint256 shares);
    event LiquidityRemoved(address indexed provider, uint256 amount0, uint256 amount1, uint256 shares);
    event Swap(address indexed trader, bool zeroForOne, uint256 amountIn, uint256 amountOut, uint256 feeBps);

    modifier nonReentrant() {
        require(locked != 2, "reentrant");
        locked = 2;
        _;
        locked = 1;
    }

    constructor(address _token0, address _token1) {
        require(_token0 != _token1, "identical tokens");
        token0 = IERC20(_token0);
        token1 = IERC20(_token1);
        locked = 1;
    }

    /// Fee charged on the *input* leg of a swap, in basis points (1 = 0.01%).
    /// Implemented by StaticFeePool (constant) and DynamicFeePool (flow-adaptive).
    function currentFeeBps() public view virtual returns (uint256);

    /// Hook called after reserves are updated on a swap, so a subclass can
    /// update whatever state its fee rule depends on. No-op in the base pool.
    function _afterSwap() internal virtual {}

    /// Hook called once, right after the pool receives its first liquidity
    /// (i.e. once reserves and a price first exist). No-op in the base pool.
    function _afterFirstLiquidity() internal virtual {}

    function addLiquidity(uint256 amount0, uint256 amount1) external nonReentrant returns (uint256 shares) {
        require(amount0 > 0 && amount1 > 0, "zero amount");

        bool firstMint = totalShares == 0;
        if (firstMint) {
            shares = _sqrt(amount0 * amount1);
        } else {
            uint256 shares0 = (amount0 * totalShares) / reserve0;
            uint256 shares1 = (amount1 * totalShares) / reserve1;
            shares = shares0 < shares1 ? shares0 : shares1;
        }
        require(shares > 0, "insufficient liquidity minted");

        require(token0.transferFrom(msg.sender, address(this), amount0), "token0 transfer failed");
        require(token1.transferFrom(msg.sender, address(this), amount1), "token1 transfer failed");

        reserve0 += amount0;
        reserve1 += amount1;
        totalShares += shares;
        sharesOf[msg.sender] += shares;

        if (firstMint) _afterFirstLiquidity();

        emit LiquidityAdded(msg.sender, amount0, amount1, shares);
    }

    function removeLiquidity(uint256 shares) external nonReentrant returns (uint256 amount0, uint256 amount1) {
        require(shares > 0 && shares <= sharesOf[msg.sender], "invalid shares");

        amount0 = (shares * reserve0) / totalShares;
        amount1 = (shares * reserve1) / totalShares;
        require(amount0 > 0 && amount1 > 0, "insufficient liquidity burned");

        sharesOf[msg.sender] -= shares;
        totalShares -= shares;
        reserve0 -= amount0;
        reserve1 -= amount1;

        require(token0.transfer(msg.sender, amount0), "token0 transfer failed");
        require(token1.transfer(msg.sender, amount1), "token1 transfer failed");

        emit LiquidityRemoved(msg.sender, shares, amount0, amount1);
    }

    /// Swap an exact amount of one token in for the other. `zeroForOne`
    /// selects the direction (true: token0 in, token1 out).
    function swap(bool zeroForOne, uint256 amountIn, uint256 minAmountOut) external nonReentrant returns (uint256 amountOut) {
        require(amountIn > 0, "zero amount in");
        require(reserve0 > 0 && reserve1 > 0, "no liquidity");

        uint256 feeBps = currentFeeBps();
        uint256 amountInAfterFee = (amountIn * (10_000 - feeBps)) / 10_000;

        if (zeroForOne) {
            amountOut = (reserve1 * amountInAfterFee) / (reserve0 + amountInAfterFee);
            require(amountOut >= minAmountOut, "slippage");
            require(token0.transferFrom(msg.sender, address(this), amountIn), "token0 transfer failed");
            require(token1.transfer(msg.sender, amountOut), "token1 transfer failed");
            reserve0 += amountIn;
            reserve1 -= amountOut;
        } else {
            amountOut = (reserve0 * amountInAfterFee) / (reserve1 + amountInAfterFee);
            require(amountOut >= minAmountOut, "slippage");
            require(token1.transferFrom(msg.sender, address(this), amountIn), "token1 transfer failed");
            require(token0.transfer(msg.sender, amountOut), "token0 transfer failed");
            reserve1 += amountIn;
            reserve0 -= amountOut;
        }

        emit Swap(msg.sender, zeroForOne, amountIn, amountOut, feeBps);
        _afterSwap();
    }

    function getReserves() external view returns (uint256, uint256) {
        return (reserve0, reserve1);
    }

    /// Marginal price of token0 in units of token1, scaled by 1e18.
    function price() public view returns (uint256) {
        if (reserve0 == 0) return 0;
        return (reserve1 * 1e18) / reserve0;
    }

    function _sqrt(uint256 x) internal pure returns (uint256 y) {
        if (x == 0) return 0;
        uint256 z = (x + 1) / 2;
        y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
    }
}
