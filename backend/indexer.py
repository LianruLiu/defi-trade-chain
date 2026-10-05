"""
Polls both pools for Swap/LiquidityAdded/LiquidityRemoved events and
writes them into a local SQLite file. This exists for exactly one reason:
charting historical fee/price/volume needs a "give me the last N events"
query, and re-scanning the whole chain from the frontend on every page
load doesn't scale even at demo traffic. It is not a general-purpose
backend — there's no user accounts, no writes other than what this
indexer produces, and the chain remains the source of truth (this file
is a cache, and rebuilding it from scratch by re-running the backfill is
always correct).

    python backend/indexer.py --backfill-from-block 0 --once   # one-time backfill
    python backend/indexer.py                                   # then poll continuously
"""

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

from web3 import Web3

ROOT = Path(__file__).parent.parent
DB_PATH = Path(__file__).parent / "events.db"
POLL_INTERVAL_S = 12  # ~ one Sepolia block

SCHEMA = """
CREATE TABLE IF NOT EXISTS swaps (
    pool TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    trader TEXT NOT NULL,
    zero_for_one INTEGER NOT NULL,
    amount_in TEXT NOT NULL,
    amount_out TEXT NOT NULL,
    fee_bps INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (tx_hash, log_index)
);
CREATE TABLE IF NOT EXISTS liquidity_events (
    pool TEXT NOT NULL,
    kind TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    provider TEXT NOT NULL,
    amount0 TEXT NOT NULL,
    amount1 TEXT NOT NULL,
    shares TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    PRIMARY KEY (tx_hash, log_index)
);
CREATE TABLE IF NOT EXISTS indexer_state (
    pool TEXT PRIMARY KEY,
    last_scanned_block INTEGER NOT NULL
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def load_config():
    deployment = json.loads((ROOT / "deploy" / "deployment.json").read_text())
    static_art = json.loads((ROOT / "build" / "StaticFeePool.json").read_text())
    dynamic_art = json.loads((ROOT / "build" / "DynamicFeePool.json").read_text())
    return deployment, static_art["abi"], dynamic_art["abi"]


def index_pool(w3, conn, pool_label, address, abi, from_block, to_block):
    contract = w3.eth.contract(address=address, abi=abi)

    swap_logs = contract.events.Swap().get_logs(from_block=from_block, to_block=to_block)
    add_logs = contract.events.LiquidityAdded().get_logs(from_block=from_block, to_block=to_block)
    remove_logs = contract.events.LiquidityRemoved().get_logs(from_block=from_block, to_block=to_block)

    for log in swap_logs:
        block = w3.eth.get_block(log["blockNumber"])
        conn.execute(
            "INSERT OR IGNORE INTO swaps VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                pool_label, log["blockNumber"], log["transactionHash"].hex(), log["logIndex"],
                log["args"]["trader"], int(log["args"]["zeroForOne"]),
                str(log["args"]["amountIn"]), str(log["args"]["amountOut"]),
                log["args"]["feeBps"], block["timestamp"],
            ),
        )

    for log in add_logs:
        block = w3.eth.get_block(log["blockNumber"])
        conn.execute(
            "INSERT OR IGNORE INTO liquidity_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                pool_label, "add", log["blockNumber"], log["transactionHash"].hex(), log["logIndex"],
                log["args"]["provider"], str(log["args"]["amount0"]), str(log["args"]["amount1"]),
                str(log["args"]["shares"]), block["timestamp"],
            ),
        )

    for log in remove_logs:
        block = w3.eth.get_block(log["blockNumber"])
        conn.execute(
            "INSERT OR IGNORE INTO liquidity_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                pool_label, "remove", log["blockNumber"], log["transactionHash"].hex(), log["logIndex"],
                log["args"]["provider"], str(log["args"]["amount0"]), str(log["args"]["amount1"]),
                str(log["args"]["shares"]), block["timestamp"],
            ),
        )

    conn.execute(
        "INSERT INTO indexer_state VALUES (?, ?) ON CONFLICT(pool) DO UPDATE SET last_scanned_block=excluded.last_scanned_block",
        (pool_label, to_block),
    )
    conn.commit()
    return len(swap_logs), len(add_logs), len(remove_logs)


def run(w3, deployment, static_abi, dynamic_abi, backfill_from_block=0, once=False):
    conn = get_db()
    pools = {
        "static": (deployment["static_pool"], static_abi),
        "dynamic": (deployment["dynamic_pool"], dynamic_abi),
    }

    while True:
        latest = w3.eth.block_number
        for label, (address, abi) in pools.items():
            row = conn.execute("SELECT last_scanned_block FROM indexer_state WHERE pool=?", (label,)).fetchone()
            from_block = (row[0] + 1) if row else backfill_from_block
            if from_block > latest:
                continue
            n_swaps, n_add, n_remove = index_pool(w3, conn, label, address, abi, from_block, latest)
            if n_swaps or n_add or n_remove:
                print(f"[{label}] blocks {from_block}-{latest}: +{n_swaps} swaps, +{n_add} adds, +{n_remove} removes")

        if once:
            break
        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-from-block", type=int, default=0)
    parser.add_argument("--once", action="store_true", help="scan once and exit, instead of polling forever")
    parser.add_argument("--local", action="store_true", help="point at local eth-tester instead of SEPOLIA_RPC_URL")
    args = parser.parse_args()

    deployment, static_abi, dynamic_abi = load_config()

    if args.local:
        import sys
        sys.path.insert(0, str(ROOT / "py"))
        from chain import LocalChain
        w3 = LocalChain().w3
    else:
        w3 = Web3(Web3.HTTPProvider(os.environ["SEPOLIA_RPC_URL"]))

    run(w3, deployment, static_abi, dynamic_abi, backfill_from_block=args.backfill_from_block, once=args.once)
