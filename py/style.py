import matplotlib.pyplot as plt
import matplotlib as mpl

BG = "#0e1117"
PANEL = "#151a24"
GRID = "#262d3d"
TEXT = "#c9d1d9"
ACCENT_BUY = "#2ecc71"
ACCENT_SELL = "#e74c3c"
ACCENT_1 = "#4f9de6"
ACCENT_2 = "#f2b134"
MUTED = "#6b7280"


def apply():
    mpl.rcParams.update(
        {
            "figure.facecolor": BG,
            "axes.facecolor": PANEL,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "text.color": TEXT,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "font.size": 10,
            "font.family": "DejaVu Sans",
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "legend.frameon": False,
            "legend.labelcolor": TEXT,
            "savefig.facecolor": BG,
            "savefig.dpi": 160,
            "figure.autolayout": False,
        }
    )
