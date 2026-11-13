import altair as alt
import streamlit as st

from data import applyFilters, insight, loadDailySales, loadOrders, money, selectedFilters

# This page compares countries, so it uses the month filter but not the country filter.
dailySales = applyFilters(loadDailySales(), "salesDate", useCountries=False)
orders = applyFilters(loadOrders(), "salesDate", useCountries=False)
if selectedFilters()[2]:
    st.caption("The country filter is not applied on this page, so all markets can be compared.")
if dailySales.empty:
    st.warning("No data for the selected filters.")
    st.stop()

countries = (dailySales.groupby("country", as_index=False)["netAmount"].sum()
             .merge(orders.groupby("country", as_index=False)
                    .agg(orderCount=("invoiceNo", "count"), averageOrder=("orderAmount", "mean"),
                         customerCount=("customerId", "nunique")), on="country", how="left")
             .fillna(0).sort_values("netAmount", ascending=False))
countries["salesShare"] = countries["netAmount"] / countries["netAmount"].sum()
ukShare = countries.loc[countries["country"] == "United Kingdom", "salesShare"].sum()

includeHome = st.toggle("Include United Kingdom", value=False, key="includeUk",
                        help="The UK is so large that it hides the differences between other markets.")
shown = countries if includeHome else countries[countries["country"] != "United Kingdom"]

left, right = st.columns(2)

with left.container(border=True):
    st.subheader("Net sales by country", anchor=False)
    bars = alt.Chart(shown.head(15)).mark_bar(color="#2E8B8B").encode(
        x=alt.X("netAmount:Q", title="Net sales (£)", axis=alt.Axis(format="~s")),
        y=alt.Y("country:N", sort="-x", title=None),
        tooltip=["country:N", alt.Tooltip("netAmount:Q", format=",.0f", title="Net sales £"),
                 alt.Tooltip("salesShare:Q", format=".1%", title="Share")])
    st.altair_chart(bars.properties(height=380))
    international = countries[countries["country"] != "United Kingdom"]
    insight(f"The UK is **{ukShare:.0%}** of net sales. Outside the UK, **{international.iloc[0]['country']}**, "
            f"**{international.iloc[1]['country']}** and **{international.iloc[2]['country']}** lead – these are the "
            "first markets to target with localised marketing and faster shipping.")

with right.container(border=True):
    st.subheader("Order size vs number of orders", anchor=False)
    bubbles = alt.Chart(shown[shown["orderCount"] >= 5]).mark_circle(opacity=0.75, stroke="#1F3864", strokeWidth=1).encode(
        x=alt.X("orderCount:Q", title="Orders (log scale)", scale=alt.Scale(type="log"), axis=alt.Axis(grid=False)),
        y=alt.Y("averageOrder:Q", title="Average order (£)"),
        size=alt.Size("customerCount:Q", title="Customers", scale=alt.Scale(range=[40, 1500])),
        color=alt.value("#1F3864"),
        tooltip=["country:N", alt.Tooltip("orderCount:Q", format=","), alt.Tooltip("averageOrder:Q", format=",.0f"),
                 alt.Tooltip("customerCount:Q", format=",")])
    text = alt.Chart(shown.head(8)).mark_text(dx=12, align="left", fontSize=10, color="#1F2937").encode(
        x="orderCount:Q", y="averageOrder:Q", text="country:N")
    st.altair_chart(alt.layer(bubbles, text).properties(height=380))
    bigBaskets = international[international["orderCount"] >= 20].sort_values("averageOrder", ascending=False)
    ukOrders = orders[orders["country"] == "United Kingdom"]["orderAmount"]
    abroadOrders = orders[orders["country"] != "United Kingdom"]["orderAmount"]
    note = (f"**{bigBaskets.iloc[0]['country']}** has the biggest orders, averaging "
            f"**{money(bigBaskets.iloc[0]['averageOrder'])}**.")
    if len(ukOrders) and len(abroadOrders):
        note += (f" Overall an overseas order is worth **{money(abroadOrders.mean())}** against "
                 f"{money(ukOrders.mean())} in the UK ({abroadOrders.mean() / ukOrders.mean():.1f}×). Overseas buyers "
                 "order less often but in bulk – volume pricing and account managers fit them best.")
    insight(note)

with st.container(border=True):
    st.subheader("All markets", anchor=False)
    st.dataframe(
        shown[["country", "netAmount", "salesShare", "orderCount", "customerCount", "averageOrder"]],
        hide_index=True,
        column_config={
            "country": "Country",
            "netAmount": st.column_config.NumberColumn("Net sales", format="£%,.0f"),
            "salesShare": st.column_config.ProgressColumn("Share of sales", format="percent", min_value=0,
                                                          max_value=float(shown["salesShare"].max())),
            "orderCount": st.column_config.NumberColumn("Orders", format="%,d"),
            "customerCount": st.column_config.NumberColumn("Customers", format="%,d"),
            "averageOrder": st.column_config.NumberColumn("Average order", format="£%,.0f"),
        },
    )
