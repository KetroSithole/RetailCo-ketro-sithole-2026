"""The four pipeline commands: setup, extract, run and report."""
import csv
import hashlib
import shutil
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pyodbc

from .settings import PROJECT_FOLDER, Settings

SQL_FOLDER = PROJECT_FOLDER / "sql"
SOURCE_URL = "https://archive.ics.uci.edu/static/public/352/data.csv"  # UCI Online Retail dataset

# CSV header -> column in RETAIL_STG.stg.salesRaw
CSV_COLUMNS = {
    "InvoiceNo": "invoiceNo",
    "StockCode": "stockCode",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoiceDate",
    "UnitPrice": "unitPrice",
    "CustomerID": "customerId",
    "Country": "country",
}


def connect(settings: Settings) -> pyodbc.Connection:
    return pyodbc.connect(settings.connectionString(), autocommit=True)


# ---------------------------------------------------------------- setup
def setup(settings: Settings) -> None:
    """Create RETAIL_STG and RETAIL_DWH with all tables, the view and the procedure."""
    settings.createFolders()
    with connect(settings) as connection:
        for script in sorted(SQL_FOLDER.glob("*.sql")):
            for batch in script.read_text(encoding="utf-8").split("\nGO"):
                if batch.strip():
                    connection.execute(batch)
            print(f"ran sql/{script.name}")


# ---------------------------------------------------------------- extract
def extract(settings: Settings) -> None:
    """Download the source CSV into the inbox folder."""
    settings.createFolders()
    filePath = settings.inboxFolder / f"online_retail_{date.today():%Y%m%d}.csv"
    urllib.request.urlretrieve(SOURCE_URL, filePath)
    print(f"downloaded {filePath.name}")


# ---------------------------------------------------------------- run
def run(settings: Settings) -> bool:
    """For each CSV in the inbox: load to staging, build the warehouse, move the file."""
    settings.createFolders()
    files = sorted(settings.inboxFolder.glob("*.csv"))
    if not files:
        print("inbox is empty")
        return True

    allSucceeded = True
    with connect(settings) as connection:
        for filePath in files:
            succeeded = processFile(connection, filePath)
            destination = settings.archiveFolder if succeeded else settings.errorFolder
            shutil.move(filePath, destination / f"{datetime.now():%Y%m%d_%H%M%S}_{filePath.name}")
            print(f"{filePath.name}: moved to {destination.name}")
            allSucceeded = allSucceeded and succeeded
    return allSucceeded


def processFile(connection: pyodbc.Connection, filePath: Path) -> bool:
    fileHash = hashlib.sha256(filePath.read_bytes()).hexdigest()

    alreadyLoaded = connection.execute(
        "SELECT 1 FROM RETAIL_DWH.etl.runLog WHERE fileHash = ? AND status = 'success'", fileHash).fetchone()
    if alreadyLoaded:
        print(f"{filePath.name}: already loaded before, skipped")
        return True

    runId = connection.execute(
        "INSERT INTO RETAIL_DWH.etl.runLog (fileName, fileHash, status) OUTPUT INSERTED.runId "
        "VALUES (?, ?, 'loading')", filePath.name, fileHash).fetchone()[0]

    try:
        rowCount = loadFileToStaging(connection, runId, filePath)
        connection.execute("UPDATE RETAIL_DWH.etl.runLog SET fileRowCount = ? WHERE runId = ?", rowCount, runId)
        print(f"{filePath.name}: {rowCount:,} rows loaded into RETAIL_STG.stg.salesRaw")

        status, insertedCount, skippedCount, deletedCount, factRowCount, errorMessage = connection.execute(
            "EXEC RETAIL_DWH.etl.loadWarehouse @runId = ?", runId).fetchone()
        if status != "success":
            raise RuntimeError(errorMessage)
        print(f"{filePath.name}: RETAIL_DWH updated - {insertedCount:,} new, {skippedCount:,} already loaded, "
              f"{deletedCount:,} soft-deleted; fact.sales has {factRowCount:,} active rows")
        return True

    except Exception as error:
        connection.execute("DELETE FROM RETAIL_STG.stg.salesRaw WHERE runId = ?", runId)
        connection.execute(
            "UPDATE RETAIL_DWH.etl.runLog SET status = 'failed', finishedAt = SYSDATETIME(), errorMessage = ? "
            "WHERE runId = ?", str(error)[:4000], runId)
        print(f"{filePath.name}: FAILED - {error}")
        return False


def loadFileToStaging(connection: pyodbc.Connection, runId: int, filePath: Path) -> int:
    with filePath.open(encoding="utf-8", newline="") as csvFile:
        reader = csv.reader(csvFile)
        header = next(reader)
        missingColumns = [column for column in CSV_COLUMNS if column not in header]
        if missingColumns:
            raise ValueError(f"missing columns {missingColumns}")
        positions = [header.index(column) for column in CSV_COLUMNS]
        rows = [[runId, lineNumber] + [line[position] or None for position in positions]
                for lineNumber, line in enumerate(reader, start=1)]

    insertSql = (f"INSERT INTO RETAIL_STG.stg.salesRaw (runId, lineNumber, {', '.join(CSV_COLUMNS.values())}) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    cursor = connection.cursor()
    cursor.fast_executemany = True
    connection.autocommit = False          # load the whole file in one transaction
    try:
        for start in range(0, len(rows), 20_000):
            cursor.executemany(insertSql, rows[start:start + 20_000])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.autocommit = True
    return len(rows)


# ---------------------------------------------------------------- report
def report(settings: Settings) -> None:
    """Run the business queries and save the results to output/report_<environment>.md."""
    lines = [f"# Report - {settings.environment}"]

    with connect(settings) as connection:
        for script in sorted((SQL_FOLDER / "queries").glob("*.sql")):
            sql = script.read_text(encoding="utf-8")
            title = sql.splitlines()[0].lstrip("- ")
            lines += ["", f"## {title}", ""] + markdownTable(connection.execute(sql))

        lines += ["", "## Data quality (latest run)", ""] + markdownTable(connection.execute(
            "SELECT checkName, recordCount, action FROM RETAIL_DWH.etl.dataQuality "
            "WHERE runId = (SELECT MAX(runId) FROM RETAIL_DWH.etl.dataQuality) ORDER BY recordCount DESC"))

        lines += ["", "## ETL runs", ""] + markdownTable(connection.execute(
            "SELECT TOP 10 runId, fileName, status, startedAt, fileRowCount, insertedRowCount, skippedRowCount, deletedRowCount, factRowCount, errorMessage "
            "FROM RETAIL_DWH.etl.runLog ORDER BY runId DESC"))

    reportFile = PROJECT_FOLDER / "output" / f"report_{settings.environment}.md"
    reportFile.parent.mkdir(exist_ok=True)
    reportFile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved {reportFile.relative_to(PROJECT_FOLDER)}")


def markdownTable(cursor: pyodbc.Cursor, maxRows: int = 15) -> list[str]:
    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()

    def formatValue(value, column):
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return f"{value:,.2f}"
        if isinstance(value, int) and not column.endswith("Id"):
            return f"{value:,}"
        return str(value)

    table = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows[:maxRows]:
        table.append("| " + " | ".join(formatValue(value, column) for value, column in zip(row, columns)) + " |")
    if len(rows) > maxRows:
        table.append(f"\n_{len(rows)} rows, first {maxRows} shown_")
    return table
