// Filled in after you run deploy/deploy_testnet.py — copy the addresses
// out of deploy/deployment.json. Kept as a separate file (not fetched
// from the backend) so this page still works if the backend is down;
// only historical charts need the backend, not the swap/read functionality.
const CONFIG = {
  chainId: 11155111, // Sepolia
  rpcUrl: "REPLACE_WITH_YOUR_SEPOLIA_RPC_URL", // used for read-only calls before wallet connects
  apiBase: "http://localhost:8000",
  etherscanBase: "https://sepolia.etherscan.io",

  token0: { address: "0xREPLACE", symbol: "dUSD", decimals: 18 },
  token1: { address: "0xREPLACE", symbol: "dETH", decimals: 18 },
  staticPool: "0xREPLACE",
  dynamicPool: "0xREPLACE",
};
