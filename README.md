# defi-trade-chain

## What is here

This repository currently contains a single project, vendored as a
subdirectory:

- [`defi-adaptive-amm/`](defi-adaptive-amm/) — the full adaptive-fee AMM
  research project: Solidity contracts (constant-product pool with a
  volatility-responsive fee), a Python replica + Monte Carlo LVR experiment,
  deployment scripts, indexer/API backend, and a vanilla-JS frontend.
  Start at [`defi-adaptive-amm/README.md`](defi-adaptive-amm/README.md).

## Note on the layout (for the repo owner)

The nested `defi-adaptive-amm/` folder duplicates the project that also
lives in the private `defi-adaptive-amm` repo (there as a stripped copy:
contracts + `py/` + `reports/` only). This copy here is the fuller one —
it additionally contains `backend/`, `deploy/`, and `frontend/`.

If the nesting was accidental, the clean options are: (a) flatten this
repo so the AMM project lives at the root, or (b) remove the nested
folder and keep the project in exactly one repo. Until then, treat this
copy as the reference for the full project.
