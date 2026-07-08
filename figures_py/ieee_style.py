# ieee_style.py — shared IEEE Access figure style (import into every fig script)
import matplotlib as mpl

def apply_ieee_style():
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["STIXGeneral", "Times New Roman", "Nimbus Roman",
                       "Liberation Serif", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "axes.linewidth": 0.8,
        "lines.linewidth": 1.2,
        "errorbar.capsize": 2.5,
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,   # TrueType — IEEE requirement
        "ps.fonttype": 42,
    })

COL_W  = 3.5     # single column (in)
COL_W2 = 7.16    # double column (in)

# colorblind-safe, print-safe palette (accent + neutral gray)
GREEN_DARK = "#1b4d3e"   # retrieval fidelity / defender
GREEN_MID  = "#2e7d64"   # retrieval coverage
RED_DARK   = "#9e2b25"   # attacker / capacity
STEEL      = "#4c6d8c"   # agent structure (gray-blue, not pure blue)
GRAY       = "#7f7f7f"
INK        = "#222222"

def luminance(rgb):
    """Relative luminance of an RGB(A) tuple in [0,1]; <0.5 -> use white text."""
    r, g, b = rgb[0], rgb[1], rgb[2]
    return 0.299*r + 0.587*g + 0.114*b

def text_on(rgb):
    return "white" if luminance(rgb) < 0.5 else INK

def bracket(ax, x0, x1, y, text, dy=0.028, color=GRAY, fs=7, ink=INK, va="bottom", pad=0.012):
    """Endpoint-contrast bracket from x0..x1 at height y (down-ticks), text centered above."""
    ax.plot([x0, x0, x1, x1], [y-dy, y, y, y-dy], color=color, lw=0.8, clip_on=False, zorder=5)
    ax.text((x0+x1)/2.0, y+pad, text, ha="center", va=va, fontsize=fs, color=ink, zorder=6)
