"""Data access for the dashboard: cached queries against RETAIL_DWH plus shared filters.

The queries return small, pre-aggregated tables. Filters (date range, countries)
are applied in pandas so changing a filter does not hit the database again.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyodbc
import streamlit as st

PROJECT_FOLDER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_FOLDER))
from etl.settings import Settings  # noqa: E402  (reuses the .config environment settings)


def runQuery(sql: str) -> pd.DataFrame:
    settings = Settings()
    with pyodbc.connect(settings.connectionString()) as connection:
        cursor = connection.execute(sql)
        columns = [column[0] for column in cursor.description]
        frame = pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
    for column in frame.columns:                       # SQL DECIMAL -> float for charts
        if len(frame) and isinstance(frame[column].iloc[0], Decimal):
            frame[column] = frame[column].astype(float)
    return frame


@st.cache_data(ttl="15m", show_spinner="Loading sales by day...")
def loadDailySales() -> pd.DataFrame:
    frame = runQuery("""
        SELECT
            calendar.calendarDate                                                     AS salesDate,
            sales.country,
            SUM(sales.salesAmount)                                                    AS salesAmount,
            SUM(sales.cancelledAmount)                                                AS cancelledAmount,
            SUM(sales.netAmount)                                                      AS netAmount,
            SUM(IIF(sales.lineType = 'product' AND sales.transactionType = 'sale', sales.quantity, 0)) AS units
        FROM RETAIL_DWH.fact.sales   AS sales
        JOIN RETAIL_DWH.dim.calendar AS calendar ON calendar.calendarKey = sales.calendarKey
        WHERE sales.isDeleted = 0
        GROUP BY calendar.calendarDate, sales.country
    """)
    frame["salesDate"] = pd.to_datetime(frame["salesDate"])
    return frame


@st.cache_data(ttl="15m", show_spinner="Loading orders...")
def loadOrders() -> pd.DataFrame:
    """One row per customer order (a sale invoice with product sales)."""
    frame = runQuery("""
        SELECT
            sales.invoiceNo,
            MIN(sales.invoiceAt)                                              AS invoiceAt,
            MAX(customer.customerId)                                          AS customerId,
            MAX(sales.country)                                                AS country,
            SUM(IIF(sales.lineType <> 'stockAdjustment', sales.lineAmount, 0)) AS orderAmount,
            SUM(sales.salesAmount)                                            AS productAmount,
            SUM(IIF(sales.lineType = 'product', sales.quantity, 0))           AS units,
            COUNT(*)                                                          AS lineCount
        FROM RETAIL_DWH.fact.sales   AS sales
        JOIN RETAIL_DWH.dim.customer AS customer ON customer.customerKey = sales.customerKey
        WHERE sales.isDeleted = 0
          AND sales.transactionType = 'sale'
        GROUP BY sales.invoiceNo
        HAVING SUM(sales.salesAmount) > 0
    """)
    frame["invoiceAt"] = pd.to_datetime(frame["invoiceAt"])
    frame["salesDate"] = frame["invoiceAt"].dt.normalize()
    return frame


@st.cache_data(ttl="15m", show_spinner="Loading cancellations...")
def loadCustomerCancellations() -> pd.DataFrame:
    """Cancelled product value per customer per day (to show customer value net of cancellations)."""
    frame = runQuery("""
        SELECT
            customer.customerId,
            calendar.calendarDate        AS salesDate,
            sales.country,
            SUM(sales.cancelledAmount)   AS cancelledAmount
        FROM RETAIL_DWH.fact.sales    AS sales
        JOIN RETAIL_DWH.dim.customer  AS customer ON customer.customerKey = sales.customerKey
        JOIN RETAIL_DWH.dim.calendar  AS calendar ON calendar.calendarKey = sales.calendarKey
        WHERE sales.isDeleted = 0
          AND sales.cancelledAmount > 0
          AND sales.customerKey <> 0
        GROUP BY customer.customerId, calendar.calendarDate, sales.country
    """)
    frame["salesDate"] = pd.to_datetime(frame["salesDate"])
    return frame


@st.cache_data(ttl="15m", show_spinner="Loading products...")
def loadProductMonths() -> pd.DataFrame:
    """Product sales per month, with the current product description (SCD2)."""
    frame = runQuery("""
        WITH monthly AS (
            SELECT
                product.stockCode,
                DATEFROMPARTS(calendar.yearNo, calendar.monthNo, 1)               AS salesMonth,
                sales.country,
                SUM(sales.salesAmount)                                            AS salesAmount,
                SUM(sales.cancelledAmount)                                        AS cancelledAmount,
                SUM(sales.netAmount)                                              AS netAmount,
                SUM(IIF(sales.transactionType = 'sale', sales.quantity, 0))       AS units
            FROM RETAIL_DWH.fact.sales    AS sales
            JOIN RETAIL_DWH.dim.product   AS product  ON product.productKey   = sales.productKey
            JOIN RETAIL_DWH.dim.calendar  AS calendar ON calendar.calendarKey = sales.calendarKey
            WHERE sales.isDeleted = 0
              AND sales.lineType = 'product'
            GROUP BY product.stockCode, calendar.yearNo, calendar.monthNo, sales.country
        )
        SELECT monthly.*, currentProduct.description
        FROM monthly
        JOIN RETAIL_DWH.dim.product AS currentProduct
          ON currentProduct.stockCode = monthly.stockCode
         AND currentProduct.isCurrent = 1
    """)
    frame["salesMonth"] = pd.to_datetime(frame["salesMonth"])
    return frame


@st.cache_data(ttl="5m", show_spinner=False)
def loadPipeline() -> dict:
    return {
        "runLog": runQuery("SELECT * FROM RETAIL_DWH.etl.runLog ORDER BY runId DESC"),
        "dataQuality": runQuery("""
            SELECT checkName, recordCount, action, checkedAt
            FROM RETAIL_DWH.etl.dataQuality
            WHERE runId = (SELECT MAX(runId) FROM RETAIL_DWH.etl.dataQuality)
        """),
        "history": runQuery("""
            SELECT
                (SELECT COUNT(*) FROM RETAIL_DWH.fact.sales WHERE isDeleted = 0)                  AS activeLines,
                (SELECT COUNT(*) FROM RETAIL_DWH.fact.sales WHERE isDeleted = 1)                  AS softDeletedLines,
                (SELECT COUNT(*) FROM RETAIL_DWH.dim.product WHERE isCurrent = 0)                 AS closedProductVersions,
                (SELECT COUNT(*) FROM RETAIL_DWH.dim.customer WHERE isCurrent = 0)                AS closedCustomerVersions,
                (SELECT COUNT(*) FROM RETAIL_DWH.dim.product)                                     AS productRows,
                (SELECT COUNT(*) FROM RETAIL_DWH.dim.customer WHERE customerKey <> 0)             AS customerRows
        """),
    }


# ---------------------------------------------------------------- shared filters
def selectedFilters() -> tuple[pd.Timestamp, pd.Timestamp, list[str]]:
    """Date range and countries chosen in the sidebar (see streamlit_app.py)."""
    startMonth, endMonth = st.session_state.get("monthRange", (None, None))
    countries = st.session_state.get("countries", [])
    return startMonth, endMonth, countries


def applyFilters(frame: pd.DataFrame, dateColumn: str, useCountries: bool = True) -> pd.DataFrame:
    startMonth, endMonth, countries = selectedFilters()
    filtered = frame
    if startMonth is not None:
        nextMonth = endMonth + pd.offsets.MonthBegin(1)
        filtered = filtered[(filtered[dateColumn] >= startMonth) & (filtered[dateColumn] < nextMonth)]
    if countries and useCountries:
        filtered = filtered[filtered["country"].isin(countries)]
    return filtered


def money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"£{value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"£{value / 1_000:,.1f}k"
    return f"£{value:,.0f}"


def insight(text: str) -> None:
    """A highlighted 'what this tells us' note under a chart."""
    st.info(text, icon=":material/lightbulb:")
