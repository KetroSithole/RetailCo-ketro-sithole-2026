import altair as alt
import pandas as pd
import streamlit as st

from data import applyFilters, insight, loadProductMonths, money

productMonths = applyFilters(loadProductMonths(), "salesMonth")
if productMonths.empty:
    st.warning("No data for the selected filters.")
    st.stop()

products = (productMonths.groupby(["stockCode", "description"], as_index=False)
            [["salesAmount", "cancelledAmount", "netAmount", "units"]].sum()
            .sort_values("netAmount", ascending=False))
products["label"] = products["description"].str.title()

# ---------------------------------------------------------------- top products
with st.container(border=True):
    header, control = st.columns([3, 1], vertical_alignment="bottom")
    header.subheader("Best-selling products", anchor=False)
    topCount = control.segmented_control("Show top", [10, 20, 30], default=10, key="topProducts")
    topProducts = products.head(topCount or 10)
    bars = alt.Chart(topProducts).mark_bar(color="#1F3864").encode(
        x=alt.X("netAmount:Q", title="Net sales (£)", axis=alt.Axis(format="~s")),
        y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
        tooltip=["stockCode:N", "label:N", alt.Tooltip("netAmount:Q", format=",.0f", title="Net sales £"),
                 alt.Tooltip("units:Q", format=",", title="Units")])
    st.altair_chart(bars.properties(height=max(280, 22 * len(topProducts))))
    leader = topProducts.iloc[0]
    topShare = topProducts["netAmount"].sum() / products["netAmount"].sum()
    insight(f"**{leader['label']}** leads with **{money(leader['netAmount'])}**. These {len(topProducts)} products "
            f"alone bring **{topShare:.0%}** of net sales out of {len(products):,} products sold – they deserve the "
            "best shelf space, safety stock and the first marketing budget.")

left, right = st.columns(2)

# ---------------------------------------------------------------- Pareto curve
with left.container(border=True):
    st.subheader("How concentrated are sales?", anchor=False)
    positive = products[products["netAmount"] > 0].reset_index(drop=True)
    positive["productShare"] = (positive.index + 1) / len(positive)
    positive["salesShare"] = positive["netAmount"].cumsum() / positive["netAmount"].sum()
    curve = alt.Chart(positive).mark_area(line={"color": "#2E8B8B"}, color="#2E8B8B", opacity=0.25).encode(
        x=alt.X("productShare:Q", title="Share of products (best first)", axis=alt.Axis(format="%")),
        y=alt.Y("salesShare:Q", title="Share of net sales", axis=alt.Axis(format="%")),
        tooltip=[alt.Tooltip("productShare:Q", format=".0%", title="Products"),
                 alt.Tooltip("salesShare:Q", format=".0%", title="Sales")])
    eightyLine = alt.Chart(pd.DataFrame({"y": [0.8]})).mark_rule(color="#C0392B", strokeDash=[4, 4]).encode(y="y:Q")
    st.altair_chart(alt.layer(curve, eightyLine).properties(height=300))
    productsFor80 = int((positive["salesShare"] < 0.8).sum()) + 1
    insight(f"Just **{productsFor80:,} of {len(positive):,} products ({productsFor80 / len(positive):.0%})** make "
            "80% of net sales. These core lines must never go out of stock; the long tail is a candidate for "
            "range rationalisation.")

# ---------------------------------------------------------------- most cancelled
with right.container(border=True):
    st.subheader("Most cancelled products", anchor=False)
    cancelled = products[products["salesAmount"] >= 2000].copy()
    cancelled["cancellationRate"] = cancelled["cancelledAmount"] / cancelled["salesAmount"]
    cancelled = cancelled.sort_values("cancelledAmount", ascending=False).head(10)
    st.dataframe(
        cancelled[["label", "cancelledAmount", "cancellationRate"]],
        hide_index=True,
        column_config={
            "label": st.column_config.TextColumn("Product", width="medium"),
            "cancelledAmount": st.column_config.NumberColumn("Cancelled", format="£%,.0f"),
            "cancellationRate": st.column_config.ProgressColumn("Rate", format="percent", min_value=0, max_value=1),
        },
        height=300,
    )
    insight("A few products lose a large share of their sales to cancellations. Very high rates usually mean one "
            "huge order placed by mistake and cancelled – check the order process for these lines.")

# ---------------------------------------------------------------- rising stars
with st.container(border=True):
    st.subheader("Rising stars", anchor=False)
    monthsInRange = sorted(productMonths["salesMonth"].unique())
    if len(monthsInRange) < 6:
        st.caption("Select at least 6 months to compare recent and earlier sales.")
    else:
        recentMonths = monthsInRange[-4:-1] if pd.Timestamp(monthsInRange[-1]).month == 12 else monthsInRange[-3:]
        earlierMonths = [month for month in monthsInRange if month < recentMonths[0]]
        monthlyNet = (productMonths.groupby(["stockCode", "salesMonth"])["netAmount"].sum()
                      .unstack(fill_value=0).reindex(columns=monthsInRange, fill_value=0))
        growth = pd.DataFrame({
            "recentAverage": monthlyNet[recentMonths].mean(axis=1),
            "earlierAverage": monthlyNet[earlierMonths].mean(axis=1),
            "trend": monthlyNet.round(0).values.tolist(),
        }, index=monthlyNet.index)
        growth["growth"] = growth["recentAverage"] - growth["earlierAverage"]
        growth = (growth[growth["earlierAverage"] >= 100].sort_values("growth", ascending=False).head(10)
                  .join(products.set_index("stockCode")["label"]).reset_index())
        st.dataframe(
            growth[["label", "earlierAverage", "recentAverage", "growth", "trend"]],
            hide_index=True,
            column_config={
                "label": st.column_config.TextColumn("Product", width="large"),
                "earlierAverage": st.column_config.NumberColumn("Earlier £/month", format="£%,.0f"),
                "recentAverage": st.column_config.NumberColumn("Recent £/month", format="£%,.0f"),
                "growth": st.column_config.NumberColumn("Growth £/month", format="£%,.0f"),
                "trend": st.column_config.AreaChartColumn("Monthly net sales", y_min=0),
            },
        )
        insight(f"Compares the last full 3 months (**{pd.Timestamp(recentMonths[0]):%b}–{pd.Timestamp(recentMonths[-1]):%b %Y}**) "
                f"with the monthly average before. The fastest riser, **{growth.iloc[0]['label']}**, gained "
                f"**{money(growth.iloc[0]['growth'])} per month**. Order stock for these lines early, and check after "
                "the season which ones are lasting trends rather than one-off seasonal peaks.")
