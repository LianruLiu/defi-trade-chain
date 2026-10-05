"""
Deploys StaticFeePool (30bps) and DynamicFeePool to whatever chain
SEPOLIA_RPC_URL points at, plus two MockERC20 tokens for the demo pair.

This sandbox has no route to Alchemy/Infura/Etherscan (network allowlist
is package registries only), so this script is written and tested against
the local eth-tester chain (`python deploy/deploy_testnet.py --local`) and
is meant to be run for real on your own machine:

    export SEPOLIA_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/<key>"
    export DEPLOYER_PRIVATE_KEY="0x..."   # a burner wallet, testnet only
    python deploy/deploy_testnet.py

Writes the deployed addresses to deploy/deployment.json, which both the
backend indexer and the frontend read to know what to point at.

Getting the two things this needs, if you don't have them yet:
  - RPC URL: free tier at alchemy.com or infura.io, create an app on
    "Ethereum Sepolia".
  - Sepolia ETH: sepoliafaucet.com or the faucet linked from your RPC
    provider's dashboard usually give enough for this (few cents worth
    of gas). Use a fresh wallet for this — never reuse a real wallet's
    private key for anything, testnet included, since it's still a live
    private key in an env var on your disk.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "py"))
from chain import LocalChain  # noqa: E402

ROOT = Path(__file__).parent.parent
ONE = 10**18


def deploy_local():
    """Runs against eth-tester so the deployment logic itself is exercised
    and verified without needing real testnet credentials."""
    chain = LocalChain()
    return _deploy(chain.w3, chain.deployer, chain._artifact, sign_and_send=None)


def deploy_real():
    from web3 import Web3
    from web3.middleware import geth_poa_middleware

    rpc_url = os.environ["SEPOLIA_RPC_URL"]
    private_key = os.environ["DEPLOYER_PRIVATE_KEY"]

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    account = w3.eth.account.from_key(private_key)
    w3.eth.default_account = account.address

    print(f"deployer: {account.address}")
    print(f"balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")

    def artifact(name):
        return json.loads((ROOT / "build" / f"{name}.json").read_text())

    return _deploy(w3, account.address, artifact, sign_and_send=(w3, account, private_key))


def _send(w3, account, private_key, tx_builder):
    """Signs and sends a transaction built by `tx_builder` when running
    against a real chain (as opposed to eth-tester, where .transact()
    from an unlocked test account is enough)."""
    tx = tx_builder.build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 3_000_000,
        "gasPrice": w3.eth.gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


def _deploy(w3, deployer, artifact_fn, sign_and_send):
    def deploy_contract(name, *ctor_args):
        art = artifact_fn(name)
        Contract = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
        if sign_and_send is None:
            tx_hash = Contract.constructor(*ctor_args).transact({"from": deployer})
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        else:
            _, account, pk = sign_and_send
            receipt = _send(w3, account, pk, Contract.constructor(*ctor_args))
        print(f"  {name}: {receipt.contractAddress}")
        return w3.eth.contract(address=receipt.contractAddress, abi=art["abi"])

    def call(contract_fn, *args):
        if sign_and_send is None:
            tx_hash = contract_fn(*args).transact({"from": deployer})
            return w3.eth.wait_for_transaction_receipt(tx_hash)
        _, account, pk = sign_and_send
        return _send(w3, account, pk, contract_fn(*args))

    print("deploying tokens ...")
    t0 = deploy_contract("MockERC20", "Demo USD", "dUSD")
    t1 = deploy_contract("MockERC20", "Demo ETH", "dETH")

    print("minting demo supply to deployer ...")
    call(t0.functions.mint, deployer, 10_000_000 * ONE)
    call(t1.functions.mint, deployer, 10_000_000 * ONE)

    print("deploying pools ...")
    static_pool = deploy_contract("StaticFeePool", t0.address, t1.address, 30)
    dynamic_pool = deploy_contract(
        "DynamicFeePool", t0.address, t1.address,
        5, 5, 100, 2_000, 3 * 10**17,
    )

    print("seeding initial liquidity (1000:1 demo ratio, 1000 dUSD : 1 dETH) ...")
    for pool in (static_pool, dynamic_pool):
        call(t0.functions.approve, pool.address, 1_000_000 * ONE)
        call(t1.functions.approve, pool.address, 1_000 * ONE)
        call(pool.functions.addLiquidity, 1_000_000 * ONE, 1_000 * ONE)

    deployment = {
        "token0": {"address": t0.address, "symbol": "dUSD"},
        "token1": {"address": t1.address, "symbol": "dETH"},
        "static_pool": static_pool.address,
        "dynamic_pool": dynamic_pool.address,
        "deployer": deployer,
    }
    (ROOT / "deploy" / "deployment.json").write_text(json.dumps(deployment, indent=2))
    print("\nwrote deploy/deployment.json")
    return deployment


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="deploy to a local eth-tester chain instead of SEPOLIA_RPC_URL")
    args = parser.parse_args()

    if args.local:
        deploy_local()
    else:
        deploy_real()
