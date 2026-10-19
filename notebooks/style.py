from pathlib import Path

import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.io as pio
from cycler import cycler
from IPython.display import HTML, display
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent.parent

# Surfaces and text. The text colours are the only colours used for words.
SURFACE, GRID = "#1a1a19", "#2c2c2a"
INK, INK_2, INK_3 = "#f0efec", "#c3c2b7", "#8d8c84"

# Series colours, in a fixed order. Soft and desaturated, so they are easy on the eyes on the dark surface.
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, VIOLET = (
    "#6f9fb0",
    "#d08a62",
    "#8bb174",
    "#cfb066",
    "#bb7d9a",
    "#9a92c8",
)
LINE = "#4a4946"  # hairlines that must still show on the surface

# One hue, dark to light, for amounts. Low values sink into the surface.
SEQ_COLORS = ["#26363b", "#3f5d68", "#6f9fb0", "#cfe0e6"]
SEQ = LinearSegmentedColormap.from_list("shelf", SEQ_COLORS)

# Plotly Express reads its colours from the default template, so register ours as the default.
SHELF = go.layout.Template(pio.templates["plotly_dark"])
SHELF.layout.colorway = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, VIOLET]
pio.templates["shelf"] = SHELF
pio.templates.default = "shelf"

_FONT = "'Segoe UI', Inter, system-ui, sans-serif"  # for the HTML cards
_have = {f.name for f in font_manager.fontManager.ttflist}
PLOT_FONT = next(
    (f for f in ("Segoe UI", "Inter", "Helvetica Neue") if f in _have), "DejaVu Sans"
)


def _compact(v, _=None):
    for size, tag in ((1e6, "M"), (1e3, "K")):
        if abs(v) >= size:
            return f"{v / size:g}{tag}"
    return f"{v:g}"


COMPACT = FuncFormatter(_compact)


