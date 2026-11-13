import altair as alt
import pandas as pd
import streamlit as st

from data import applyFilters, insight, loadDailySales, loadOrders, money

dailySales = applyFilters(loadDailySales(), "salesDate")
orders = applyFilters(loadOrders(), "salesDate")
if dailySales.empty:
    st.warning("No data for the selected filters.")
    st.stop()

# ---------------------------------------------------------------- monthly summary
monthOf = lambda dates: dates.dt.to_period("M").dt.to_timestamp()
monthly = (dailySales.assign(month=monthOf(dailySales["salesDate"]))
           .groupby("month", as_index=False)[["salesAmount", "cancelledAmount", "netAmount"]].sum())
monthlyOrders = (orders.assign(month=monthOf(orders["salesDate"]))
                 .groupby("month", as_index=False)
                 .agg(orderCount=("invoiceNo", "count"), averageOrder=("orderAmount", "mean")))
monthly = monthly.merge(monthlyOrders, on="month", how="left").fillna(0)
monthly["monthLabel"] = monthly["month"].dt.strftime("%b %y")   # month names give full-width bars

netSales = dailySales["netAmount"].sum()
salesAmount = dailySales["salesAmount"].sum()
cancelledAmount = dailySales["cancelledAmount"].sum()
knownCustomers = orders["customerId"].nunique()

# ---------------------------------------------------------------- KPI row
with st.container(horizontal=True):
    st.metric("Net sales", money(netSales), border=True,
              chart_data=monthly["netAmount"].round(0).tolist(), chart_type="bar",
              help="Product sales minus cancellations")
    st.metric("Orders", f"{len(orders):,}", border=True,
              chart_data=monthly["orderCount"].tolist(), chart_type="line")
    st.metric("Customers", f"{knownCustomers:,}", border=True, help="Known customers (guests excluded)")
    st.metric("Average order", money(orders["orderAmount"].mean()), border=True,
              chart_data=monthly["averageOrder"].round(0).tolist(), chart_type="line")
    st.metric("Cancellation rate", f"{cancelledAmount / salesAmount:.1%}", border=True,
              help="Cancelled product value as a share of product sales")

# ---------------------------------------------------------------- monthly trend
with st.container(border=True):
    st.subheader("Net sales and orders by month", anchor=False)
    base = alt.Chart(monthly).encode(x=alt.X("monthLabel:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)))
    bars = base.mark_bar(color="#2E8B8B", opacity=0.85).encode(
        y=alt.Y("netAmount:Q", title="Net sales (£)", axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip("month:T", format="%B %Y"), alt.Tooltip("netAmount:Q", format=",.0f", title="Net sales £"),
                 alt.Tooltip("orderCount:Q", format=",", title="Orders")])
    line = base.mark_line(color="#1F3864", point=True, strokeWidth=2.5).encode(
        y=alt.Y("orderCount:Q", title="Orders"))
    st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=340))

    best = monthly.loc[monthly["netAmount"].idxmax()]
    peakMonths = monthly[monthly["month"].dt.month.isin([9, 10, 11])]["netAmount"].mean()
    normalMonths = monthly[monthly["month"].dt.month.isin(range(1, 9))]["netAmount"].mean()
    note = f"**{best['month']:%B %Y}** was the strongest month with **{money(best['netAmount'])}** net sales."
    if pd.notna(peakMonths) and pd.notna(normalMonths) and normalMonths > 0:
        note += (f" September–November averaged **{peakMonths / normalMonths:.1f}×** a typical January–August month: "
                 "customers (many of them retailers) stock up for Christmas, so stock, staff and marketing should be "
                 "planned from late summer.")
    insight(note)

# ---------------------------------------------------------------- second row
left, right = st.columns(2)

with left.container(border=True):
    st.subheader("Who buys", anchor=False)
    customerMix = pd.DataFrame({
        "customerType": ["Known customers", "Guests (no customer id)"],
        "orderAmount": [orders.loc[orders["customerId"].notna(), "orderAmount"].sum(),
                        orders.loc[orders["customerId"].isna(), "orderAmount"].sum()],
    })
    donut = alt.Chart(customerMix).mark_arc(innerRadius=70).encode(
        theta="orderAmount:Q",
        color=alt.Color("customerType:N", title=None,
                        scale=alt.Scale(domain=["Known customers", "Guests (no customer id)"], range=["#1F3864", "#E08E2B"]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=["customerType:N", alt.Tooltip("orderAmount:Q", format=",.0f", title="Order value £")])
    st.altair_chart(donut.properties(height=280))
    guestShare = customerMix["orderAmount"].iloc[1] / customerMix["orderAmount"].sum()
    if guestShare > 0.005:
        insight(f"Guests bring **{guestShare:.0%}** of order value but cannot be marketed to or analysed as customers. "
                "Asking for an account at checkout would unlock this data.")
    else:
        insight("Every order in this selection comes from a known customer, so all of it can be used for customer analysis.")

with right.container(border=True):
    st.subheader("Cancellations by month", anchor=False)
    cancelChart = alt.Chart(monthly).mark_bar(color="#C0392B").encode(
        x=alt.X("monthLabel:O", title=None, sort=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("cancelledAmount:Q", title="Cancelled (£)", axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip("month:T", format="%B %Y"), alt.Tooltip("cancelledAmount:Q", format=",.0f")])
    st.altair_chart(cancelChart.properties(height=280))
    worst = monthly.loc[monthly["cancelledAmount"].idxmax()]
    worstMonthDays = dailySales[dailySales["salesDate"].dt.to_period("M").dt.to_timestamp() == worst["month"]]
    worstDay = worstMonthDays.groupby("salesDate")["cancelledAmount"].sum()
    insight(f"Cancellations are **{cancelledAmount / salesAmount:.1%}** of sales overall. In the worst month, "
            f"**{worst['month']:%B %Y}** ({money(worst['cancelledAmount'])}), "
            f"**{worstDay.max() / worst['cancelledAmount']:.0%}** of the cancelled value happened on a single day "
            f"({worstDay.idxmax():%d %b}) – usually one very large order cancelled straight away, which points to an "
            "ordering-process issue rather than unhappy customers.")
