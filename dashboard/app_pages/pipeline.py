import altair as alt
import streamlit as st

from data import insight, loadPipeline

pipeline = loadPipeline()
runLog = pipeline["runLog"]
dataQuality = pipeline["dataQuality"]
history = pipeline["history"].iloc[0]

if st.button("Refresh", icon=":material/refresh:"):
    loadPipeline.clear()
    st.rerun()

# ---------------------------------------------------------------- KPI row
lastRun = runLog.iloc[0] if len(runLog) else None
with st.container(horizontal=True):
    st.metric("Last run", lastRun["status"].title() if lastRun is not None else "–", border=True,
              help=f"{lastRun['fileName']} at {lastRun['startedAt']}" if lastRun is not None else None)
    st.metric("Files processed", f"{(runLog['status'] == 'success').sum():,}", border=True)
    st.metric("Active sales lines", f"{history['activeLines']:,}", border=True)
    st.metric("Soft-deleted lines", f"{history['softDeletedLines']:,}", border=True,
              help="Lines removed from a re-sent invoice. Kept for audit, excluded from reports.")
    st.metric("Product / customer versions closed (SCD2)",
              f"{history['closedProductVersions']:,} / {history['closedCustomerVersions']:,}", border=True)

# ---------------------------------------------------------------- data quality
with st.container(border=True):
    st.subheader("Data quality – latest run", anchor=False)
    left, right = st.columns([3, 2])
    bars = alt.Chart(dataQuality).encode(
        x=alt.X("recordCount:Q", title="Rows", axis=alt.Axis(format="~s"),
                scale=alt.Scale(domainMax=float(dataQuality["recordCount"].max()) * 1.15)),  # room for labels
        y=alt.Y("checkName:N", sort="-x", title=None),
        tooltip=["checkName:N", alt.Tooltip("recordCount:Q", format=","), "action:N"])
    chart = bars.mark_bar(color="#1F3864") + bars.mark_text(align="left", dx=4, fontSize=10, color="#1F2937").encode(
        text=alt.Text("recordCount:Q", format=","))
    left.altair_chart(chart.properties(height=360))
    right.dataframe(
        dataQuality.sort_values("recordCount", ascending=False)[["checkName", "recordCount", "action"]],
        hide_index=True,
        column_config={"checkName": "Check", "recordCount": st.column_config.NumberColumn("Rows", format="%,d"),
                       "action": "What the ETL did"},
        height=360,
    )
    guestRows = dataQuality.loc[dataQuality["checkName"] == "guestRows", "recordCount"].sum()
    fileRows = runLog.loc[runLog["runId"] == runLog["runId"].max(), "fileRowCount"].sum()
    note = ("Duplicates and invalid rows are removed before they reach the warehouse; everything else is kept and "
            "labelled, so no sale is silently lost.")
    if fileRows:
        note += (f" **{guestRows / fileRows:.0%}** of lines in the latest file have no customer number – the "
                 "biggest data gap to fix at the source.")
    insight(note)

# ---------------------------------------------------------------- run log
with st.container(border=True):
    st.subheader("ETL run log", anchor=False)
    st.dataframe(
        runLog[["runId", "fileName", "status", "startedAt", "finishedAt", "fileRowCount", "insertedRowCount",
                "skippedRowCount", "deletedRowCount", "factRowCount", "errorMessage"]],
        hide_index=True,
        column_config={
            "runId": st.column_config.NumberColumn("Run", format="%d"),
            "fileName": "File",
            "status": "Status",
            "startedAt": st.column_config.DatetimeColumn("Started", format="D MMM YYYY HH:mm"),
            "finishedAt": st.column_config.DatetimeColumn("Finished", format="HH:mm:ss"),
            "fileRowCount": st.column_config.NumberColumn("File rows", format="%,d"),
            "insertedRowCount": st.column_config.NumberColumn("New", format="%,d"),
            "skippedRowCount": st.column_config.NumberColumn("Skipped", format="%,d"),
            "deletedRowCount": st.column_config.NumberColumn("Soft-deleted", format="%,d"),
            "factRowCount": st.column_config.NumberColumn("Active lines after run", format="%,d"),
            "errorMessage": "Error",
        },
    )
    st.caption("New = lines added · Skipped = already in the warehouse · Soft-deleted = removed from a re-sent "
               "invoice (kept with isDeleted = 1). Source: RETAIL_DWH.etl.runLog")
