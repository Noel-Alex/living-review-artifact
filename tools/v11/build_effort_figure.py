"""Effort-model winner map (fig:effort) from evidence/v11-wpa/effort-dominance.json.

Run: python -I -B tools/v11/build_effort_figure.py   (from paper-drafts/, Python 3.12 for vendored matplotlib)
Each panel is the full 5^4 log-weight grid: outer cells index the silent-misplacement (x) and
missed re-check (y) weights; the 5x5 sub-cells inside index the unnecessary re-check weight (x)
and the flagged wrong placement weight (y). A lost anchor costs 1. Colour encodes the cheapest
method; luminance differs between methods so the map survives grayscale printing.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "evidence/v11-wpa/effort-dominance.json"
OUT = ROOT / "v11-professor-revision/generated"
sys.path.insert(0, str(ROOT / "tools/vendor"))
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

plt.rcParams.update({"font.family": "serif", "font.size": 7.5, "pdf.fonttype": 42,
                     "axes.spines.top": False, "axes.spines.right": False})
NAMES = {"cascade": "Cascade, default", "calibrated": r"Cascade, $\theta=0.5$", "cascade_v1": "Cascade v1",
         "tracker_adapter": "Contextual tracker", "quote_exact": "Exact quotation", "diff_drift": "Diff drift",
         "line_number": "Line number", "tie": "Tie"}
# Ordered dark to light so neighbouring methods differ in luminance.
SHADE = {"cascade": "#1b2a49", "calibrated": "#4a6896", "quote_exact": "#ababab", "cascade_v1": "#a08cb4",
         "tracker_adapter": "#e3ab55", "diff_drift": "#fbf3e0", "line_number": "#ffffff", "tie": "#b30000"}
ORDER = list(SHADE)


def tick(v: float) -> str:
    return f"{v:.0f}" if v >= 10 else f"{v:.2g}"


def winner_grid(regions, axes):
    ws, mi, fr, wr = (axes[k] for k in ("wrong_silent", "missed", "false_recheck", "wrong_with_recheck"))
    grid = [[0] * 25 for _ in range(25)]
    for r in regions:
        w = r["winners"][0] if len(r["winners"]) == 1 else "tie"
        col = ws.index(r["wrong_silent"]) * 5 + fr.index(r["false_recheck"])
        row = mi.index(r["missed"]) * 5 + wr.index(r["wrong_with_recheck"])
        grid[row][col] = ORDER.index(w)
    return grid


def main() -> None:
    raw = SRC.read_bytes()
    d = json.loads(raw)["data"]
    axes = d["axes"]
    panels = [("main", "all", "Controlled edits, main seed"), ("real", "all", "Real histories, all retained")]
    fig, axs = plt.subplots(1, 2, figsize=(7.1, 3.25), constrained_layout=True)
    used = set()
    cmap = ListedColormap([SHADE[k] for k in ORDER])
    for ax, (bench, sub, title) in zip(axs, panels):
        reg = d["regions"][bench][sub]
        grid = winner_grid(reg["regions"], axes)
        used |= {ORDER[v] for row in grid for v in row}
        ax.imshow(grid, origin="lower", cmap=cmap, vmin=-0.5, vmax=len(ORDER) - 0.5, interpolation="nearest")
        for b in range(1, 5):
            ax.axhline(b * 5 - 0.5, color="white", lw=1.2)
            ax.axvline(b * 5 - 0.5, color="white", lw=1.2)
        ticks = [2 + 5 * i for i in range(5)]
        ax.set_xticks(ticks, [tick(v) for v in axes["wrong_silent"]])
        ax.set_yticks(ticks, [tick(v) for v in axes["missed"]])
        ax.set_xlabel("weight of a silent misplacement")
        ax.set_ylabel("weight of a missed re-check")
        excluded = "" if "tracker_adapter" in reg["methods"] else " (tracker excluded)"
        ax.set_title(title + excluded, fontsize=7.5)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
    handles = [Patch(facecolor=SHADE[k], edgecolor="black", lw=0.4, label=NAMES[k]) for k in ORDER if k in used]
    fig.legend(handles=handles, loc="outside lower center", ncol=len(handles), frameon=False, fontsize=7)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "effort-v11.pdf")
    (OUT / "effort-v11-provenance.json").write_text(json.dumps(
        {"input": str(SRC.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(raw).hexdigest(),
         "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         "panels": [f"{b}/{s}" for b, s, _ in panels], "methods_shown": sorted(used)}, indent=2), encoding="utf-8")
    print("wrote effort-v11.pdf", sorted(used))


if __name__ == "__main__":
    main()
