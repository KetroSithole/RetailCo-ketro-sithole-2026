"""RetailCo sales dashboard.

Run from the project folder:   streamlit run dashboard/streamlit_app.py
Data comes from RETAIL_DWH (the environment in .config/settings.env).
"""
import pandas as pd
import streamlit as st

from data import loadDailySales

st.set_page_config(page_title="RetailCo sales dashboard", page_icon=":material/storefront:", layout="wide")

page = st.navigation(
    {
        "": [
            st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:", default=True),
        ],
        "Analysis": [
            st.Page("app_pages/sales_patterns.py", title="When customers buy", icon=":material/schedule:"),
            st.Page("app_pages/products.py", title="Products", icon=":material/inventory_2:"),
            st.Page("app_pages/customers.py", title="Customers", icon=":material/groups:"),
            st.Page("app_pages/markets.py", title="Markets", icon=":material/public:"),
        ],
        "Platform": [
            st.Page("app_pages/pipeline.py", title="Data quality & ETL", icon=":material/fact_check:"),
        ],
    }
)

# ---------------------------------------------------------------- sidebar filters (shared by all pages)
dailySales = loadDailySales()
months = sorted(dailySales["salesDate"].dt.to_period("M").dt.to_timestamp().unique())
countries = (dailySales.groupby("country")["netAmount"].sum().sort_values(ascending=False).index.tolist())

with st.sidebar:
    st.markdown("**Filters**")
    st.select_slider(
        "Months",
        options=months,
        value=(months[0], months[-1]),
        format_func=lambda month: pd.Timestamp(month).strftime("%b %Y"),
        key="monthRange",
    )
    st.multiselect("Countries", countries, placeholder="All countries", key="countries")
    st.caption("Source: RETAIL_DWH star schema · UCI Online Retail dataset (CC BY 4.0)")

st.title(page.title, anchor=False)
page.run()
