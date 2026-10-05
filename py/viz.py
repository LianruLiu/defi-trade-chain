import matplotlib.pyplot as plt
import numpy as np

import style
from lvr_experiment import make_dynamic, run_path, simulate_price_path

style.apply()

LABELS = {
    "static_5bps": "Static 5bps",
    "static_30bps": "Static 30bps",
    "dynamic_5_100bps": "Dynamic 5\u2013100bps",
}
COLORS = {
    "static_5bps": style.ACCENT_SELL,
    "static_30bps": style.MUTED,
    "dynamic_5_100bps": style.ACCENT_1,
}


def pnl_distribution(summary, path):
    fig, ax = plt.subplots(figsize=(9, 5))
    names = list(summary.keys())
    data = [summary[n]["pnl_raw"] for n in names]

    bp = ax.boxplot(
        data, vert=True, patch_artist=True, showfliers=False, widths=0.5,
        medianprops={"color": style.TEXT, "linewidth": 1.5},
    )
    for patch, name in zip(bp["boxes"], names):
        patch.set_facecolor(COLORS[name])
        patch.set_alpha(0.55)
        patch.set_edgecolor(COLORS[name])
    for element in ("whiskers", "caps"):
        for line in bp[element]:
            line.set_color(style.MUTED)

    ax.axhline(0, color=style.MUTED, lw=0.7, ls="--")
    ax.set_xticks(range(1, len(names) + 1))
    ax.set_xticklabels([LABELS[n] for n in names])
    ax.set_ylabel("LP net P&L vs. hold (token1 units)")
    ax.set_title("LP outcome distribution across 200 Monte Carlo price paths")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def pnl_vs_volume_tradeoff(summary, path):
    fig, ax = plt.subplots(figsize=(7.5, 6))
    for name, v in summary.items():
        ax.scatter(
            v["retail_vol_mean"], v["pnl_mean"], s=180,
            color=COLORS[name], edgecolor=style.BG, linewidth=1.2, zorder=3,
        )
        ax.annotate(
            LABELS[name], (v["retail_vol_mean"], v["pnl_mean"]),
            textcoords="offset points", xytext=(10, 6), fontsize=9, color=style.TEXT,
        )
    ax.set_xlabel("mean retail volume captured (token1 units)")
    ax.set_ylabel("mean LP net P&L vs. hold (token1 units)")
    ax.set_title("LP protection vs. retail volume captured — the actual tradeoff")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def fee_response_example(path, seed=99):
    import random
    rng = random.Random(seed)
    price_path = simulate_price_path(600, rng=rng)

    pool = make_dynamic()()
    from lvr_experiment import _Ledger, run_arbitrage_step, run_retail_step

    fee_hist, price_hist = [], []
    ledger = _Ledger()
    step_rng = random.Random(seed + 1)
    for t in range(1, len(price_path)):
        ext_price = price_path[t]
        fee_hist.append(pool.current_fee_bps())
        price_hist.append(ext_price)
        run_arbitrage_step(pool, ext_price, depth_cap=int(0.2 * 1_000_000 * 10**18), ledger=ledger)
        run_retail_step(pool, step_rng, base_size=200.0, elasticity_k=0.01, ext_price=ext_price, ledger=ledger)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 5.5), sharex=True, height_ratios=[1.3, 1], gridspec_kw={"hspace": 0.08}
    )
    ax1.plot(price_hist, color=style.ACCENT_2, lw=0.9)
    ax1.set_ylabel("external price")
    ax1.set_title("Dynamic fee response to a simulated price path (one Monte Carlo draw)")

    ax2.plot(fee_hist, color=style.ACCENT_1, lw=1.0)
    ax2.axhline(5, color=style.MUTED, lw=0.6, ls="--")
    ax2.axhline(100, color=style.MUTED, lw=0.6, ls="--")
    ax2.set_ylabel("fee (bps)")
    ax2.set_xlabel("step")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def summary_table_chart(summary, path):
    names = list(summary.keys())
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))

    metrics = [("pnl_mean", "mean P&L vs hold"), ("fees_mean", "mean fees earned"), ("retail_vol_mean", "mean retail volume")]
    for ax, (key, title) in zip(axes, metrics):
        vals = [summary[n][key] for n in names]
        bars = ax.bar(range(len(names)), vals, color=[COLORS[n] for n in names], alpha=0.85)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels([LABELS[n] for n in names], rotation=20, ha="right", fontsize=8)
        ax.set_title(title, fontsize=10)
        ax.axhline(0, color=style.MUTED, lw=0.6)

    fig.suptitle("Config comparison, mean across 200 paths", y=1.03, fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
