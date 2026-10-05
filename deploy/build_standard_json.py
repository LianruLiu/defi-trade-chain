"""
Etherscan's "Solidity (Standard-Json-Input)" verification format wants
the exact solc input JSON that produced the bytecode — this builds that,
rather than hand-flattening imports into one file (which is what you'd
have to do without this, and is easy to get subtly wrong).

    python deploy/build_standard_json.py
    # -> deploy/standard_input.json
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOLC = ROOT / "tools" / "solc"
CONTRACTS_DIR = ROOT / "contracts"


def build():
    sol_files = sorted(CONTRACTS_DIR.rglob("*.sol"))
    sources = {}
    for f in sol_files:
        rel_path = f.relative_to(ROOT).as_posix()
        sources[rel_path] = {"content": f.read_text()}

    standard_input = {
        "language": "Solidity",
        "sources": sources,
        "settings": {
            "optimizer": {"enabled": True, "runs": 200},
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode"]}},
        },
    }

    out_path = ROOT / "deploy" / "standard_input.json"
    out_path.write_text(json.dumps(standard_input, indent=2))
    print(f"wrote {out_path}")

    # sanity-check it actually compiles the way compile.py's invocation does
    result = subprocess.run(
        [str(SOLC), "--standard-json"],
        input=json.dumps(standard_input), capture_output=True, text=True,
    )
    output = json.loads(result.stdout)
    if "errors" in output and any(e["severity"] == "error" for e in output["errors"]):
        for e in output["errors"]:
            print(e["formattedMessage"])
        raise RuntimeError("standard-json input does not compile cleanly")
    print("verified: standard-json input compiles cleanly with solc --standard-json")
    return standard_input


if __name__ == "__main__":
    build()