def apply_style():
    """Dark charts: hairline grid, no box, thin marks, quiet text."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "figure.dpi": 130,
            "font.family": PLOT_FONT,
            "font.size": 10.5,
            "text.color": INK,
            "axes.labelcolor": INK_2,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "axes.edgecolor": GRID,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.prop_cycle": cycler(
                color=[BLUE, ORANGE, AQUA, YELLOW, MAGENTA, VIOLET]
            ),
            "lines.linewidth": 2,
            "lines.solid_capstyle": "round",
            "legend.frameon": False,
            "legend.labelcolor": INK_2,
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlepad": 24,
        }
    )


def finish(ax, title, subtitle=None, xlabel=None, ylabel=None, x_grid=False):
    """Title on the left, a quiet subtitle under it, no tick marks."""
    ax.set_title(title)
    if subtitle:
        ax.text(
            0,
            1.03,
            subtitle,
            transform=ax.transAxes,
            color=INK_3,
            fontsize=9.5,
            va="bottom",
        )
    ax.set_xlabel(xlabel or "")
    ax.set_ylabel(ylabel or "")
    ax.tick_params(length=0)
    ax.grid(x_grid, axis="x")
    return ax


def label_bars(ax, fmt="{:,.0f}", only_max=False, horizontal=False):
    """Write the value at the tip of the bars. Use only_max=True to label just the longest one."""
    bars = list(ax.patches)
    if only_max:
        bars = [
            max(bars, key=lambda p: p.get_width() if horizontal else p.get_height())
        ]
    for p in bars:
        if horizontal:
            ax.annotate(
                fmt.format(p.get_width()),
                (p.get_width(), p.get_y() + p.get_height() / 2),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                color=INK,
                fontsize=9.5,
            )
        else:
            ax.annotate(
                fmt.format(p.get_height()),
                (p.get_x() + p.get_width() / 2, p.get_height()),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                color=INK,
                fontsize=9.5,
            )


def interactive(
    fig, title, subtitle="", xlabel=None, ylabel=None, height=420, x=None, y=None
):
    """Plotly twin of finish(): the same dark look, with hover, zoom and legend toggling. x and y hold extra axis options. Only y has grid lines unless you pass showgrid."""
    fig.update_layout(
        template="shelf",
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        height=height,
        font={"family": _FONT, "color": INK_2, "size": 13},
        margin={"t": 100, "l": 70, "r": 40, "b": 70},
        hoverlabel={
            "bgcolor": "#262624",
            "bordercolor": LINE,
            "font": {"family": _FONT, "color": INK},
        },
        title={
            "text": f"<b>{title}</b><br><span style='font-size:13px;color:{INK_3}'>{subtitle}</span>",
            "x": 0,
            "xref": "container",
            "xanchor": "left",
            "pad": {"l": 30},
            "font": {"color": INK, "size": 19},
        },
    )
    for update, axis, label, extra in (
        (fig.update_xaxes, "x", xlabel, x),
        (fig.update_yaxes, "y", ylabel, y),
    ):
        update(
            title={"text": label, "font": {"color": INK_3, "size": 12}},
            gridcolor=GRID,
            zeroline=False,
            showline=False,
            ticks="",
            automargin=True,
            **{"showgrid": axis == "y", **(extra or {})},
        )
    fig.update_traces(marker_cornerradius=4, selector={"type": "bar"})
    fig.show(
        config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
    )


def banner(title, subtitle=""):
    """A large title card for the top of a notebook."""
    display(
        HTML(f"""<div style="font-family:{_FONT};padding:30px 34px;border-radius:18px;border:1px solid {GRID};
      background:radial-gradient(120% 140% at 0% 0%, #2f4a52 0%, #223338 28%, {SURFACE} 75%)">
      <div style="color:#a9c4cc;letter-spacing:.2em;font-size:11.5px;text-transform:uppercase">Shelfmate</div>
      <div style="color:{INK};font-size:34px;font-weight:700;margin-top:6px;line-height:1.15">{title}</div>
      <div style="color:{INK_2};font-size:15px;margin-top:8px;max-width:760px">{subtitle}</div></div>""")
    )


def section(number, title, blurb=""):
    """A numbered heading card for each part of the notebook."""
    display(
        HTML(f"""<div style="font-family:{_FONT};margin:30px 0 8px;padding:14px 18px;border-radius:14px;
      background:{SURFACE};border:1px solid {GRID};display:flex;align-items:center;gap:14px">
      <div style="min-width:38px;height:38px;border-radius:12px;background:{BLUE};color:#14191b;font-weight:700;
        display:flex;align-items:center;justify-content:center">{number}</div>
      <div><div style="color:{INK};font-size:21px;font-weight:700">{title}</div>
      <div style="color:{INK_3};font-size:13.5px">{blurb}</div></div></div>""")
    )


def stat_tiles(items):
    """A row of big numbers. items maps a label to its value."""
    tiles = "".join(
        f'<div style="flex:1;min-width:150px;padding:18px 20px;border-radius:14px;background:{SURFACE};border:1px solid {GRID}">'
        f'<div style="color:{INK_3};font-size:12px;letter-spacing:.08em;text-transform:uppercase">{k}</div>'
        f'<div style="color:{INK};font-size:28px;font-weight:700;margin-top:4px">{v}</div></div>'
        for k, v in items.items()
    )
    display(
        HTML(
            f'<div style="font-family:{_FONT};display:flex;gap:12px;flex-wrap:wrap;margin:10px 0">{tiles}</div>'
        )
    )


def takeaways(items, title="What we learned"):
    """A card with one short sentence per finding."""
    rows = "".join(
        f'<div style="display:flex;gap:12px;margin:10px 0"><div style="color:{BLUE};font-weight:700">&#9679;</div>'
        f'<div style="color:{INK_2};font-size:15px;line-height:1.5">{t}</div></div>'
        for t in items
    )
    display(
        HTML(f"""<div style="font-family:{_FONT};padding:22px 26px;border-radius:16px;background:{SURFACE};border:1px solid {GRID}">
      <div style="color:{INK};font-size:19px;font-weight:700;margin-bottom:6px">{title}</div>{rows}</div>""")
    )


def show(df, caption=None, n=10, formats=None):
    """Show a table with the same dark look."""
    styler = (
        df.head(n)
        .style.format(formats or {}, precision=3)
        .set_caption(caption or "")
        .hide(axis="index")
        .set_table_styles(
            [
                {
                    "selector": "",
                    "props": f"font-family:{_FONT};background:{SURFACE};color:{INK};border-collapse:collapse",
                },
                {
                    "selector": "caption",
                    "props": f"caption-side:top;text-align:left;color:{INK};font-size:15px;font-weight:700;padding:10px 4px",
                },
                {
                    "selector": "th",
                    "props": f"background:#22221f;color:{INK_2};text-align:left;padding:8px 14px;font-weight:600;border-bottom:1px solid {GRID}",
                },
                {
                    "selector": "td",
                    "props": f"padding:7px 14px;border-bottom:1px solid {GRID}",
                },
            ]
        )
    )
    display(styler)
