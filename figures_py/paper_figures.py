#!/usr/bin/env python3
"""paper_figures.py — the four result figures from results_cells.csv.

fig_06 capacity (win rate + decoy identification)   -> paper Fig. 5
fig_07 retrieval (fidelity dose-response + coverage) -> paper Fig. 6
fig_08 attacker-defender structure (2x2 heatmap)     -> paper Fig. 7
fig_09 token-normalized defender efficiency          -> paper Fig. 8

Reads ../results_cells.csv; writes PNG/PDF/SVG to ../figures/. Shared IEEE style in ieee_style.py."""
import csv, os, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm, LinearSegmentedColormap
from ieee_style import (apply_ieee_style, COL_W, COL_W2, GREEN_DARK, GREEN_MID,
                        RED_DARK, STEEL, GRAY, INK, text_on, bracket)
apply_ieee_style()

OUT = "../figures"; os.makedirs(OUT, exist_ok=True)
C = {r["cell"]: r for r in csv.DictReader(open("../results_cells.csv"))}
f = lambda c, k: float(C[c][k])
def err(cells, k, lo, hi):
    m = np.array([f(c, k) for c in cells])
    return np.vstack([m-[f(c, lo) for c in cells], [f(c, hi) for c in cells]-m])
def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(f"{OUT}/{name}.{ext}", bbox_inches="tight")
    plt.close(fig); print("  wrote", name)

# ============================ FIG 06 — capacity (vertical single column) ============================
cap = ["cap_0.5b", "cap_1.5b", "cap_7b", "cap_14b"]
cln = ["capclean_visible_0.5b", "capclean_visible_1.5b", "capclean_visible_7b", "capclean_visible_14b"]
x = [0, 1, 2, 3]; labs = ["0.5B", "1.5B", "7B", "14B"]
fig, (axA, axB) = plt.subplots(2, 1, figsize=(COL_W, 5.0), constrained_layout=True)

