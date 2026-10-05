"""
Read-only API over the SQLite cache indexer.py maintains. Three endpoints,
because that's all the frontend actually needs: current pool state (reads
live from chain, not cache — it's cheap and freshness matters here),
swap history (for the fee/price-over-time charts), and pool comparison
stats (aggregates over the cached swap history).

    uvicorn backend.api:app --reload --port 8000
"""

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from web3 import Web3

ROOT = Path(__file__).parent.parent
DB_PATH = Path(__file__).parent / "events.db"
ONE = 10**18

app = FastAPI(title="adaptive-amm-api")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_w3():
    import os
    if os.environ.get("USE_LOCAL_CHAIN"):
        return _cached_local_chain()
    return Web3(Web3.HTTPProvider(os.environ["SEPOLIA_RPC_URL"]))


_LOCAL_CHAIN_SINGLETON = {}


def _cached_local_chain():
    """Local-dev-only: eth-tester is in-memory per process, so this has to
    be a singleton or every request would spin up an empty chain with none
    of the demo's deployed contracts on it."""
    if "w3" not in _LOCAL_CHAIN_SINGLETON:
        import sys
        sys.path.insert(0, str(ROOT / "py"))
        from chain import LocalChain
        _LOCAL_CHAIN_SINGLETON["w3"] = LocalChain().w3
    return _LOCAL_CHAIN_SINGLETON["w3"]


@app.get("/api/pools")
def list_pools():
    deployment = json.loads((ROOT / "deploy" / "deployment.json").read_text())
    return deployment


@app.get("/api/swaps")
def swap_history(pool: str = Query("dynamic", pattern="^(static|dynamic)$"), limit: int = 500):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM swaps WHERE pool=? ORDER BY block_number DESC, log_index DESC LIMIT ?",
        (pool, limit),
    ).fetchall()
    return [dict(r) for r in rows][::-1]


@app.get("/api/stats")
def pool_stats():
    conn = db()
    out = {}
    for pool in ("static", "dynamic"):
        row = conn.execute(
            "SELECT COUNT(*) AS n_swaps, "
            "SUM(CAST(amount_in AS REAL)) AS total_volume_in, "
            "AVG(fee_bps) AS mean_fee_bps, "
            "MAX(fee_bps) AS max_fee_bps "
            "FROM swaps WHERE pool=?",
            (pool,),
        ).fetchone()
        out[pool] = dict(row)
    return out


@app.get("/api/live-state")
def live_state():
    """Reads current reserves/fee directly from chain — this one endpoint
    is intentionally not cache-backed, since a demo where the displayed
    fee lags the real one by a polling interval undermines the whole point."""
    deployment = json.loads((ROOT / "deploy" / "deployment.json").read_text())
    w3 = get_w3()
    out = {}
    for label, key in (("static", "static_pool"), ("dynamic", "dynamic_pool")):
        art_name = "StaticFeePool" if label == "static" else "DynamicFeePool"
        abi = json.loads((ROOT / "build" / f"{art_name}.json").read_text())["abi"]
        contract = w3.eth.contract(address=deployment[key], abi=abi)
        r0, r1 = contract.functions.getReserves().call()
        fee = contract.functions.currentFeeBps().call()
        out[label] = {
            "reserve0": str(r0), "reserve1": str(r1),
            "price": r1 / r0 if r0 else None,
            "fee_bps": fee,
        }
    return out
