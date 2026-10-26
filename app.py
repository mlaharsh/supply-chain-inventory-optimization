"""Interactive inventory-control dashboard for Streamlit Community Cloud.

Reads the curated Tableau exports committed under ``outputs/tableau`` and
presents the executive overview, recovery queue, supplier scorecard, and SKU
drilldown. All figures are synthetic and generated from seed 42.
"""

from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "outputs" / "tableau"

st.set_page_config(
    page_title="Inventory Control · Supply Chain Analytics",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Visual system
# ---------------------------------------------------------------------------

NAVY = "#0b1f3a"
INK = "#182230"
MUTED = "#667085"
LINE = "#e4e7ec"
TEAL = "#0e7c86"
TEAL_LIGHT = "#7fc3c9"
TEAL_PALE = "#d9eef0"
AMBER = "#d97706"
ORANGE = "#dc6803"
RED = "#b42318"
GREEN = "#067647"
WHITE = "#ffffff"

ABC_COLORS = {"A": TEAL, "B": "#4f9ea6", "C": "#a7d7db"}
RISK_COLORS = {
    "Critical": RED,
    "High": ORANGE,
    "Watch": AMBER,
    "Low": GREEN,
}
RISK_ORDER = ["Critical", "High", "Watch", "Low"]

PLOT_CONFIG = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
}

