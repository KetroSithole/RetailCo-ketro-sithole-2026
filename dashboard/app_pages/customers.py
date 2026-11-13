import altair as alt
import pandas as pd
import streamlit as st

from data import applyFilters, insight, loadCustomerCancellations, loadOrders, money

orders = applyFilters(loadOrders(), "salesDate")
knownOrders = orders[orders["customerId"].notna()]
if knownOrders["customerId"].nunique() < 10:
    st.warning("Not enough customers for the selected filters.")
    st.stop()

# ---------------------------------------------------------------- one row per customer (RFM)
referenceDate = knownOrders["invoiceAt"].max() + pd.Timedelta(days=1)
customers = knownOrders.groupby("customerId").agg(
    lastOrder=("invoiceAt", "max"),
    firstOrder=("invoiceAt", "min"),
    orderCount=("invoiceNo", "count"),
    orderAmount=("orderAmount", "sum"),
    country=("country", "last"),
)
cancellations = applyFilters(loadCustomerCancellations(), "salesDate").groupby("customerId")["cancelledAmount"].sum()
customers["orderAmount"] = customers["orderAmount"] - cancellations.reindex(customers.index, fill_value=0)  # net value
customers["recencyDays"] = (referenceDate - customers["lastOrder"]).dt.days


def quintile(series: pd.Series, highIsGood: bool = True) -> pd.Series:
    scores = pd.qcut(series.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    return scores if highIsGood else 6 - scores


customers["recencyScore"] = quintile(customers["recencyDays"], highIsGood=False)
customers["frequencyScore"] = quintile(customers["orderCount"])


def segment(row) -> str:
    recency, frequency = row["recencyScore"], row["frequencyScore"]
    if recency >= 4 and frequency >= 4:
        return "Champions"
    if recency >= 3 and frequency >= 3:
        return "Loyal"
    if recency >= 4:
        return "New & promising"
    if recency <= 2 and frequency >= 3:
        return "At risk"
    if recency <= 2:
        return "Hibernating"
    return "Need attention"


customers["segment"] = customers.apply(segment, axis=1)
SEGMENT_ORDER = ["Champions", "Loyal", "New & promising", "Need attention", "At risk", "Hibernating"]
SEGMENT_COLORS = ["#1F3864", "#2E8B8B", "#7C9CBF", "#E08E2B", "#C0392B", "#94A3B8"]

# ---------------------------------------------------------------- KPI row
repeatShare = (customers["orderCount"] > 1).mean()
topFifth = customers["orderAmount"].sort_values(ascending=False)
topFifthShare = topFifth.head(max(1, len(topFifth) // 5)).sum() / topFifth.sum()
with st.container(horizontal=True):
    st.metric("Customers", f"{len(customers):,}", border=True)
    st.metric("Buy more than once", f"{repeatShare:.0%}", border=True)
    st.metric("Orders per customer", f"{customers['orderCount'].mean():.1f}", border=True)
    st.metric("Value per customer", money(customers["orderAmount"].mean()), border=True)
    st.metric("Sales from top 20% of customers", f"{topFifthShare:.0%}", border=True)

# ---------------------------------------------------------------- segments
summary = (customers.groupby("segment").agg(customerCount=("orderCount", "size"), orderAmount=("orderAmount", "sum"),
                                            averageOrders=("orderCount", "mean"), averageRecency=("recencyDays", "mean"))
           .reindex(SEGMENT_ORDER).dropna().reset_index())
summary["customerShare"] = summary["customerCount"] / summary["customerCount"].sum()
summary["valueShare"] = summary["orderAmount"] / summary["orderAmount"].sum()

with st.container(border=True):
    st.subheader("Customer segments (recency × frequency)", anchor=False)
    left, right = st.columns(2)
    shares = summary.melt(id_vars="segment", value_vars=["customerShare", "valueShare"], var_name="measure", value_name="share")
    shares["measure"] = shares["measure"].map({"customerShare": "Share of customers", "valueShare": "Share of sales"})
    chart = alt.Chart(shares).mark_bar().encode(
        y=alt.Y("segment:N", sort=SEGMENT_ORDER, title=None),
        x=alt.X("share:Q", title=None, axis=alt.Axis(format="%")),
        yOffset="measure:N",
        color=alt.Color("measure:N", title=None, scale=alt.Scale(range=["#94A3B8", "#1F3864"]), legend=alt.Legend(orient="bottom")),
        tooltip=["segment:N", "measure:N", alt.Tooltip("share:Q", format=".1%")])
    left.altair_chart(chart.properties(height=330))
    right.dataframe(
        summary[["segment", "customerCount", "averageOrders", "valueShare"]],
        hide_index=True,
        column_config={
            "segment": "Segment",
            "customerCount": st.column_config.NumberColumn("Customers", format="%,d"),
            "averageOrders": st.column_config.NumberColumn("Avg orders", format="%.1f"),
            "valueShare": st.column_config.ProgressColumn("Share of sales", format="percent", min_value=0, max_value=1),
        },
    )
    champions = summary.set_index("segment").reindex(["Champions", "At risk"])
    insight(f"**Champions** are {champions.loc['Champions', 'customerShare']:.0%} of customers but bring "
            f"**{champions.loc['Champions', 'valueShare']:.0%}** of sales – protect them with account management and "
            f"early access to new ranges. **At risk** customers ({champions.loc['At risk', 'customerCount']:,.0f}) used to "
            "buy often but have gone quiet: a win-back offer to this group is the quickest revenue opportunity.")

# ---------------------------------------------------------------- cohort retention
with st.container(border=True):
    st.subheader("Do new customers come back? (monthly cohorts)", anchor=False)
    cohortOrders = knownOrders.merge(customers["firstOrder"], left_on="customerId", right_index=True)
    cohortOrders["cohort"] = cohortOrders["firstOrder"].dt.to_period("M")
    cohortOrders["monthsLater"] = (cohortOrders["invoiceAt"].dt.to_period("M") - cohortOrders["cohort"]).apply(lambda gap: gap.n)
    cohortSize = cohortOrders.groupby("cohort")["customerId"].nunique()
    retention = (cohortOrders.groupby(["cohort", "monthsLater"])["customerId"].nunique()
                 .div(cohortSize, level="cohort").rename("retention").reset_index())
    retention = retention[retention["monthsLater"] <= 12]
    retention["cohortLabel"] = retention["cohort"].dt.strftime("%Y-%m")
    heat = alt.Chart(retention).mark_rect().encode(
        x=alt.X("monthsLater:O", title="Months after first order", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("cohortLabel:O", title="First order month"),
        color=alt.Color("retention:Q", title="Came back", scale=alt.Scale(scheme="tealblues"), legend=alt.Legend(format="%")),
        tooltip=["cohortLabel:O", "monthsLater:O", alt.Tooltip("retention:Q", format=".0%")])
    labels = alt.Chart(retention[retention["monthsLater"] > 0]).mark_text(fontSize=9).encode(
        x="monthsLater:O", y="cohortLabel:O", text=alt.Text("retention:Q", format=".0%"),
        color=alt.condition("datum.retention > 0.3", alt.value("white"), alt.value("#1F2937")))
    st.altair_chart(alt.layer(heat, labels).properties(height=380))
    firstCohort = retention[(retention["cohortLabel"] == retention["cohortLabel"].min()) & (retention["monthsLater"].between(1, 11))]
    laterMonthOne = retention[(retention["monthsLater"] == 1) & (retention["cohortLabel"] > retention["cohortLabel"].min())]["retention"].mean()
    insight(f"The first cohort (customers already buying in {retention['cohortLabel'].min()}) is very loyal – "
            f"**{firstCohort['retention'].mean():.0%}** of them order in a typical later month. Newer customers return "
            f"much less (**{laterMonthOne:.0%}** come back the next month). A second-order offer within 30 days "
            "would lift retention of new customers.")

# ---------------------------------------------------------------- top customers
with st.container(border=True):
    st.subheader("Top 15 customers", anchor=False)
    topCustomers = customers.sort_values("orderAmount", ascending=False).head(15).reset_index()
    st.dataframe(
        topCustomers[["customerId", "country", "segment", "orderCount", "orderAmount", "lastOrder"]],
        hide_index=True,
        column_config={
            "customerId": st.column_config.NumberColumn("Customer", format="%d"),
            "country": "Country",
            "segment": "Segment",
            "orderCount": st.column_config.NumberColumn("Orders", format="%,d"),
            "orderAmount": st.column_config.NumberColumn("Net value", format="£%,.0f", help="Orders minus cancellations"),
            "lastOrder": st.column_config.DatetimeColumn("Last order", format="D MMM YYYY"),
        },
    )
