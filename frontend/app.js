// Minimal ABI fragments — only what this page actually calls. The full
// ABI lives in build/*.json for anything that needs it (the backend does).
const ERC20_ABI = [
  "function approve(address spender, uint256 amount) returns (bool)",
  "function balanceOf(address account) view returns (uint256)",
  "function mint(address to, uint256 amount)",
];
const POOL_ABI = [
  "function getReserves() view returns (uint256, uint256)",
  "function currentFeeBps() view returns (uint256)",
  "function swap(bool zeroForOne, uint256 amountIn, uint256 minAmountOut) returns (uint256)",
];

const ONE = 10n ** 18n;

let provider, signer, userAddress;
let readProvider = new ethers.JsonRpcProvider(CONFIG.rpcUrl);

const pools = {
  static: { address: CONFIG.staticPool, label: "static" },
  dynamic: { address: CONFIG.dynamicPool, label: "dynamic" },
};

function poolContract(name, runner) {
  return new ethers.Contract(pools[name].address, POOL_ABI, runner);
}
function tokenContract(address, runner) {
  return new ethers.Contract(address, ERC20_ABI, runner);
}

function fmtToken(raw, decimals = 18, dp = 4) {
  return Number(ethers.formatUnits(raw, decimals)).toLocaleString(undefined, { maximumFractionDigits: dp });
}

async function refreshPoolState() {
  for (const name of ["static", "dynamic"]) {
    try {
      const pool = poolContract(name, readProvider);
      const [reserves, fee] = await Promise.all([
        pool.getReserves(),
        pool.currentFeeBps(),
      ]);
      const [r0, r1] = reserves;
      const price = r0 > 0n ? Number(r1) / Number(r0) : 0;

      document.getElementById(`${name}Fee`).textContent = `${fee} bps (${(Number(fee) / 100).toFixed(2)}%)`;
      document.getElementById(`${name}Price`).textContent = price.toFixed(6);
      document.getElementById(`${name}Reserves`).textContent =
        `${fmtToken(r0)} ${CONFIG.token0.symbol} / ${fmtToken(r1)} ${CONFIG.token1.symbol}`;
    } catch (e) {
      console.error(`failed to read ${name} pool`, e);
      document.getElementById(`${name}Fee`).textContent = "error — check config.js addresses";
    }
  }
}

function setStatus(msg, kind = "") {
  const el = document.getElementById("swapStatus");
  el.textContent = msg;
  el.className = `status ${kind}`;
}

async function connectWallet() {
  if (!window.ethereum) {
    setStatus("No wallet found — install MetaMask.", "error");
    return;
  }
  provider = new ethers.BrowserProvider(window.ethereum);
  await provider.send("eth_requestAccounts", []);
  signer = await provider.getSigner();
  userAddress = await signer.getAddress();

  const network = await provider.getNetwork();
  if (Number(network.chainId) !== CONFIG.chainId) {
    setStatus(`Wrong network — switch your wallet to chain ${CONFIG.chainId} (Sepolia).`, "error");
  }

  document.getElementById("account").textContent = `${userAddress.slice(0, 6)}…${userAddress.slice(-4)}`;
  document.getElementById("connectBtn").textContent = "Connected";
  document.getElementById("connectBtn").disabled = true;
}

async function mintDemoTokens() {
  if (!signer) return setStatus("Connect your wallet first.", "error");
  setStatus("Minting demo tokens...");
  try {
    const amount = 10_000n * ONE;
    const t0 = tokenContract(CONFIG.token0.address, signer);
    const t1 = tokenContract(CONFIG.token1.address, signer);
    await (await t0.mint(userAddress, amount)).wait();
    await (await t1.mint(userAddress, amount * 10n)).wait(); // dETH is worth ~1000x dUSD in this demo pair
    setStatus("Minted 10,000 dUSD and 100,000 dETH to your address.", "success");
  } catch (e) {
    console.error(e);
    setStatus(`Mint failed: ${e.shortMessage || e.message}`, "error");
  }
}

async function doSwap() {
  if (!signer) return setStatus("Connect your wallet first.", "error");

  const poolName = document.getElementById("poolSelect").value;
  const zeroForOne = document.getElementById("directionSelect").value === "true";
  const amountStr = document.getElementById("amountInput").value;
  if (!amountStr || Number(amountStr) <= 0) return setStatus("Enter an amount.", "error");

  const amountIn = ethers.parseUnits(amountStr, 18);
  const tokenIn = zeroForOne ? CONFIG.token0.address : CONFIG.token1.address;

  try {
    setStatus("Approving...");
    const token = tokenContract(tokenIn, signer);
    await (await token.approve(pools[poolName].address, amountIn)).wait();

    setStatus("Swapping...");
    const pool = poolContract(poolName, signer);
    const tx = await pool.swap(zeroForOne, amountIn, 0);
    const receipt = await tx.wait();

    setStatus(`Swap confirmed: ${receipt.hash.slice(0, 10)}...`, "success");
    await refreshPoolState();
    await loadFeeChart();
  } catch (e) {
    console.error(e);
    setStatus(`Swap failed: ${e.shortMessage || e.message}`, "error");
  }
}

let feeChart;
async function loadFeeChart() {
  try {
    const resp = await fetch(`${CONFIG.apiBase}/api/swaps?pool=dynamic&limit=200`);
    if (!resp.ok) throw new Error(`backend returned ${resp.status}`);
    const swaps = await resp.json();

    const labels = swaps.map((s) => new Date(s.timestamp * 1000).toLocaleTimeString());
    const fees = swaps.map((s) => s.fee_bps);

    const ctx = document.getElementById("feeChart").getContext("2d");
    if (feeChart) feeChart.destroy();
    feeChart = new Chart(ctx, {
      type: "line",
      data: { labels, datasets: [{ label: "dynamic pool fee (bps)", data: fees, borderColor: "#4f9de6", tension: 0.2 }] },
      options: {
        scales: {
          x: { ticks: { color: "#6b7280" }, grid: { color: "#262d3d" } },
          y: { ticks: { color: "#6b7280" }, grid: { color: "#262d3d" } },
        },
        plugins: { legend: { labels: { color: "#c9d1d9" } } },
      },
    });
  } catch (e) {
    console.warn("chart load failed (is the backend running?)", e);
  }
}

document.getElementById("connectBtn").addEventListener("click", connectWallet);
document.getElementById("swapBtn").addEventListener("click", doSwap);
document.getElementById("mintBtn").addEventListener("click", mintDemoTokens);
document.getElementById("etherscanLink").href = `${CONFIG.etherscanBase}/address/${CONFIG.dynamicPool}`;

refreshPoolState();
loadFeeChart();
setInterval(refreshPoolState, 15_000);
