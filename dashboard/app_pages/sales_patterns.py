import altair as alt
import pandas as pd
import streamlit as st

from data import applyFilters, insight, loadDailySales, loadOrders, money

orders = applyFilters(loadOrders(), "salesDate")
dailySales = applyFilters(loadDailySales(), "salesDate")
if orders.empty:
    st.warning("No data for the selected filters.")
    st.stop()

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ---------------------------------------------------------------- weekday x hour heatmap
with st.container(border=True):
    st.subheader("Orders by day of week and hour", anchor=False)
    orders = orders.assign(weekday=orders["invoiceAt"].dt.day_name(), hour=orders["invoiceAt"].dt.hour)
    grid = (orders.groupby(["weekday", "hour"]).size().rename("orderCount")
            .reindex(pd.MultiIndex.from_product([WEEKDAYS, range(6, 21)], names=["weekday", "hour"]), fill_value=0)
            .reset_index())
    heatmap = alt.Chart(grid).mark_rect(cornerRadius=3).encode(
        x=alt.X("hour:O", title="Hour of day"),
        y=alt.Y("weekday:N", sort=WEEKDAYS, title=None),
        color=alt.Color("orderCount:Q", title="Orders", scale=alt.Scale(scheme="tealblues")),
        tooltip=["weekday:N", "hour:O", alt.Tooltip("orderCount:Q", format=",", title="Orders")])
    st.altair_chart(heatmap.properties(height=300))

    peak = grid.loc[grid["orderCount"].idxmax()]
    byDay = grid.groupby("weekday")["orderCount"].sum().reindex(WEEKDAYS)
    noTradeDays = [day for day, count in byDay.items() if count == 0]
    middayShare = orders["hour"].between(10, 15).mean()
    note = (f"The busiest slot is **{peak['weekday']} at {int(peak['hour'])}:00**. "
            f"**{byDay.idxmax()}** is the busiest day overall, and **{middayShare:.0%}** of orders arrive between "
            "10:00 and 15:59.")
    if noTradeDays:
        note += f" There are **no orders on {', '.join(noTradeDays)}** – the business does not trade then."
    note += " Customer service and warehouse staff should be concentrated around late morning and midday."
    insight(note)

left, right = st.columns(2)

# ---------------------------------------------------------------- daily trend with rolling average
with left.container(border=True):
    st.subheader("Daily net sales", anchor=False)
    daily = dailySales.groupby("salesDate", as_index=False)["netAmount"].sum().sort_values("salesDate")
    daily["sevenDayAverage"] = daily["netAmount"].rolling(7, min_periods=1).mean()
    base = alt.Chart(daily).encode(x=alt.X("salesDate:T", title=None))
    points = base.mark_circle(color="#94A3B8", opacity=0.5, size=18).encode(
        y=alt.Y("netAmount:Q", title="Net sales (£)", axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip("salesDate:T", format="%a %d %b %Y"), alt.Tooltip("netAmount:Q", format=",.0f")])
    trend = base.mark_line(color="#1F3864", strokeWidth=2.5).encode(y="sevenDayAverage:Q")
    st.altair_chart(alt.layer(points, trend).properties(height=300))
    bestDay = daily.loc[daily["netAmount"].idxmax()]
    insight(f"Grey dots are single days, the line is the 7-day average. The best single day was "
            f"**{bestDay['salesDate']:%A %d %B %Y}** with **{money(bestDay['netAmount'])}**. Daily sales swing a lot "
            "because a few large wholesale orders can double a day's total.")

# ---------------------------------------------------------------- order value by weekday
with right.container(border=True):
    st.subheader("Average order value by day", anchor=False)
    weekdayValue = (orders.groupby("weekday", as_index=False)
                    .agg(averageOrder=("orderAmount", "mean"), orderCount=("invoiceNo", "count")))
    bars = alt.Chart(weekdayValue).mark_bar(color="#2E8B8B").encode(
        x=alt.X("weekday:N", sort=WEEKDAYS, title=None),
        y=alt.Y("averageOrder:Q", title="Average order (£)"),
        tooltip=["weekday:N", alt.Tooltip("averageOrder:Q", format=",.0f", title="Average order £"),
                 alt.Tooltip("orderCount:Q", format=",", title="Orders")])
    st.altair_chart(bars.properties(height=300))
    highest = weekdayValue.loc[weekdayValue["averageOrder"].idxmax()]
    lowest = weekdayValue.loc[weekdayValue["averageOrder"].idxmin()]
    note = (f"Orders are largest on **{highest['weekday']}** ({money(highest['averageOrder'])}) and smallest on "
            f"**{lowest['weekday']}** ({money(lowest['averageOrder'])}).")
    if lowest["weekday"] == "Sunday":
        note += (" Smaller Sunday baskets suggest more individual shoppers at the weekend – a good moment for "
                 "consumer-focused promotions, while weekdays suit trade customers.")
    insight(note)
