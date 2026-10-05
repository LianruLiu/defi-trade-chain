"""
Submits the two pool contracts to Etherscan for source verification, using
the standard-json-input built by build_standard_json.py. Requires:

    export ETHERSCAN_API_KEY="..."   # free at etherscan.io/apis

Run after deploy_testnet.py has written deploy/deployment.json.

    python deploy/verify_etherscan.py

Not runnable in this sandbox (no route to api.etherscan.io) — written
against Etherscan's documented v2 API and left for you to run once the
contracts are actually on Sepolia. If it 400s, the most common cause is
a constructor-argument ABI-encoding mismatch — see the note in
`_encode_constructor_args` below before debugging further afield.
"""

import json
import os
import time
from pathlib import Path

import requests
from eth_abi import encode

ROOT = Path(__file__).parent.parent
API_URL = "https://api.etherscan.io/v2/api"
SEPOLIA_CHAIN_ID = 11155111


def _encode_constructor_args(contract_name: str, deployment: dict) -> str:
    """
    Etherscan needs the ABI-encoded constructor arguments as a hex string
    (no 0x prefix) appended to its verification request — it can't infer
    them from the deployed bytecode alone. These must match byte-for-byte
    what was actually passed at deploy time; if you change the pool
    parameters in deploy_testnet.py, update this function too.
    """
    t0 = deployment["token0"]["address"]
    t1 = deployment["token1"]["address"]

    if contract_name == "StaticFeePool":
        types, values = ["address", "address", "uint256"], [t0, t1, 30]
    elif contract_name == "DynamicFeePool":
        types = ["address", "address", "uint256", "uint256", "uint256", "uint256", "uint256"]
        values = [t0, t1, 5, 5, 100, 2_000, 3 * 10**17]
    else:
        raise ValueError(contract_name)

    return encode(types, values).hex()


def verify(contract_name: str, address: str, deployment: dict):
    standard_input = json.loads((ROOT / "deploy" / "standard_input.json").read_text())
    source_path = f"contracts/{contract_name}.sol"

    payload = {
        "apikey": os.environ["ETHERSCAN_API_KEY"],
        "chainid": SEPOLIA_CHAIN_ID,
        "module": "contract",
        "action": "verifysourcecode",
        "contractaddress": address,
        "sourceCode": json.dumps(standard_input),
        "codeformat": "solidity-standard-json-input",
        "contractname": f"{source_path}:{contract_name}",
        "compilerversion": "v0.8.24+commit.e11b9ed9",
        "constructorArguements": _encode_constructor_args(contract_name, deployment),
    }

    resp = requests.post(API_URL, data=payload, timeout=30)
    result = resp.json()
    print(f"{contract_name}: {result}")

    if result.get("status") == "1":
        guid = result["result"]
        return _poll_status(guid)
    return result


def _poll_status(guid: str, max_wait_s: int = 120):
    for _ in range(max_wait_s // 5):
        time.sleep(5)
        resp = requests.get(API_URL, params={
            "apikey": os.environ["ETHERSCAN_API_KEY"],
            "chainid": SEPOLIA_CHAIN_ID,
            "module": "contract",
            "action": "checkverifystatus",
            "guid": guid,
        })
        result = resp.json()
        print(f"  status: {result}")
        if result.get("result") not in ("Pending in queue",):
            return result
    return {"status": "0", "result": "timed out polling"}


if __name__ == "__main__":
    deployment = json.loads((ROOT / "deploy" / "deployment.json").read_text())
    verify("StaticFeePool", deployment["static_pool"], deployment)
    verify("DynamicFeePool", deployment["dynamic_pool"], deployment)