CSS = f"""
<style>
  .block-container {{
    padding-top: 2.1rem;
    padding-bottom: 3rem;
    max-width: 1400px;
  }}
  [data-testid="stAppViewContainer"] {{ background: #f3f5f8; }}
  [data-testid="stHeader"] {{ background: rgba(243,245,248,.82); }}
  [data-testid="stSidebar"] {{
    background: {NAVY};
    border-right: 1px solid rgba(255,255,255,.06);
  }}
  [data-testid="stSidebar"] > div:first-child {{ padding-top: 1.1rem; }}
  [data-testid="stSidebar"] * {{ color: #e6eff8; }}
  [data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] .stCaption p {{
    color: #8ea9c4 !important;
  }}
  [data-testid="stSidebar"] a {{ color: #7de3d3 !important; }}
  [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.12); }}
  [data-testid="stSidebar"] [role="radiogroup"] label {{
    padding: 8px 10px;
    border-radius: 8px;
    transition: background .15s ease;
  }}
  [data-testid="stSidebar"] [role="radiogroup"] label:hover {{
    background: rgba(255,255,255,.07);
  }}
  [data-testid="stSidebar"] [role="radiogroup"] label p {{
    font-size: 12.5px;
    font-weight: 600;
  }}

  .side-brand {{
    display: flex; align-items: center; gap: 10px;
    padding: 0 2px 14px;
  }}
  .side-logo {{
    width: 34px; height: 34px; border-radius: 9px;
    background: rgba(45,212,191,.13);
    border: 1px solid rgba(45,212,191,.35);
    color: #7de3d3;
    display: grid; place-items: center;
    font-size: 10px; font-weight: 800; letter-spacing: .07em;
    flex: none;
  }}
  .side-brand strong {{
    display: block; color: #fff; font-size: 13px;
    letter-spacing: -.01em; line-height: 1.2;
  }}
  .side-brand small {{
    display: block; color: #8ea9c4; font-size: 9.5px;
    letter-spacing: .07em; text-transform: uppercase; margin-top: 3px;
  }}
  .side-label {{
    color: #6f93b3; font-size: 9px; font-weight: 700;
    letter-spacing: .14em; text-transform: uppercase;
    margin: 4px 0 6px;
  }}

  .page-head {{ margin: 0 0 18px; }}
  .page-head .eyebrow {{
    display: inline-flex; align-items: center; gap: 8px;
    color: {TEAL}; font-size: 10px; font-weight: 750;
    letter-spacing: .14em; text-transform: uppercase; margin-bottom: 8px;
  }}
  .page-head .eyebrow::before {{
    content: ""; width: 22px; height: 2px;
    background: {TEAL}; border-radius: 2px;
  }}
  .page-head h1 {{
    margin: 0; color: {NAVY}; font-size: clamp(27px, 3vw, 36px);
    line-height: 1.08; letter-spacing: -.035em; font-weight: 750;
  }}
  .page-head p {{
    margin: 9px 0 0; color: #475467; font-size: 13px;
    max-width: 820px; line-height: 1.6;
  }}

  .section-head {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 16px; margin: 22px 0 7px;
  }}
  .section-head h3 {{
    margin: 0; color: {NAVY}; font-size: 11.5px; font-weight: 750;
    letter-spacing: .08em; text-transform: uppercase;
  }}
  .section-head span {{ color: {MUTED}; font-size: 10.5px; }}

  .filter-label {{
    color: {MUTED}; font-size: 9px; font-weight: 750;
    letter-spacing: .14em; text-transform: uppercase; margin: -2px 0 2px;
  }}

  [data-testid="stMetric"] {{
    background: {WHITE};
    border: 1px solid {LINE};
    border-top: 3px solid {TEAL};
    border-radius: 11px;
    padding: 12px 15px 13px;
    box-shadow: 0 1px 2px rgba(11,31,58,.03);
    min-height: 100px;
  }}
  [data-testid="stMetricLabel"] p {{
    color: {MUTED} !important;
    font-size: 9.5px !important;
    font-weight: 700 !important;
    letter-spacing: .065em;
    text-transform: uppercase;
  }}
  [data-testid="stMetricValue"] {{
    color: {NAVY};
    font-size: 24px;
    font-weight: 750;
    letter-spacing: -.035em;
  }}
  [data-testid="stMetricDelta"] {{ font-size: 10px; }}

  .callout {{
    display: flex; gap: 12px; align-items: flex-start;
    background: {WHITE}; border: 1px solid {LINE};
    border-left: 4px solid {TEAL};
    border-radius: 10px; padding: 12px 15px; margin: 4px 0 6px;
  }}
  .callout.danger {{ border-left-color: {RED}; }}
  .callout.warn {{ border-left-color: {AMBER}; }}
  .callout .dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: {TEAL}; margin-top: 6px; flex: none;
  }}
  .callout.danger .dot {{ background: {RED}; }}
  .callout.warn .dot {{ background: {AMBER}; }}
  .callout p {{ margin: 0; color: #475467; font-size: 12px; line-height: 1.55; }}
  .callout strong {{ color: {NAVY}; }}

  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 9.5px; font-weight: 700; letter-spacing: .02em;
    margin-right: 5px; white-space: nowrap;
  }}
  .product-head {{
    background: {WHITE}; border: 1px solid {LINE}; border-radius: 12px;
    padding: 16px 18px; margin-bottom: 14px;
  }}
  .product-head h2 {{
    margin: 0; color: {NAVY}; font-size: 21px;
    letter-spacing: -.025em; line-height: 1.25;
  }}
  .product-head p {{
    margin: 5px 0 9px; color: {MUTED}; font-size: 11.5px;
  }}
  .product-meta {{ display: flex; flex-wrap: wrap; gap: 6px; }}

  .mini-note {{
    background: #f8fafc; border: 1px solid {LINE}; border-radius: 8px;
    padding: 9px 11px; color: {MUTED}; font-size: 10.5px; line-height: 1.55;
  }}
  .mini-note strong {{ color: {NAVY}; }}

  div[data-testid="stDataFrame"] {{ border-radius: 9px; overflow: hidden; }}
  .stDownloadButton button {{
    border-radius: 8px; border: 1px solid {LINE};
    font-size: 12px; font-weight: 600;
  }}
  [data-testid="stAppDeployButton"] {{ display: none; }}
  [data-testid="stDecoration"] {{ display: none; }}
  footer {{ visibility: hidden; }}
  #MainMenu {{ visibility: hidden; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

DATE_COLUMNS = {
    "inventory_overview": ["next_po_promised_date"],
    "abc_xyz_summary": [],
    "reorder_alerts": [],
    "supplier_performance": [],
    "purchase_order_lead_times": ["order_date", "promised_date", "received_date"],
    "inventory_snapshots": ["snapshot_date"],
    "weekly_demand": ["week_start", "week_end"],
    "monthly_demand_forecast": ["month_start", "forecast_month"],
    "forecast_accuracy": [],
    "demand_forecast": ["forecast_month"],
}


@st.cache_data(show_spinner="Loading the inventory snapshot…")
def load_data() -> dict[str, pd.DataFrame]:
    missing = [
        name
        for name in DATE_COLUMNS
        if not (DATA_DIR / f"{name}.csv").exists()
    ]
    if missing:
        raise FileNotFoundError(", ".join(f"{name}.csv" for name in missing))

    return {
        name: pd.read_csv(
            DATA_DIR / f"{name}.csv",
            parse_dates=DATE_COLUMNS[name],
        )
        for name in DATE_COLUMNS
    }


try:
    DATA = load_data()
except FileNotFoundError as exc:
    st.error(
        "The dashboard data snapshot is missing. Run the pipeline locally "
        "or restore the committed files under `outputs/tableau/`."
    )
    st.code("python -m inventory_opt.pipeline --regenerate", language="bash")
    st.caption(f"Missing: {exc}")
    st.stop()

OVERVIEW = DATA["inventory_overview"]
ABC_SUMMARY = DATA["abc_xyz_summary"]
SUPPLIERS = DATA["supplier_performance"]
PURCHASE_ORDERS = DATA["purchase_order_lead_times"]
SNAPSHOTS = DATA["inventory_snapshots"]
WEEKLY = DATA["weekly_demand"]
MONTHLY = DATA["monthly_demand_forecast"]
ACCURACY = DATA["forecast_accuracy"]
FORECAST = DATA["demand_forecast"]

AS_OF = pd.to_datetime(SNAPSHOTS["snapshot_date"]).max()
SKU_COUNT = len(OVERVIEW)
SUPPLIER_COUNT = OVERVIEW["supplier_name"].nunique()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def money(value: float, decimals: int = 0) -> str:
    if pd.isna(value):
        return "—"
    return f"${value:,.{decimals}f}"


def money_compact(value: float) -> str:
    if pd.isna(value):
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.1f}K"
    return f"${value:,.0f}"


def number(value: float, decimals: int = 0) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}"


def pct(value: float, decimals: int = 1) -> str:
    if pd.isna(value):
        return "—"
    return f"{value * 100:,.{decimals}f}%"


def signed_days(value: float) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:+,.1f} days"


def page_header(eyebrow: str, title: str, description: str) -> None:
    st.markdown(
        f'<div class="page-head"><div class="eyebrow">{html.escape(eyebrow)}</div>'
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(description)}</p></div>",
        unsafe_allow_html=True,
    )


def section_head(title: str, note: str = "") -> None:
    st.markdown(
        f'<div class="section-head"><h3>{html.escape(title)}</h3>'
        f"<span>{html.escape(note)}</span></div>",
        unsafe_allow_html=True,
    )


def callout(text_html: str, tone: str = "") -> None:
    st.markdown(
        f'<div class="callout {tone}"><span class="dot"></span>'
        f"<p>{text_html}</p></div>",
        unsafe_allow_html=True,
    )


def badge(text: str, background: str, color: str) -> str:
    return (
        f'<span class="badge" style="background:{background};color:{color}">'
        f"{html.escape(text)}</span>"
    )


def style_figure(
    fig: go.Figure,
    height: int = 300,
    legend: bool = False,
    top_margin: int = 10,
) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=10, t=top_margin, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Segoe UI, Inter, -apple-system, Arial, sans-serif",
            size=11,
            color="#344054",
        ),
        hoverlabel=dict(
            bgcolor=NAVY,
            bordercolor=NAVY,
            font=dict(color="white", size=11),
        ),
        showlegend=legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            font=dict(size=10),
        ),
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor=LINE,
        tickfont=dict(size=10),
        title_font=dict(size=10),
    )
    fig.update_yaxes(
        gridcolor=LINE,
        zeroline=False,
        tickfont=dict(size=10),
        title_font=dict(size=10),
    )
    return fig


def weighted_on_time(frame: pd.DataFrame) -> float:
    weight = frame["received_po_count"].fillna(0)
    if weight.sum() == 0:
        return float("nan")
    return float((frame["on_time_rate"] * weight).sum() / weight.sum())


def weighted_wape(frame: pd.DataFrame) -> float:
    actual = frame["actual_holdout_units"].sum()
    if actual == 0:
        return float("nan")
    return float(frame["abs_error_units"].sum() / actual)


def filter_frame(
    frame: pd.DataFrame,
    abc: list[str],
    xyz: list[str],
    suppliers: list[str],
    risk: list[str],
) -> pd.DataFrame:
    view = frame
    if abc:
        view = view[view["abc_class"].isin(abc)]
    if xyz:
        view = view[view["xyz_class"].isin(xyz)]
    if suppliers:
        view = view[view["supplier_name"].isin(suppliers)]
    if risk:
        view = view[view["risk_tier"].isin(risk)]
    return view.copy()


def portfolio_filters(key: str) -> tuple[list[str], list[str], list[str], list[str]]:
    with st.container(border=True):
        st.markdown('<div class="filter-label">Filter portfolio</div>', unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns([0.8, 0.8, 1.35, 1.15])
        abc = col1.multiselect(
            "ABC class",
            ["A", "B", "C"],
            key=f"{key}_abc",
            placeholder="All",
        )
        xyz = col2.multiselect(
            "XYZ class",
            ["X", "Y", "Z"],
            key=f"{key}_xyz",
            placeholder="All",
        )
        suppliers = col3.multiselect(
            "Supplier",
            sorted(OVERVIEW["supplier_name"].dropna().unique()),
            key=f"{key}_supplier",
            placeholder="All suppliers",
        )
        risk = col4.multiselect(
            "Risk tier",
            RISK_ORDER,
            key=f"{key}_risk",
            placeholder="All tiers",
        )
    return abc, xyz, suppliers, risk


def risk_badge_html(tier: str) -> str:
    color = RISK_COLORS.get(tier, MUTED)
    backgrounds = {
        "Critical": "#fee4e2",
        "High": "#ffead5",
        "Watch": "#fef0c7",
        "Low": "#d1fadf",
    }
    return badge(tier, backgrounds.get(tier, "#f2f4f7"), color)


# ---------------------------------------------------------------------------
# Page: Executive overview
# ---------------------------------------------------------------------------


def render_overview() -> None:
    page_header(
        "Executive overview",
        "Inventory control at a glance",
        "A weekly operating view of working capital, service risk, and supplier reliability. "
        "Every metric is derived from the same reproducible pipeline run.",
    )

    abc, xyz, suppliers, risk = portfolio_filters("overview")
    view = filter_frame(OVERVIEW, abc, xyz, suppliers, risk)

    if view.empty:
        st.warning("No SKUs match the current filters. Clear one or more filters to continue.")
        return

    total_value = view["current_inventory_value"].sum()
    average_value = view["avg_inventory_value_52w"].sum()
    annual_value = view["annual_consumption_value"].sum()
    high_risk = int(view["risk_tier"].isin(["High", "Critical"]).sum())
    lost_revenue = view["projected_lost_revenue_value"].sum()
    actions = int(view["reorder_required"].fillna(False).sum())
    supplier_view = (
        SUPPLIERS[SUPPLIERS["supplier_name"].isin(suppliers)]
        if suppliers
        else SUPPLIERS
    )
    otd = weighted_on_time(supplier_view)
    target_weight = supplier_view["received_po_count"].fillna(0)
    target_otd = (
        float((supplier_view["on_time_target_pct"] * target_weight).sum() / target_weight.sum())
        if target_weight.sum()
        else float("nan")
    )
    wape = weighted_wape(ACCURACY)

    metric_cols = st.columns(6)
    metric_cols[0].metric(
        "On-hand value",
        money(total_value),
        delta=f"{money(total_value - average_value)} vs 52-wk avg",
        delta_color="inverse",
        help="Current on-hand inventory at standard cost, compared with the 52-week average inventory value.",
    )
    metric_cols[1].metric(
        "Annual value",
        money(annual_value),
        help="Trailing 365-day units multiplied by standard cost (annual consumption value).",
    )
    metric_cols[2].metric(
        "At-risk SKUs",
        f"{high_risk} of {len(view)}",
        help=(
            "SKUs classified High or Critical by the Monte Carlo stockout model. "
            f"{actions} currently need a replenishment action."
        ),
    )
    metric_cols[3].metric(
        "Revenue at risk",
        money(lost_revenue),
        help="Projected lost sales value if available inventory is exhausted before the next receipt.",
    )
    metric_cols[4].metric(
        "Supplier on-time",
        pct(otd),
        delta=f"{pct(otd - target_otd)} vs target",
        help="Received purchase orders that arrived on or before the promised date, weighted by PO count.",
    )
    metric_cols[5].metric(
        "Forecast WAPE",
        pct(wape),
        help="Weighted absolute percentage error on the held-out final three months of history.",
    )

    top = view.sort_values("projected_lost_revenue_value", ascending=False).iloc[0]
    if top["projected_lost_revenue_value"] > 0:
        callout(
            f"<strong>{high_risk} SKUs</strong> are in the High/Critical risk band, representing "
            f"<strong>{money(lost_revenue)}</strong> of projected lost revenue. "
            f"The single largest exposure is <strong>{html.escape(str(top['sku']))} · "
            f"{html.escape(str(top['product_name']))}</strong> at "
            f"<strong>{money(top['projected_lost_revenue_value'])}</strong>.",
            tone="danger",
        )
    else:
        callout(
            "No High/Critical stockout risk in the current slice. "
            "Use the filters above to inspect the full portfolio.",
        )

    heat_col, capital_col = st.columns([1.45, 1], gap="medium")
    with heat_col:
        section_head("ABC-XYZ segmentation", "count of SKUs · share of annual consumption value")
        matrix = (
            view.groupby(["abc_class", "xyz_class"])
            .agg(
                sku_count=("sku", "count"),
                acv=("annual_consumption_value", "sum"),
                at_risk=("stockout_risk_flag", "sum"),
            )
            .reset_index()
        )
        acv_total = matrix["acv"].sum()
        z_values: list[list[float]] = []
        text_values: list[list[str]] = []
        custom: list[list[list[float]]] = []
        for a in ["A", "B", "C"]:
            z_row, text_row, custom_row = [], [], []
            for x in ["X", "Y", "Z"]:
                cell = matrix[(matrix["abc_class"] == a) & (matrix["xyz_class"] == x)]
                if cell.empty:
                    count, value, at_risk = 0, 0.0, 0
                else:
                    count = int(cell["sku_count"].iloc[0])
                    value = float(cell["acv"].iloc[0])
                    at_risk = int(cell["at_risk"].iloc[0])
                share = value / acv_total if acv_total else 0
                z_row.append(count)
                text_row.append(f"{count} SKUs<br>{share:.0%} of ACV")
                custom_row.append([value, at_risk])
            z_values.append(z_row)
            text_values.append(text_row)
            custom.append(custom_row)

        fig = go.Figure(
            go.Heatmap(
                x=["X · stable", "Y · variable", "Z · intermittent"],
                y=["A · high value", "B · mid value", "C · low value"],
                z=z_values,
                text=text_values,
                customdata=custom,
                texttemplate="%{text}",
                textfont=dict(size=11.5, color=NAVY),
                colorscale=[
                    [0.0, "#f7fbfc"],
                    [0.45, "#d9eef0"],
                    [1.0, "#8dcbd1"],
                ],
                zmin=0,
                zmax=max(max(row) for row in z_values) if z_values else 1,
                xgap=4,
                ygap=4,
                showscale=False,
                hovertemplate=(
                    "<b>%{y} / %{x}</b><br>"
                    "%{z} SKUs<br>"
                    "Annual consumption: $%{customdata[0]:,.0f}<br>"
                    "At risk: %{customdata[1]}"
                    "<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            height=292,
            margin=dict(l=8, r=8, t=8, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Segoe UI, Inter, Arial, sans-serif", size=10.5, color="#475467"),
            xaxis=dict(side="bottom", tickfont=dict(size=10.5, color="#475467")),
            yaxis=dict(autorange="reversed", tickfont=dict(size=10.5, color="#475467")),
        )
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with capital_col:
        section_head("Where capital sits", "current inventory value by ABC class")
        capital = (
            view.groupby("abc_class")["current_inventory_value"]
            .sum()
            .reindex(["A", "B", "C"])
            .fillna(0)
        )
        fig = go.Figure(
            go.Pie(
                labels=capital.index,
                values=capital.values,
                hole=0.63,
                marker=dict(
                    colors=[ABC_COLORS["A"], ABC_COLORS["B"], ABC_COLORS["C"]],
                    line=dict(color=WHITE, width=2),
                ),
                textinfo="label+percent",
                textposition="inside",
                insidetextorientation="horizontal",
                hovertemplate="<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>",
            )
        )
        fig.add_annotation(
            text=f"<b>{money(total_value)}</b><br><span style='font-size:9px;color:#667085'>ON HAND</span>",
            showarrow=False,
            font=dict(size=15, color=NAVY),
        )
        fig.update_layout(
            height=292,
            margin=dict(l=8, r=8, t=8, b=8),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Segoe UI, Inter, Arial, sans-serif", size=10.5),
            showlegend=False,
        )
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    section_head("Planner action queue", "ranked by projected lost revenue · top 8")
    queue = view[view["reorder_required"].fillna(False)].sort_values(
        "projected_lost_revenue_value", ascending=False
    )
    queue = queue.head(8)
    if queue.empty:
        st.info("No SKU in this slice requires replenishment right now.")
    else:
        queue_view = queue[
            [
                "risk_tier",
                "sku",
                "product_name",
                "supplier_name",
                "current_stock_units",
                "dynamic_rop_target_units",
                "suggested_order_units",
                "projected_lost_revenue_value",
            ]
        ]
        st.dataframe(
            queue_view,
            hide_index=True,
            width="stretch",
            height=305,
            column_config={
                "risk_tier": st.column_config.TextColumn("Risk", width="small"),
                "sku": st.column_config.TextColumn("SKU", width="small"),
                "product_name": st.column_config.TextColumn("Product", width="medium"),
                "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
                "current_stock_units": st.column_config.NumberColumn(
                    "On hand", format="%.0f", width="small"
                ),
                "dynamic_rop_target_units": st.column_config.NumberColumn(
                    "ROP", format="%.0f", width="small"
                ),
                "suggested_order_units": st.column_config.NumberColumn(
                    "Order", format="%.0f", width="small"
                ),
                "projected_lost_revenue_value": st.column_config.NumberColumn(
                    "At risk", format="$%.0f", width="small"
                ),
            },
        )

    supplier_col, exposure_col = st.columns(2, gap="medium")
    with supplier_col:
        section_head("Lowest on-time suppliers", "diamond = target")
        supplier_chart = SUPPLIERS.sort_values("on_time_rate").head(8).copy()
        bar_colors = [
            RED
            if row["on_time_rate"] < row["on_time_target_pct"] - 0.05
            else AMBER
            if row["on_time_rate"] < row["on_time_target_pct"]
            else TEAL
            for _, row in supplier_chart.iterrows()
        ]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=supplier_chart["on_time_rate"] * 100,
                y=supplier_chart["supplier_name"],
                orientation="h",
                marker=dict(color=bar_colors, cornerradius=3),
                text=[f"{v:.0%}" for v in supplier_chart["on_time_rate"]],
                textposition="inside",
                insidetextanchor="start",
                textfont=dict(size=9.5, color=WHITE),
                hovertemplate="<b>%{y}</b><br>On-time: %{x:.1f}%<extra></extra>",
                name="On-time rate",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=supplier_chart["on_time_target_pct"] * 100,
                y=supplier_chart["supplier_name"],
                mode="markers",
                marker=dict(symbol="diamond", size=7, color=NAVY, line=dict(width=0)),
                hovertemplate="<b>%{y}</b><br>Target: %{x:.1f}%<extra></extra>",
                name="Target",
            )
        )
        style_figure(fig, height=300, legend=False)
        fig.update_xaxes(range=[0, 108], ticksuffix="%", showgrid=True, gridcolor="#f2f4f7")
        fig.update_layout(bargap=0.42)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with exposure_col:
        section_head("Largest revenue exposure", "SKU-level projected lost sales")
        exposure = (
            view[view["projected_lost_revenue_value"] > 0]
            .nlargest(8, "projected_lost_revenue_value")
            .sort_values("projected_lost_revenue_value")
        )
        if exposure.empty:
            st.info("No projected revenue exposure in this slice.")
        else:
            fig = go.Figure(
                go.Bar(
                    x=exposure["projected_lost_revenue_value"],
                    y=exposure["sku"],
                    orientation="h",
                    marker=dict(
                        color=[
                            RISK_COLORS.get(tier, MUTED)
                            for tier in exposure["risk_tier"]
                        ],
                        cornerradius=3,
                    ),
                    text=[money_compact(v) for v in exposure["projected_lost_revenue_value"]],
                    textposition="outside",
                    textfont=dict(size=9, color="#475467"),
                    customdata=exposure[["product_name", "risk_tier"]],
                    hovertemplate=(
                        "<b>%{y}</b> · %{customdata[0]}<br>"
                        "Risk: %{customdata[1]}<br>"
                        "Exposure: $%{x:,.0f}<extra></extra>"
                    ),
                )
            )
            style_figure(fig, height=300)
            fig.update_xaxes(
                tickprefix="$",
                tickformat=",.0f",
                showgrid=True,
                gridcolor="#f2f4f7",
                range=[0, exposure["projected_lost_revenue_value"].max() * 1.25],
            )
            fig.update_layout(bargap=0.45, margin=dict(l=8, r=10, t=10, b=8))
            st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    section_head("Inventory value trend", "weekly snapshots · 24 months")
    trend = (
        SNAPSHOTS.groupby("snapshot_date", as_index=False)
        .agg(inventory_value=("inventory_value", "sum"))
        .sort_values("snapshot_date")
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend["snapshot_date"],
            y=trend["inventory_value"],
            mode="lines",
            line=dict(color=TEAL, width=2.4),
            fill="tozeroy",
            fillcolor="rgba(14,124,134,.08)",
            hovertemplate="%{x|%d %b %Y}<br><b>$%{y:,.0f}</b><extra></extra>",
            name="Inventory value",
        )
    )
    trailing_avg = trend["inventory_value"].tail(52).mean()
    fig.add_hline(
        y=trailing_avg,
        line_dash="dot",
        line_color="#98a2b3",
        annotation_text=f"52-wk avg {money(trailing_avg)}",
        annotation_position="top left",
        annotation_font=dict(size=9, color=MUTED),
    )
    style_figure(fig, height=260)
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    st.caption(
        f"Synthetic dataset · seed 42 · as of {AS_OF:%d %b %Y} · "
        "values are decision support, not a financial statement."
    )


# ---------------------------------------------------------------------------
# Page: Reorder queue
# ---------------------------------------------------------------------------


def render_reorder_queue() -> None:
    page_header(
        "Reorder queue",
        "Turn risk into a purchase decision",
        "SKUs whose inventory position is below the forecast-driven reorder point, "
        "ranked by revenue exposure. Suggested quantities respect minimum order quantities.",
    )

    with st.container(border=True):
        st.markdown('<div class="filter-label">Queue controls</div>', unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1.25, 1.25, 1])
        risk_filter = col1.multiselect(
            "Risk tier",
            RISK_ORDER,
            default=["Critical", "High"],
            key="queue_risk",
        )
        statuses = sorted(OVERVIEW["reorder_status"].dropna().unique())
        status_filter = col2.multiselect(
            "Reorder status",
            statuses,
            key="queue_status",
            placeholder="All statuses",
        )
        action_only = col3.toggle(
            "Action required only",
            value=True,
            key="queue_action_only",
        )

    queue = OVERVIEW.copy()
    if risk_filter:
        queue = queue[queue["risk_tier"].isin(risk_filter)]
    if status_filter:
        queue = queue[queue["reorder_status"].isin(status_filter)]
    if action_only:
        queue = queue[queue["reorder_required"].fillna(False)]

    queue = queue.sort_values(
        ["projected_lost_revenue_value", "risk_rank"],
        ascending=[False, False],
    )

    metric_cols = st.columns(5)
    metric_cols[0].metric("SKUs in view", number(len(queue)))
    metric_cols[1].metric(
        "Need action",
        number(queue["reorder_required"].fillna(False).sum()),
    )
    metric_cols[2].metric(
        "Units to order",
        number(queue.loc[queue["reorder_required"].fillna(False), "suggested_order_units"].sum()),
    )
    metric_cols[3].metric(
        "Revenue at risk",
        money(queue["projected_lost_revenue_value"].sum()),
    )
    metric_cols[4].metric(
        "Critical SKUs",
        number((queue["risk_tier"] == "Critical").sum()),
    )

    if queue.empty:
        st.info(
            "No SKUs match this queue. Widen the risk or status filters, or turn off "
            "“Action required only”."
        )
        return

    chart_col, policy_col = st.columns([1.25, 1], gap="medium")
    with chart_col:
        section_head("Revenue exposure by SKU", "top 12 in the current queue")
        chart_data = queue.nlargest(12, "projected_lost_revenue_value").sort_values(
            "projected_lost_revenue_value"
        )
        fig = go.Figure(
            go.Bar(
                x=chart_data["projected_lost_revenue_value"],
                y=chart_data["sku"],
                orientation="h",
                marker=dict(
                    color=[RISK_COLORS.get(t, MUTED) for t in chart_data["risk_tier"]],
                    cornerradius=3,
                ),
                text=[money_compact(v) for v in chart_data["projected_lost_revenue_value"]],
                textposition="outside",
                textfont=dict(size=9, color="#475467"),
                customdata=chart_data[["product_name", "risk_tier", "reorder_status"]],
                hovertemplate=(
                    "<b>%{y}</b> · %{customdata[0]}<br>"
                    "Risk: %{customdata[1]} · %{customdata[2]}<br>"
                    "Exposure: $%{x:,.0f}<extra></extra>"
                ),
            )
        )
        style_figure(fig, height=330)
        fig.update_xaxes(
            tickprefix="$",
            tickformat=",.0f",
            showgrid=True,
            gridcolor="#f2f4f7",
            range=[0, chart_data["projected_lost_revenue_value"].max() * 1.25],
        )
        fig.update_layout(bargap=0.42, margin=dict(l=8, r=10, t=10, b=8))
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with policy_col:
        section_head("Inventory position vs ROP", "most under-covered SKUs")
        gap_data = queue.nsmallest(12, "gap_to_dynamic_rop_units").sort_values(
            "gap_to_dynamic_rop_units", ascending=False
        )
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=gap_data["inventory_position_units"].clip(lower=0),
                y=gap_data["sku"],
                orientation="h",
                name="Inventory position",
                marker=dict(color=TEAL_LIGHT, cornerradius=3),
                hovertemplate="<b>%{y}</b><br>Position: %{x:,.0f} units<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=gap_data["dynamic_rop_target_units"],
                y=gap_data["sku"],
                mode="markers",
                name="Dynamic ROP",
                marker=dict(symbol="diamond", size=9, color=NAVY),
                hovertemplate="<b>%{y}</b><br>ROP: %{x:,.0f} units<extra></extra>",
            )
        )
        style_figure(fig, height=330, legend=True, top_margin=28)
        fig.update_xaxes(title_text="units", showgrid=True, gridcolor="#f2f4f7")
        fig.update_layout(bargap=0.4)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    section_head("Decision table", "one row per SKU · sort or download")
    table_cols = [
        "risk_tier",
        "sku",
        "product_name",
        "supplier_name",
        "inventory_position_units",
        "dynamic_rop_target_units",
        "gap_to_dynamic_rop_units",
        "suggested_order_units",
        "projected_lost_revenue_value",
    ]
    st.dataframe(
        queue[table_cols],
        hide_index=True,
        width="stretch",
        height=360,
        column_config={
            "risk_tier": st.column_config.TextColumn("Risk", width="small"),
            "sku": st.column_config.TextColumn("SKU", width="small"),
            "product_name": st.column_config.TextColumn("Product", width="medium"),
            "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
            "inventory_position_units": st.column_config.NumberColumn(
                "Position", format="%.0f", width="small"
            ),
            "dynamic_rop_target_units": st.column_config.NumberColumn(
                "ROP", format="%.0f", width="small"
            ),
            "gap_to_dynamic_rop_units": st.column_config.NumberColumn(
                "Gap", format="%.0f", width="small"
            ),
            "suggested_order_units": st.column_config.NumberColumn(
                "Order", format="%.0f", width="small"
            ),
            "projected_lost_revenue_value": st.column_config.NumberColumn(
                "At risk", format="$%.0f", width="small"
            ),
        },
    )
    st.download_button(
        "Download queue as CSV",
        data=queue[table_cols].to_csv(index=False).encode("utf-8"),
        file_name=f"reorder_queue_{AS_OF:%Y%m%d}.csv",
        mime="text/csv",
    )

    section_head("Open purchase orders for queued SKUs", "inbound supply in transit")
    open_pos = PURCHASE_ORDERS[
        PURCHASE_ORDERS["is_open"].fillna(False)
        & PURCHASE_ORDERS["sku"].isin(queue["sku"])
    ].copy()
    if open_pos.empty:
        st.info("No open purchase orders for the selected SKUs.")
    else:
        open_pos = open_pos.sort_values("promised_date")
        st.dataframe(
            open_pos[
                [
                    "po_number",
                    "sku",
                    "product_name",
                    "supplier_name",
                    "order_date",
                    "promised_date",
                    "quantity_ordered",
                    "open_units",
                    "status",
                    "is_overdue",
                ]
            ],
            hide_index=True,
            width="stretch",
            height=180,
            column_config={
                "po_number": st.column_config.TextColumn("PO", width="small"),
                "sku": st.column_config.TextColumn("SKU", width="small"),
                "product_name": st.column_config.TextColumn("Product", width="medium"),
                "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
                "order_date": st.column_config.DateColumn("Ordered", format="DD MMM YY"),
                "promised_date": st.column_config.DateColumn("Promised", format="DD MMM YY"),
                "quantity_ordered": st.column_config.NumberColumn("Ordered", format="%.0f"),
                "open_units": st.column_config.NumberColumn("Open", format="%.0f"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "is_overdue": st.column_config.CheckboxColumn("Overdue", width="small"),
            },
        )


# ---------------------------------------------------------------------------
# Page: Supplier performance
# ---------------------------------------------------------------------------


def render_suppliers() -> None:
    page_header(
        "Supplier performance",
        "Lead-time variability is a working-capital cost",
        "Promised versus actual lead time, on-time delivery, and the incremental safety "
        "and cycle stock created by supplier variability.",
    )

    metric_cols = st.columns(6)
    metric_cols[0].metric("Suppliers", number(len(SUPPLIERS)))
    metric_cols[1].metric(
        "Weighted on-time",
        pct(weighted_on_time(SUPPLIERS)),
        help="PO-count-weighted on-time rate across received orders.",
    )
    weighted_variance = (
        (SUPPLIERS["avg_variance_days"] * SUPPLIERS["received_po_count"]).sum()
        / SUPPLIERS["received_po_count"].sum()
    )
    metric_cols[2].metric(
        "Lead-time variance",
        signed_days(weighted_variance),
        help=(
            "Actual receipt date minus promised date, weighted by received POs. "
            "A negative value means suppliers are early on average."
        ),
    )
    metric_cols[3].metric(
        "Open POs",
        number(SUPPLIERS["open_po_count"].sum()),
        delta=f"{number(SUPPLIERS['overdue_open_po_count'].sum())} overdue",
        delta_color="inverse",
    )
    metric_cols[4].metric(
        "Open inbound",
        number(SUPPLIERS["open_inbound_units"].sum()) + " units",
        help="Units on open purchase orders, across all suppliers.",
    )
    metric_cols[5].metric(
        "Lead-time exposure",
        money(SUPPLIERS["lead_time_exposure_value"].sum()),
        help="SKU-level incremental safety and cycle stock required by actual supplier lead time, at cost.",
    )

    section_head("Supplier scorecard", "sort any column · click a row for context")
    scorecard_cols = [
        "supplier_name",
        "country_code",
        "sku_count",
        "received_po_count",
        "promised_lead_time_days",
        "avg_actual_lead_time_days",
        "avg_variance_days",
        "on_time_rate",
        "on_time_target_pct",
        "open_po_count",
        "overdue_open_po_count",
        "lead_time_exposure_value",
    ]
    st.dataframe(
        SUPPLIERS[scorecard_cols].sort_values("on_time_rate"),
        hide_index=True,
        width="stretch",
        height=470,
        column_config={
            "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
            "country_code": st.column_config.TextColumn("Country", width="small"),
            "sku_count": st.column_config.NumberColumn("SKUs", format="%.0f", width="small"),
            "received_po_count": st.column_config.NumberColumn(
                "Received", format="%.0f", width="small"
            ),
            "promised_lead_time_days": st.column_config.NumberColumn(
                "Promised", format="%.0f", width="small"
            ),
            "avg_actual_lead_time_days": st.column_config.NumberColumn(
                "Actual", format="%.1f", width="small"
            ),
            "avg_variance_days": st.column_config.NumberColumn(
                "Variance", format="%+.1f", width="small"
            ),
            "on_time_rate": st.column_config.NumberColumn(
                "On-time", format="percent", width="small"
            ),
            "on_time_target_pct": st.column_config.NumberColumn(
                "Target", format="percent", width="small"
            ),
            "open_po_count": st.column_config.NumberColumn("Open POs", format="%.0f", width="small"),
            "overdue_open_po_count": st.column_config.NumberColumn(
                "Overdue", format="%.0f", width="small"
            ),
            "lead_time_exposure_value": st.column_config.NumberColumn(
                "Exposure", format="$%.0f", width="small"
            ),
        },
    )

    chart_col, scatter_col = st.columns([1.15, 1], gap="medium")
    with chart_col:
        section_head("On-time rate vs target", "sorted by on-time rate")
        chart = SUPPLIERS.sort_values("on_time_rate").copy()
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=chart["on_time_rate"] * 100,
                y=chart["supplier_name"],
                orientation="h",
                marker=dict(
                    color=[
                        TEAL if row["on_time_rate"] >= row["on_time_target_pct"] else AMBER
                        for _, row in chart.iterrows()
                    ],
                    cornerradius=3,
                ),
                text=[f"{v:.0%}" for v in chart["on_time_rate"]],
                textposition="inside",
                insidetextanchor="start",
                textfont=dict(size=9, color=WHITE),
                hovertemplate="<b>%{y}</b><br>On-time: %{x:.1f}%<extra></extra>",
                name="On-time",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=chart["on_time_target_pct"] * 100,
                y=chart["supplier_name"],
                mode="markers",
                marker=dict(symbol="diamond", size=7, color=NAVY),
                name="Target",
                hovertemplate="<b>%{y}</b><br>Target: %{x:.1f}%<extra></extra>",
            )
        )
        style_figure(fig, height=430, legend=True, top_margin=28)
        fig.update_xaxes(range=[0, 105], ticksuffix="%", showgrid=True, gridcolor="#f2f4f7")
        fig.update_layout(bargap=0.4, margin=dict(l=8, r=46, t=30, b=8))
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with scatter_col:
        section_head(
            "Promised vs actual lead time",
            "hover for supplier · bubble = received PO count",
        )
        fig = px.scatter(
            SUPPLIERS,
            x="promised_lead_time_days",
            y="avg_actual_lead_time_days",
            size="received_po_count",
            color="on_time_rate",
            color_continuous_scale=["#fda29b", "#fec84b", "#7fc3c9", TEAL],
            range_color=[0.7, 1.0],
            hover_name="supplier_name",
            labels={
                "promised_lead_time_days": "Promised lead time (days)",
                "avg_actual_lead_time_days": "Average actual lead time (days)",
                "on_time_rate": "On-time",
            },
            size_max=34,
        )
        fig.update_traces(marker=dict(line=dict(width=1, color=WHITE)))
        max_days = max(
            SUPPLIERS["promised_lead_time_days"].max(),
            SUPPLIERS["avg_actual_lead_time_days"].max(),
        ) * 1.06
        fig.add_trace(
            go.Scatter(
                x=[0, max_days],
                y=[0, max_days],
                mode="lines",
                line=dict(color="#98a2b3", dash="dot", width=1),
                name="Perfect match",
                hoverinfo="skip",
            )
        )
        style_figure(fig, height=430, legend=True, top_margin=28)
        fig.update_layout(coloraxis_colorbar=dict(title="OTD", thickness=8, len=0.65))
        fig.update_xaxes(range=[0, max_days], showgrid=True, gridcolor="#f2f4f7")
        fig.update_yaxes(range=[0, max_days], showgrid=True, gridcolor="#f2f4f7")
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    variance_col, exposure_col = st.columns([1.15, 1], gap="medium")
    with variance_col:
        section_head("PO variance distribution", "actual minus promised date · received POs")
        received = PURCHASE_ORDERS[PURCHASE_ORDERS["received_date"].notna()].copy()
        supplier_order = list(
            SUPPLIERS.sort_values("avg_variance_days")["supplier_name"]
        )
        fig = px.box(
            received,
            x="variance_days",
            y="supplier_name",
            color="supplier_name",
            category_orders={"supplier_name": supplier_order},
            color_discrete_sequence=[
                TEAL,
                "#4f9ea6",
                "#7fc3c9",
                "#a7d7db",
                NAVY,
                "#98a2b3",
                AMBER,
                ORANGE,
                RED,
                "#6b8faf",
                "#3b6b8a",
                "#8dcbd1",
            ],
            points="outliers",
            labels={"variance_days": "Variance (days)", "supplier_name": ""},
        )
        fig.add_vline(x=0, line_dash="dot", line_color="#98a2b3")
        style_figure(fig, height=430)
        fig.update_layout(showlegend=False, bargap=0.25)
        fig.update_xaxes(showgrid=True, gridcolor="#f2f4f7", zeroline=True, zerolinecolor="#98a2b3")
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with exposure_col:
        section_head("Working-capital exposure", "incremental stock required by lead time")
        exposure = SUPPLIERS.sort_values("lead_time_exposure_value").copy()
        fig = go.Figure(
            go.Bar(
                x=exposure["lead_time_exposure_value"],
                y=exposure["supplier_name"],
                orientation="h",
                marker=dict(color=TEAL, cornerradius=3),
                text=[money_compact(v) for v in exposure["lead_time_exposure_value"]],
                textposition="outside",
                textfont=dict(size=8.5, color="#475467"),
                customdata=exposure[["lead_time_variance_days", "on_time_rate"]],
                hovertemplate=(
                    "<b>%{y}</b><br>Exposure: $%{x:,.0f}<br>"
                    "Variance: %{customdata[0]:+.1f} days<br>"
                    "On-time: %{customdata[1]:.1%}<extra></extra>"
                ),
            )
        )
        style_figure(fig, height=430)
        fig.update_xaxes(
            tickprefix="$",
            tickformat=",.0f",
            showgrid=True,
            gridcolor="#f2f4f7",
            range=[0, exposure["lead_time_exposure_value"].max() * 1.22],
        )
        fig.update_layout(bargap=0.4, margin=dict(l=8, r=10, t=10, b=8))
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    section_head("Supplier detail", "open orders and SKU mix")
    focus = st.selectbox(
        "Focus supplier",
        ["All suppliers"] + sorted(SUPPLIERS["supplier_name"]),
        key="supplier_focus",
    )
    if focus == "All suppliers":
        overdue = PURCHASE_ORDERS[
            PURCHASE_ORDERS["is_overdue"].fillna(False) & PURCHASE_ORDERS["is_open"].fillna(False)
        ].sort_values("promised_date")
        st.markdown(
            '<div class="mini-note"><strong>Overdue inbound.</strong> '
            "These open purchase orders have passed their promised receipt date.</div>",
            unsafe_allow_html=True,
        )
        if overdue.empty:
            st.info("No overdue open purchase orders.")
        else:
            st.dataframe(
                overdue[
                    [
                        "po_number",
                        "sku",
                        "product_name",
                        "supplier_name",
                        "promised_date",
                        "open_units",
                        "status",
                    ]
                ],
                hide_index=True,
                width="stretch",
                height=230,
                column_config={
                    "po_number": st.column_config.TextColumn("PO", width="small"),
                    "sku": st.column_config.TextColumn("SKU", width="small"),
                    "product_name": st.column_config.TextColumn("Product", width="medium"),
                    "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
                    "promised_date": st.column_config.DateColumn("Promised", format="DD MMM YY"),
                    "open_units": st.column_config.NumberColumn("Open units", format="%.0f"),
                    "status": st.column_config.TextColumn("Status", width="small"),
                },
            )
        return

    supplier_row = SUPPLIERS[SUPPLIERS["supplier_name"] == focus].iloc[0]
    supplier_pos = PURCHASE_ORDERS[PURCHASE_ORDERS["supplier_name"] == focus].copy()
    supplier_open = supplier_pos[supplier_pos["is_open"].fillna(False)].sort_values("promised_date")
    supplier_skus = OVERVIEW[OVERVIEW["supplier_name"] == focus].sort_values(
        "annual_consumption_value", ascending=False
    )

    detail_cols = st.columns(6)
    detail_cols[0].metric("On-time rate", pct(supplier_row["on_time_rate"]))
    detail_cols[1].metric("Promised lead time", f"{supplier_row['promised_lead_time_days']:.0f} days")
    detail_cols[2].metric("Actual lead time", f"{supplier_row['avg_actual_lead_time_days']:.1f} days")
    detail_cols[3].metric("Open POs", number(supplier_row["open_po_count"]))
    detail_cols[4].metric("Inbound units", number(supplier_row["open_inbound_units"]))
    detail_cols[5].metric("Exposure", money(supplier_row["lead_time_exposure_value"]))

    if supplier_open.empty:
        st.info(f"No open purchase orders for {focus}.")
    else:
        st.dataframe(
            supplier_open[
                [
                    "po_number",
                    "sku",
                    "product_name",
                    "order_date",
                    "promised_date",
                    "quantity_ordered",
                    "open_units",
                    "is_overdue",
                ]
            ],
            hide_index=True,
            width="stretch",
            height=220,
            column_config={
                "po_number": st.column_config.TextColumn("PO", width="small"),
                "sku": st.column_config.TextColumn("SKU", width="small"),
                "product_name": st.column_config.TextColumn("Product", width="medium"),
                "order_date": st.column_config.DateColumn("Ordered", format="DD MMM YY"),
                "promised_date": st.column_config.DateColumn("Promised", format="DD MMM YY"),
                "quantity_ordered": st.column_config.NumberColumn("Ordered", format="%.0f"),
                "open_units": st.column_config.NumberColumn("Open", format="%.0f"),
                "is_overdue": st.column_config.CheckboxColumn("Overdue", width="small"),
            },
        )

    section_head(f"{focus} SKU mix", "risk and consumption value")
    st.dataframe(
        supplier_skus[
            [
                "sku",
                "product_name",
                "abc_xyz_segment",
                "risk_tier",
                "reorder_status",
                "annual_consumption_value",
                "current_inventory_value",
                "projected_lost_revenue_value",
            ]
        ],
        hide_index=True,
        width="stretch",
        height=260,
        column_config={
            "sku": st.column_config.TextColumn("SKU", width="small"),
            "product_name": st.column_config.TextColumn("Product", width="medium"),
            "abc_xyz_segment": st.column_config.TextColumn("Segment", width="small"),
            "risk_tier": st.column_config.TextColumn("Risk", width="small"),
            "reorder_status": st.column_config.TextColumn("Status", width="medium"),
            "annual_consumption_value": st.column_config.NumberColumn(
                "Annual value", format="$%.0f"
            ),
            "current_inventory_value": st.column_config.NumberColumn(
                "On hand", format="$%.0f"
            ),
            "projected_lost_revenue_value": st.column_config.NumberColumn(
                "At risk", format="$%.0f"
            ),
        },
    )


# ---------------------------------------------------------------------------
# Page: SKU drilldown
# ---------------------------------------------------------------------------


def render_sku_drilldown() -> None:
    page_header(
        "SKU drilldown",
        "One item, end to end",
        "Demand history, the fitted forecast, inventory versus reorder point, "
        "and the exact replenishment action for a single SKU.",
    )

    sku_options = OVERVIEW.sort_values("annual_consumption_value", ascending=False)["sku"].tolist()
    names = OVERVIEW.set_index("sku")["product_name"].to_dict()
    selected_sku = st.selectbox(
        "Search or select a SKU",
        sku_options,
        format_func=lambda sku: f"{sku} · {names.get(sku, '')}",
        key="sku_drilldown",
    )
    row = OVERVIEW[OVERVIEW["sku"] == selected_sku].iloc[0]

    risk_color = RISK_COLORS.get(row["risk_tier"], MUTED)
    risk_bg = {
        "Critical": "#fee4e2",
        "High": "#ffead5",
        "Watch": "#fef0c7",
        "Low": "#d1fadf",
    }.get(row["risk_tier"], "#f2f4f7")
    badges = "".join(
        [
            badge(f"{row['abc_class']}{row['xyz_class']} segment", "#e8f4f5", TEAL),
            badge(row["demand_pattern"], "#f2f4f7", "#475467"),
            badge(row["risk_tier"] + " risk", risk_bg, risk_color),
            badge(row["reorder_status"], "#eef2f7", NAVY),
        ]
    )
    st.markdown(
        f'<div class="product-head"><h2>{html.escape(str(row["product_name"]))}</h2>'
        f"<p>{html.escape(str(row['sku']))} · {html.escape(str(row['category']))} · "
        f"supplied by {html.escape(str(row['supplier_name']))}</p>"
        f'<div class="product-meta">{badges}</div></div>',
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(6)
    metric_cols[0].metric(
        "On hand",
        number(row["current_stock_units"]),
        help=(
            "Current on-hand units. Inventory position, including open inbound, is "
            f"{number(row['inventory_position_units'])} units."
        ),
    )
    metric_cols[1].metric(
        "Dynamic ROP",
        number(row["dynamic_rop_target_units"]),
        delta=f"{number(row['gap_to_dynamic_rop_units'])} gap",
        delta_color="normal",
        help="Forecast-driven reorder point at the SKU target service level.",
    )
    metric_cols[2].metric(
        "Safety stock",
        number(row["dynamic_safety_stock_target_units"]),
        help=f"Buffer at the SKU target service level of {row['target_service_level']:.0%}.",
    )
    metric_cols[3].metric(
        "EOQ",
        number(row["eoq_units"]),
        help=(
            "Economic order quantity. Suggested order of "
            f"{number(row['suggested_order_units'])} units may be adjusted for MOQ and position."
        ),
    )
    metric_cols[4].metric(
        "Stockout risk",
        pct(row["stockout_probability"]),
        help=f"Monte Carlo probability that lead-time demand exceeds available units. Risk tier: {row['risk_tier']}.",
    )
    metric_cols[5].metric(
        "Forecast WAPE",
        pct(row["forecast_wape"]),
        help=f"Holdout error for the selected model: {row['forecast_model']}.",
    )

    if row["reorder_required"]:
        callout(
            f"<strong>{html.escape(str(row['risk_action']))}.</strong> "
            f"At the current forecast, the SKU has about "
            f"<strong>{number(row['days_of_supply_forecast'], 1)} days</strong> of cover and a "
            f"<strong>{pct(row['stockout_probability'])}</strong> stockout probability before the next receipt. "
            f"Suggested order: <strong>{number(row['suggested_order_units'])} units</strong>; "
            f"projected lost revenue: <strong>{money(row['projected_lost_revenue_value'])}</strong>.",
            tone="danger" if row["risk_tier"] == "Critical" else "warn",
        )
    else:
        callout(
            f"<strong>{html.escape(str(row['reorder_status']))}.</strong> "
            f"Inventory position is <strong>{number(row['inventory_position_units'])} units</strong> "
            f"against a dynamic ROP of <strong>{number(row['dynamic_rop_target_units'])}</strong>. "
            f"Stockout probability is <strong>{pct(row['stockout_probability'])}</strong>.",
        )

    demand_col, weekly_col = st.columns([1.18, 1], gap="medium")
    with demand_col:
        section_head("Monthly demand and forecast", "actuals + 3-month ETS forecast")
        sku_monthly = MONTHLY[MONTHLY["sku"] == selected_sku].sort_values("month_start")
        actual = sku_monthly[sku_monthly["record_type"] == "Actual"]
        forecast = sku_monthly[sku_monthly["record_type"] == "Forecast"]
        fig = go.Figure()
        if not actual.empty and not forecast.empty:
            band_x = [actual["month_start"].iloc[-1]] + forecast["month_start"].tolist()
            band_upper = [actual["actual_units"].iloc[-1]] + forecast["upper_95_units"].tolist()
            band_lower = [actual["actual_units"].iloc[-1]] + forecast["lower_95_units"].tolist()
            forecast_x = band_x
            forecast_y = [actual["actual_units"].iloc[-1]] + forecast["forecast_units"].tolist()
            fig.add_trace(
                go.Scatter(
                    x=band_x,
                    y=band_upper,
                    mode="lines",
                    line=dict(width=0),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=band_x,
                    y=band_lower,
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(14,124,134,.14)",
                    name="95% interval",
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=forecast_x,
                    y=forecast_y,
                    mode="lines+markers",
                    line=dict(color=AMBER, width=2.2, dash="dash"),
                    marker=dict(size=5),
                    name="Forecast",
                    hovertemplate="%{x|%b %Y}<br>Forecast: %{y:,.1f} units<extra></extra>",
                )
            )
        fig.add_trace(
            go.Scatter(
                x=actual["month_start"],
                y=actual["actual_units"],
                mode="lines+markers",
                line=dict(color=TEAL, width=2.2),
                marker=dict(size=4.5),
                name="Actual",
                hovertemplate="%{x|%b %Y}<br>Actual: %{y:,.1f} units<extra></extra>",
            )
        )
        fig.add_vline(
            x=AS_OF.to_pydatetime(),
            line_dash="dot",
            line_color="#98a2b3",
            annotation_text="as of",
            annotation_font=dict(size=9, color=MUTED),
            annotation_position="top",
        )
        style_figure(fig, height=310, legend=True, top_margin=30)
        fig.update_yaxes(title_text="units", showgrid=True, gridcolor="#f2f4f7")
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
        st.caption(
            f"Model: **{row['forecast_model']}** · holdout WAPE **{pct(row['forecast_wape'])}** · "
            f"forecast horizon **{int(row['lead_time_horizon_days'])} days**"
        )

    with weekly_col:
        section_head("Weekly demand", "last 52 weeks · 4-week average")
        sku_weekly = WEEKLY[WEEKLY["sku"] == selected_sku].sort_values("week_start").tail(52)
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=sku_weekly["week_start"],
                y=sku_weekly["units_sold"],
                name="Units sold",
                marker=dict(color=TEAL_PALE, cornerradius=2),
                hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} units<extra></extra>",
            )
        )
        rolling = sku_weekly.set_index("week_start")["units_sold"].rolling(4).mean()
        fig.add_trace(
            go.Scatter(
                x=rolling.index,
                y=rolling.values,
                mode="lines",
                name="4-week average",
                line=dict(color=NAVY, width=2),
                hovertemplate="%{x|%d %b %Y}<br>%{y:,.1f} units<extra></extra>",
            )
        )
        style_figure(fig, height=310, legend=True, top_margin=30)
        fig.update_yaxes(title_text="units", showgrid=True, gridcolor="#f2f4f7")
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)
        st.caption(
            f"Annual units **{number(row['annual_units'])}** · weekly CV **{row['weekly_cv']:.2f}** · "
            f"pattern **{row['demand_pattern']}**"
        )

    inventory_col, policy_col = st.columns([1.18, 1], gap="medium")
    with inventory_col:
        section_head("Inventory versus retro reorder point", "weekly history")
        sku_snapshots = SNAPSHOTS[SNAPSHOTS["sku"] == selected_sku].sort_values("snapshot_date")
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=sku_snapshots["snapshot_date"],
                y=sku_snapshots["on_hand_units"],
                mode="lines",
                name="On hand",
                line=dict(color=TEAL, width=2.2),
                hovertemplate="%{x|%d %b %Y}<br>On hand: %{y:,.0f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sku_snapshots["snapshot_date"],
                y=sku_snapshots["inventory_position_units"],
                mode="lines",
                name="Inventory position",
                line=dict(color=NAVY, width=1.6, dash="dash"),
                hovertemplate="%{x|%d %b %Y}<br>Position: %{y:,.0f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sku_snapshots["snapshot_date"],
                y=sku_snapshots["historical_rop_target_units"],
                mode="lines",
                name="Historical ROP",
                line=dict(color=RED, width=1.5, dash="dot"),
                hovertemplate="%{x|%d %b %Y}<br>ROP: %{y:,.0f}<extra></extra>",
            )
        )
        style_figure(fig, height=300, legend=True, top_margin=30)
        fig.update_yaxes(title_text="units", showgrid=True, gridcolor="#f2f4f7")
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    with policy_col:
        section_head("Current policy levels", "units · target service level")
        policy_labels = [
            "On hand",
            "Inbound open",
            "Inventory position",
            "Safety stock",
            "Reorder point",
            "EOQ",
        ]
        policy_values = [
            row["current_stock_units"],
            row["inbound_open_units"],
            row["inventory_position_units"],
            row["dynamic_safety_stock_target_units"],
            row["dynamic_rop_target_units"],
            row["eoq_units"],
        ]
        policy_colors = [TEAL, "#a7d7db", NAVY, "#4f9ea6", AMBER, "#98a2b3"]
        fig = go.Figure(
            go.Bar(
                x=policy_values,
                y=policy_labels,
                orientation="h",
                marker=dict(color=policy_colors, cornerradius=3),
                text=[number(v) for v in policy_values],
                textposition="outside",
                textfont=dict(size=9.5, color="#475467"),
                hovertemplate="<b>%{y}</b><br>%{x:,.0f} units<extra></extra>",
            )
        )
        style_figure(fig, height=300)
        fig.update_xaxes(title_text="units", showgrid=True, gridcolor="#f2f4f7")
        fig.update_layout(bargap=0.35, margin=dict(l=8, r=48, t=10, b=8))
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG)

    section_head("Purchase order history", "most recent receipts and open commitments")
    sku_pos = PURCHASE_ORDERS[PURCHASE_ORDERS["sku"] == selected_sku].sort_values(
        "order_date", ascending=False
    ).head(10)
    if sku_pos.empty:
        st.info("No purchase orders for this SKU.")
    else:
        st.dataframe(
            sku_pos[
                [
                    "po_number",
                    "supplier_name",
                    "order_date",
                    "promised_date",
                    "received_date",
                    "quantity_ordered",
                    "quantity_received",
                    "open_units",
                    "variance_days",
                    "status",
                ]
            ],
            hide_index=True,
            width="stretch",
            height=250,
            column_config={
                "po_number": st.column_config.TextColumn("PO", width="small"),
                "supplier_name": st.column_config.TextColumn("Supplier", width="medium"),
                "order_date": st.column_config.DateColumn("Ordered", format="DD MMM YY"),
                "promised_date": st.column_config.DateColumn("Promised", format="DD MMM YY"),
                "received_date": st.column_config.DateColumn("Received", format="DD MMM YY"),
                "quantity_ordered": st.column_config.NumberColumn("Ordered", format="%.0f"),
                "quantity_received": st.column_config.NumberColumn("Received", format="%.0f"),
                "open_units": st.column_config.NumberColumn("Open", format="%.0f"),
                "variance_days": st.column_config.NumberColumn("Variance", format="%+.1f"),
                "status": st.column_config.TextColumn("Status", width="small"),
            },
        )

    st.caption(
        "Historical ROP fields are retrospective and intended for trend analysis only. "
        "Current risk and actions come from the latest pipeline run."
    )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

PAGES = [
    "Executive Overview",
    "Reorder Queue",
    "Supplier Performance",
    "SKU Drilldown",
]
PAGE_KEYS = {
    "overview": PAGES[0],
    "queue": PAGES[1],
    "suppliers": PAGES[2],
    "sku": PAGES[3],
}
requested_page = st.query_params.get("page", "overview")
if isinstance(requested_page, list):
    requested_page = requested_page[0]
default_page = PAGE_KEYS.get(str(requested_page).lower(), PAGES[0])

with st.sidebar:
    st.markdown(
        '<div class="side-brand"><span class="side-logo">IC</span>'
        "<div><strong>Inventory Control</strong><small>Portfolio demo</small></div></div>",
        unsafe_allow_html=True,
    )
    page = st.radio(
        "Workspace",
        PAGES,
        index=PAGES.index(default_page),
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown('<div class="side-label">Data snapshot</div>', unsafe_allow_html=True)
    st.markdown(f"**As of {AS_OF:%d %b %Y}**")
    st.caption(f"{SKU_COUNT} SKUs · {SUPPLIER_COUNT} suppliers · synthetic seed 42")
    st.divider()
    st.markdown('<div class="side-label">Explore</div>', unsafe_allow_html=True)
    st.markdown(
        "- [GitHub repository](https://github.com/mlaharsh/supply-chain-inventory-optimization)\n"
        "- [Dashboard preview](https://mlaharsh.github.io/supply-chain-inventory-optimization/)\n"
        "- [Methodology](https://github.com/mlaharsh/supply-chain-inventory-optimization/blob/main/docs/methodology.md)\n"
        "- [Tableau spec](https://github.com/mlaharsh/supply-chain-inventory-optimization/blob/main/docs/tableau_dashboard_spec.md)"
    )
    st.divider()
    st.caption(
        "Synthetic data for portfolio demonstration. Figures are decision support, "
        "not a financial statement."
    )

if page == "Executive Overview":
    render_overview()
elif page == "Reorder Queue":
    render_reorder_queue()
elif page == "Supplier Performance":
    render_suppliers()
else:
    render_sku_drilldown()
