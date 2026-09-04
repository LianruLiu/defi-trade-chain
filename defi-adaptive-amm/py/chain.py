"""
Thin deployment/interaction layer on top of web3.py + eth-tester (a pure-
Python EVM — no Foundry/Ganache/Node needed, which matters in a sandbox
with no outbound access to those toolchains' install servers).

    chain = LocalChain()
    token0, token1 = chain.deploy_pair()
    pool = chain.deploy("StaticFeePool", token0.address, token1.address, 30)
"""

import json
from pathlib import Path

from eth_tester import EthereumTester
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

BUILD_DIR = Path(__file__).parent.parent / "build"


class LocalChain:
    def __init__(self):
        self._tester = EthereumTester()
        self.w3 = Web3(EthereumTesterProvider(self._tester))
        self.deployer = self.w3.eth.accounts[0]
        self.w3.eth.default_account = self.deployer

    def _artifact(self, name):
        return json.loads((BUILD_DIR / f"{name}.json").read_text())

    def deploy(self, contract_name, *ctor_args):
        art = self._artifact(contract_name)
        Contract = self.w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
        tx_hash = Contract.constructor(*ctor_args).transact()
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return self.w3.eth.contract(address=receipt.contractAddress, abi=art["abi"])

    def deploy_token(self, name, symbol, mint_to, amount):
        token = self.deploy("MockERC20", name, symbol)
        token.functions.mint(mint_to, amount).transact()
        return token

    def approve(self, token, owner, spender, amount):
        token.functions.approve(spender, amount).transact({"from": owner})

    def new_account(self, eth=0):
        acct = self.w3.eth.account.create()
        if eth:
            self.w3.eth.send_transaction(
                {"from": self.deployer, "to": acct.address, "value": self.w3.to_wei(eth, "ether")}
            )
        self._tester.add_account(acct.key.hex())
        return acct.address
