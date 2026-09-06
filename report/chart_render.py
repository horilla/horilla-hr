"""Server-side chart-to-PNG rendering for report exports (PDF + Excel).

Uses reportlab.graphics — already a pinned dependency via xhtml2pdf/pisa
(see requirements.txt), so this adds no new package requirement. Renders
the same bar/donut/line primitives the in-app charts use
(report/metrics/*.py's payload["charts"]) into standalone PNGs that get
embedded in the PDF export and, separately, backed by real openpyxl chart
objects in the Excel export (see report/export.py).
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any, Optional

from reportlab.graphics import renderPM
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Circle, Drawing
from reportlab.lib import colors

logger = logging.getLogger(__name__)

# Same brand palette as report/export.py's COLOR_PRIMARY, plus a few
# distinct hues for additional series — kept visually consistent with the
# in-app charts and the rest of the exported document.
# Single source of truth for chart colours. report/export.py derives the
# openpyxl (native Excel chart) palette from this list -- the two used to be
# duplicated literals in separate files linked only by a comment, so drift
# between the PDF charts and the Excel charts was a matter of time.
PALETTE_HEX = [
    "E54F38",  # coral — brand primary
    "2563EB",  # blue
    "15803D",  # green
    "7C3AED",  # violet
    "0D9488",  # teal
    "F59E0B",  # amber
]

PALETTE = [colors.HexColor(f"#{value}") for value in PALETTE_HEX]

# reportlab defaults to Times for all chart text. The exported document is set
# in Helvetica, so unset labels made every chart look pasted in from another
# system. Helvetica is a built-in Type 1 face, so this needs no font files.
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

WIDTH = 560
HEIGHT = 260
# Reserved column on the right for the legend, whenever one is drawn — keeps
# swatch+text inside the canvas instead of being clipped at the edge.
LEGEND_COL = 150


def render_chart_png(
    chart: dict[str, Any], width: int = WIDTH, height: int = HEIGHT
) -> Optional[bytes]:
    """Render one payload["charts"] entry to a PNG. Returns None if the
    chart has no plottable data — callers should skip it in that case."""
    categories = chart.get("categories") or []
    series = [s for s in (chart.get("series") or []) if s.get("data")]
    if not categories or not series:
        return None

    chart_type = (chart.get("type") or "bar").lower()
    try:
        if chart_type in ("donut", "pie"):
            drawing = _pie_drawing(categories, series[0], width, height)
        elif chart_type == "line":
            drawing = _line_drawing(categories, series, width, height)
        else:
            drawing = _bar_drawing(categories, series, width, height)

        buf = BytesIO()
        renderPM.drawToFile(drawing, buf, fmt="PNG", dpi=150)
        return buf.getvalue()
    except Exception:
        # A chart that fails to render used to return None, which callers
        # treat as "no data" -- so a genuine rendering failure surfaced on a
        # board document as "No data for the selected period". Log it so the
        # two are distinguishable, and still degrade to no image rather than
        # failing the whole export.
        logger.exception(
            "Chart render failed (type=%s, id=%s)",
            chart_type,
            chart.get("id") or "?",
        )
        return None


def _legend(pairs: list[tuple], x: float, y: float) -> Legend:
    legend = Legend()
    legend.x = x
    legend.y = y
    legend.alignment = "left"
    legend.fontName = FONT
    legend.fontSize = 8
    legend.boxAnchor = "nw"
    legend.dx = 8
    legend.dy = 8
    legend.dxTextSpace = 6
    legend.deltay = 14
    legend.columnMaximum = 12
    legend.colorNamePairs = pairs
    return legend


def _bar_drawing(categories, series, width, height) -> Drawing:
    drawing = Drawing(width, height)
    has_legend = len(series) > 1
    plot_width = width - LEGEND_COL - 70 if has_legend else width - 90

    chart = VerticalBarChart()
    chart.x = 55
    chart.y = 55
    chart.width = plot_width
    chart.height = height - 80
    chart.data = [[v or 0 for v in (s.get("data") or [])] for s in series]
    chart.categoryAxis.categoryNames = [str(c) for c in categories]
    chart.categoryAxis.labels.fontName = FONT
    chart.categoryAxis.labels.fontSize = 7
    if len(categories) > 6:
        chart.categoryAxis.labels.angle = 30
        chart.categoryAxis.labels.dx = -6
        chart.categoryAxis.labels.dy = -8
    chart.valueAxis.labels.fontName = FONT
    chart.valueAxis.labels.fontSize = 7

    # Negative values: valueMin pinned to 0 clipped bars that fell below the
    # axis (a bridge or variance chart draws them routinely), and category
    # labels sat on the axis line, printing on top of those bars. Let the
    # axis span the real range and drop the labels below the plot instead.
    flat = [v or 0 for s_ in series for v in (s_.get("data") or [])]
    has_negative = any(v < 0 for v in flat)
    if has_negative:
        span = max(abs(min(flat)), abs(max(flat))) or 1
        chart.valueAxis.valueMin = min(flat) - span * 0.1
        chart.valueAxis.valueMax = max(max(flat) + span * 0.1, 0)
        chart.categoryAxis.labels.dy = -10
        chart.categoryAxis.labelAxisMode = "low"
        chart.valueAxis.gridStrokeColor = colors.HexColor("#E5E7EB")
        chart.valueAxis.gridStrokeWidth = 0.5
        chart.valueAxis.visibleGrid = 1
    else:
        chart.valueAxis.valueMin = 0

    chart.barSpacing = 3
    chart.groupSpacing = 12
    chart.bars.strokeColor = None
    for i in range(len(series)):
        chart.bars[i].fillColor = PALETTE[i % len(PALETTE)]
    # A single series carrying negatives reads as one undifferentiated block
    # otherwise -- tint the negative bars so decreases are visible at a glance.
    if has_negative and len(series) == 1:
        for j, v in enumerate((series[0].get("data") or [])):
            if (v or 0) < 0:
                chart.bars[(0, j)].fillColor = colors.HexColor("#B91C1C")
    drawing.add(chart)

    if has_legend:
        pairs = [
            (PALETTE[i % len(PALETTE)], s.get("name") or f"Series {i + 1}")
            for i, s in enumerate(series)
        ]
        drawing.add(_legend(pairs, chart.x + plot_width + 20, height - 30))
    return drawing


def _pie_drawing(categories, series, width, height) -> Drawing:
    drawing = Drawing(width, height)
    values = [max(v or 0, 0) for v in (series.get("data") or [])]
    diameter = min(height - 60, 170)
    pie = Pie()
    pie.x = 30
    pie.y = (height - diameter) / 2
    pie.width = diameter
    pie.height = diameter
    pie.data = values
    # Percentage labels: a slice with no value forces the reader to eyeball
    # proportions off the legend. Shares under 5% are left unlabelled, since
    # the text collides with its neighbours at that size.
    total = sum(values) or 1
    pie.labels = [
        f"{(v / total * 100):.0f}%" if (v / total) >= 0.05 else "" for v in values
    ]
    pie.sideLabels = 0
    pie.simpleLabels = 1
    pie.slices.fontName = FONT
    pie.slices.fontSize = 7
    pie.slices.fontColor = colors.white
    pie.slices.labelRadius = 0.68
    pie.slices.strokeWidth = 1.2
    pie.slices.strokeColor = colors.white
    for i in range(len(values)):
        pie.slices[i].fillColor = PALETTE[i % len(PALETTE)]
    drawing.add(pie)

    # Donut, to match the in-app charts -- the printed artefact otherwise did
    # not look like what the user saw on screen. reportlab has no donut, so
    # punch the hub out with a page-coloured circle over the pie's centre.
    hub = Circle(
        pie.x + diameter / 2.0,
        pie.y + diameter / 2.0,
        diameter * 0.27,
        fillColor=colors.white,
        strokeColor=None,
    )
    drawing.add(hub)

    pairs = [
        (PALETTE[i % len(PALETTE)], str(categories[i]))
        for i in range(min(len(categories), len(values)))
    ]
    # Anchor the legend to the ring's own vertical centre rather than the top
    # of the canvas, so it reads as part of the figure instead of floating.
    legend_rows = len(pairs)
    legend_top = pie.y + diameter / 2.0 + min(legend_rows, 12) * 7
    drawing.add(_legend(pairs, pie.x + diameter + 26, legend_top))
    return drawing


def _line_drawing(categories, series, width, height) -> Drawing:
    drawing = Drawing(width, height)
    has_legend = len(series) > 1
    plot_width = width - LEGEND_COL - 70 if has_legend else width - 90

    chart = LinePlot()
    chart.x = 55
    chart.y = 45
    chart.width = plot_width
    chart.height = height - 75
    chart.data = [
        [(i, v or 0) for i, v in enumerate(s.get("data") or [])] for s in series
    ]
    chart.xValueAxis.valueMin = 0
    chart.xValueAxis.valueMax = max(len(categories) - 1, 1)
    chart.xValueAxis.valueSteps = list(range(len(categories))) or [0]
    labels = [str(c) for c in categories]
    chart.xValueAxis.labelTextFormat = lambda v: (
        labels[int(v)] if 0 <= int(v) < len(labels) else ""
    )
    chart.xValueAxis.labels.fontName = FONT
    chart.xValueAxis.labels.fontSize = 7
    chart.yValueAxis.labels.fontName = FONT
    chart.yValueAxis.labels.fontSize = 7
    for i in range(len(series)):
        chart.lines[i].strokeColor = PALETTE[i % len(PALETTE)]
        chart.lines[i].strokeWidth = 2.2
    drawing.add(chart)

    if has_legend:
        pairs = [
            (PALETTE[i % len(PALETTE)], s.get("name") or f"Series {i + 1}")
            for i, s in enumerate(series)
        ]
        drawing.add(_legend(pairs, chart.x + plot_width + 20, height - 30))
    return drawing
