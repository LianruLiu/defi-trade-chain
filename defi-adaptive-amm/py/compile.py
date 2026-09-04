"""
Compiles every .sol file under contracts/ with the vendored solc binary
(tools/solc — downloaded directly from the solidity GitHub releases page,
since binaries.soliditylang.org isn't reachable in this sandbox) and writes
ABI + bytecode to build/<ContractName>.json.

    python py/compile.py
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOLC = ROOT / "tools" / "solc"
CONTRACTS_DIR = ROOT / "contracts"
BUILD_DIR = ROOT / "build"


def compile_all():
    BUILD_DIR.mkdir(exist_ok=True)
    sol_files = sorted(CONTRACTS_DIR.rglob("*.sol"))

    cmd = [
        str(SOLC),
        "--combined-json", "abi,bin",
        "--optimize", "--optimize-runs", "200",
        "--base-path", str(ROOT),
        *[str(f) for f in sol_files],
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("solc compilation failed")

    output = json.loads(result.stdout)
    for full_name, data in output["contracts"].items():
        # full_name looks like "contracts/AMMPool.sol:AMMPool"
        contract_name = full_name.split(":")[-1]
        abi = data["abi"] if isinstance(data["abi"], list) else json.loads(data["abi"])
        (BUILD_DIR / f"{contract_name}.json").write_text(
            json.dumps({"abi": abi, "bytecode": data["bin"]}, indent=2)
        )
        print(f"compiled {contract_name}")


if __name__ == "__main__":
    compile_all()
