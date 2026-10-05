"""
eth-tester's chain lives in one process's memory — it can't be shared
across separate `deploy_testnet.py` / `indexer.py` / `uvicorn` processes
the way a real node (or Foundry's `anvil`) can over JSON-RPC. So this
test does all three steps in a single process, to validate the indexer
and API logic against real contract events before you run the real
multi-process flow (deploy_testnet.py -> anvil or Sepolia -> indexer.py
-> uvicorn backend.api:app) on your own machine.

    pytest backend/test_e2e_local.py -v -s
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "py"))
sys.path.insert(0, str(Path(__file__).parent.parent / "deploy"))

os.environ["USE_LOCAL_CHAIN"] = "1"

from chain import LocalChain  # noqa: E402
import deploy_testnet  # noqa: E402

ONE = 10**18
ROOT = Path(__file__).parent.parent


def test_deploy_simulate_index_and_serve(tmp_path, monkeypatch):
    # 1. deploy on a fresh local chain, same code path as the real script
    chain = LocalChain()
    deployment = deploy_testnet._deploy(chain.w3, chain.deployer, chain._artifact, sign_and_send=None)

    # 2. generate real swap activity so there's something to index
    static_art = chain._artifact("StaticFeePool")
    dynamic_art = chain._artifact("DynamicFeePool")
    static_pool = chain.w3.eth.contract(address=deployment["static_pool"], abi=static_art["abi"])
    dynamic_pool = chain.w3.eth.contract(address=deployment["dynamic_pool"], abi=dynamic_art["abi"])
    t0 = chain.w3.eth.contract(address=deployment["token0"]["address"], abi=chain._artifact("MockERC20")["abi"])

    trader = chain.w3.eth.accounts[2]
    t0.functions.mint(trader, 1_000_000 * ONE).transact({"from": chain.deployer})
    t0.functions.approve(static_pool.address, 1_000_000 * ONE).transact({"from": trader})
    t0.functions.approve(dynamic_pool.address, 1_000_000 * ONE).transact({"from": trader})

    for i in range(5):
        static_pool.functions.swap(True, (i + 1) * 100 * ONE, 0).transact({"from": trader})
        dynamic_pool.functions.swap(True, (i + 1) * 100 * ONE, 0).transact({"from": trader})

    # 3. run the indexer against this same in-memory chain
    import indexer
    db_path = tmp_path / "events.db"
    monkeypatch.setattr(indexer, "DB_PATH", db_path)
    conn = indexer.get_db()
    for label, key, art in (("static", "static_pool", static_art), ("dynamic", "dynamic_pool", dynamic_art)):
        n_swaps, n_add, n_remove = indexer.index_pool(
            chain.w3, conn, label, deployment[key], art["abi"], from_block=0, to_block=chain.w3.eth.block_number
        )
        assert n_swaps == 5, f"{label}: expected 5 swaps, indexed {n_swaps}"
    conn.close()

    # 4. point the API's DB and chain lookups at this same state and query it
    import api as api_module
    monkeypatch.setattr(api_module, "DB_PATH", db_path)
    api_module._LOCAL_CHAIN_SINGLETON["w3"] = chain.w3
    # deploy_testnet._deploy already wrote the real deploy/deployment.json
    # as a side effect (same as the real CLI flow), so the API's normal
    # ROOT/deploy/deployment.json read just works here.

    from fastapi.testclient import TestClient
    client = TestClient(api_module.app)

    resp = client.get("/api/swaps?pool=dynamic")
    assert resp.status_code == 200
    swaps = resp.json()
    assert len(swaps) == 5
    print(f"\n/api/swaps -> {len(swaps)} rows, fee_bps sequence: {[s['fee_bps'] for s in swaps]}")

    resp = client.get("/api/stats")
    assert resp.status_code == 200
    print(f"/api/stats -> {resp.json()}")

    resp = client.get("/api/live-state")
    assert resp.status_code == 200
    live = resp.json()
    print(f"/api/live-state -> {live}")
    assert live["dynamic"]["fee_bps"] > live["static"]["fee_bps"] or live["dynamic"]["fee_bps"] >= 5