# (a) win
axA.axhline(0.5, ls=(0, (4, 2)), lw=0.8, color=GRAY, zorder=1)
axA.text(3.45, 0.5, "tie (0.5)", fontsize=6.5, color=GRAY, va="center", ha="right",
         bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"))   # white bbox breaks the dashed line
axA.errorbar(x, [f(c, "win_rate") for c in cap],
             yerr=err(cap, "win_rate", "win_ci_low", "win_ci_high"),
             fmt="o", ms=5, color=GREEN_DARK, mec=INK, mew=0.4, ecolor=GREEN_DARK, zorder=3)
bracket(axA, 0, 3, 0.945, r"$0.767\!\to\!0.463$   ($\Delta\,{-}0.304$)", color=GRAY, fs=7)   # raised clear of CI
axA.set_xticks(x); axA.set_xticklabels(labs); axA.set_ylim(0, 1.06); axA.set_xlim(-0.5, 3.5)
axA.set_ylabel("Defender win rate")
axA.set_title("(a) Belief-based defender win rate", fontsize=8, pad=3)

# (b) identification
axB.errorbar(x, [f(c, "ident_rate") for c in cln],
             yerr=err(cln, "ident_rate", "ident_ci_low", "ident_ci_high"),
             fmt="s", ms=5, color=RED_DARK, mec=INK, mew=0.4, ecolor=RED_DARK, zorder=3)
bracket(axB, 0, 3, 0.80, r"Cohen's $d=1.16$", color=GRAY, fs=7)
axB.text(3.5, 0.02, "separate arm (not pooled)", fontsize=6.5, style="italic",
         color=GRAY, ha="right", va="bottom")
axB.set_xticks(x); axB.set_xticklabels(labs); axB.set_ylim(0, 0.92); axB.set_xlim(-0.5, 3.5)
axB.set_xlabel("Attacker model size (billions of parameters)")
axB.set_ylabel("Decoy identification rate")
axB.set_title("(b) Explicit decoy identification", fontsize=8, pad=3)
save(fig, "fig_06")

# ============================ FIG 07 — retrieval (vertical single column) ============================
fig, (axA, axB) = plt.subplots(2, 1, figsize=(COL_W, 5.0), constrained_layout=True)
# (a) fidelity: true-scale dose axis {0,1,2,4}; controls in a left gutter as tick labels
dose = ["fid_poison", "fid_weak", "fid_mid", "fid_strong"]; dx = [0, 1, 2, 4]
axA.axvspan(-1.75, -0.45, color="0.93", zorder=0)
axA.errorbar(dx, [f(c, "win_rate") for c in dose],
             yerr=err(dose, "win_rate", "win_ci_low", "win_ci_high"),
             fmt="o-", ms=5, lw=1.3, color=GREEN_DARK, mec=INK, mew=0.4, ecolor=GREEN_DARK, zorder=3)
# controls (dose 0, hollow, unconnected)
axA.errorbar([-1.3], [f("fid_none", "win_rate")],
             yerr=[[f("fid_none","win_rate")-f("fid_none","win_ci_low")],[f("fid_none","win_ci_high")-f("fid_none","win_rate")]],
             fmt="D", ms=5, color=GRAY, mfc="white", mec=GRAY, ecolor=GRAY, zorder=3)
axA.errorbar([-0.8], [f("fid_filler", "win_rate")],
             yerr=[[f("fid_filler","win_rate")-f("fid_filler","win_ci_low")],[f("fid_filler","win_ci_high")-f("fid_filler","win_rate")]],
             fmt="^", ms=5, color=GRAY, mfc="white", mec=GRAY, ecolor=GRAY, zorder=3)
axA.annotate("poison", (0, f("fid_poison","win_rate")), textcoords="offset points",
             xytext=(3, -11), fontsize=6.5, color=GREEN_DARK)
axA.annotate("strong", (4, f("fid_strong","win_rate")), textcoords="offset points",
             xytext=(-2, 6), fontsize=6.5, color=GREEN_DARK, ha="right")
axA.text(0.97, 0.05, r"$r=0.952$", transform=axA.transAxes, ha="right", va="bottom", fontsize=7.5, color=INK)
axA.set_xticks([-1.3, -0.8, 0, 1, 2, 4])
axA.set_xticklabels(["none", "filler", "0", "1", "2", "4"])
axA.get_xticklabels()[0].set_color(GRAY); axA.get_xticklabels()[1].set_color(GRAY)
axA.set_xlim(-1.9, 4.4); axA.set_ylim(0.4, 1.0)
axA.set_xlabel("Useful snippets among top-4 (controls at left)")
axA.set_ylabel("Defender win rate")
axA.set_title("(a) Retrieval fidelity (dose-response)", fontsize=8, pad=3)
# (b) coverage
cov = ["cov_min", "cov_mid", "cov_full"]; cx = [0, 1, 2]
axB.errorbar(cx, [f(c, "win_rate") for c in cov],
             yerr=err(cov, "win_rate", "win_ci_low", "win_ci_high"),
             fmt="D-", ms=5, lw=1.3, color=GREEN_MID, mec=INK, mew=0.4, ecolor=GREEN_MID, zorder=3)
axB.set_xticks(cx); axB.set_xticklabels(["1", "5", "20"]); axB.set_ylim(0.4, 1.0); axB.set_xlim(-0.4, 2.4)
axB.set_xlabel("Corpus coverage (chunks per stage)")
axB.set_ylabel("Defender win rate")
axB.set_title("(b) Corpus coverage", fontsize=8, pad=3)
save(fig, "fig_07")

# ============================ FIG 08 — structure 2x2 heatmap ============================
order = [["SS", "SM"], ["MS", "MM"]]
W = np.array([[f(c, "win_rate") for c in row] for row in order])
cmap = LinearSegmentedColormap.from_list("winmap", [RED_DARK, "#f2e8d8", GREEN_DARK])
norm = TwoSlopeNorm(vmin=0.30, vcenter=0.5, vmax=0.80)
fig, ax = plt.subplots(figsize=(COL_W + 1.3, COL_W + 0.9), constrained_layout=True)
im = ax.imshow(W, cmap=cmap, norm=norm, aspect="auto")
for i, row in enumerate(order):
    for j, c in enumerate(row):
        win = f(c, "win_rate"); tc = text_on(cmap(norm(win)))   # explicit luminance rule
        ax.text(j, i-0.26, c, ha="center", fontsize=11, fontweight="bold", color=tc)
        ax.text(j, i-0.01, f"{win:.3f}", ha="center", fontsize=20, fontweight="bold", color=tc)
        ax.text(j, i+0.20, f"95% CI [{f(c,'win_ci_low'):.2f}, {f(c,'win_ci_high'):.2f}]",
                ha="center", fontsize=7.5, color=tc)
        ax.text(j, i+0.35, f"Def {f(c,'def_tokens_mean'):.0f} / Atk {f(c,'atk_tokens_mean'):.0f} tok",
                ha="center", fontsize=7.5, color=tc)
ax.set_xticks([0, 1]); ax.set_xticklabels(["Single", "Multi"])
ax.set_yticks([0, 1]); ax.set_yticklabels(["Single", "Multi"])
ax.set_xlabel("Defender organization"); ax.set_ylabel("Attacker organization")
ax.xaxis.set_label_position("top"); ax.xaxis.tick_top()
for sp in ax.spines.values(): sp.set_visible(False)
ax.set_xticks(np.arange(-.5, 2, 1), minor=True); ax.set_yticks(np.arange(-.5, 2, 1), minor=True)
ax.grid(which="minor", color="white", lw=3); ax.tick_params(which="minor", length=0)
cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
cb.set_label("Defender win rate", fontsize=8)
cb.set_ticks([0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
cb.set_ticklabels(["0.3", "0.4", "0.5 (tie)", "0.6", "0.7", "0.8"])   # single unified 0.5 tick
cb.ax.axhline(0.5, color="k", lw=1.2)                                 # tie reference line
save(fig, "fig_08")

# ============================ FIG 09 — efficiency, grouped by lever ============================
groups = [("Retrieval fidelity", ["fid_none", "fid_weak", "fid_mid", "fid_strong"], GREEN_DARK),
          ("Retrieval coverage", ["cov_min", "cov_mid", "cov_full"], GREEN_MID),
          ("Agent structure",    ["SS", "SM", "MS", "MM"], STEEL)]
disp = {"fid_none":"none","fid_weak":"weak","fid_mid":"mid","fid_strong":"strong",
        "cov_min":"cov 1","cov_mid":"cov 5","cov_full":"cov 20","SS":"SS","SM":"SM","MS":"MS","MM":"MM"}
# layout rows top->bottom, sort within group by efficiency desc
rows = []  # (ypos, cell, color)
y = 0.0; bands = []
XMAX = 12.0; ANNX = 11.7
for gname, cells, col in groups:
    cells = sorted(cells, key=lambda c: -f(c, "efficiency"))
    y0 = y
    for c in cells:
        rows.append((y, c, col)); y += 1
    bands.append((gname, y0 - 0.5, y - 0.5, col))
    y += 0.9  # gap between groups
ymax = max(hi for _, _, hi, _ in bands)
fig, ax = plt.subplots(figsize=(COL_W2*0.74, 0.40*len(rows) + 1.5), constrained_layout=True)
for k, (gname, lo, hi, col) in enumerate(bands):
    ax.axhspan(lo, hi, color=col, alpha=0.06, zorder=0)
    ax.text(0.15, lo-0.35, gname, va="center", ha="left",       # horizontal label in the gap above group
            fontsize=8, fontweight="bold", color=col)
for ypos, c, col in rows:
    e = f(c, "efficiency"); w = f(c, "win_rate")
    ax.barh(ypos, e, color=col, edgecolor=INK, lw=0.4, height=0.62, zorder=3)
    ax.text(e+0.12, ypos, disp[c], va="center", fontsize=7.5, color=INK)
    ax.text(ANNX, ypos, f"win {w:.2f}  ·  Def {f(c,'def_tokens_mean'):.0f}/Atk {f(c,'atk_tokens_mean'):.0f}",
            va="center", ha="right", fontsize=6.8, color="0.25")   # aligned annotation column
ax.set_yticks([]); ax.set_ylim(-1.2, ymax+0.3); ax.invert_yaxis()
ax.set_xlim(0, XMAX); ax.set_xticks([0, 2, 4, 6, 8])
ax.set_xlabel("Efficiency  =  defender wins per 1000 deception-side tokens")
ax.axvline(0, color=INK, lw=0.8)
ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.grid(axis="x", color="#E4E4E4", lw=0.5, zorder=1); ax.set_axisbelow(True)
save(fig, "fig_09")
print("DONE ->", OUT)
