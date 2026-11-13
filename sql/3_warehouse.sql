/* ============================================================
   3_warehouse.sql  -  RETAIL_DWH

   RETAIL_DWH.dim.calendar      one row per day
   RETAIL_DWH.dim.product       one row per product VERSION   (SCD type 2)
   RETAIL_DWH.dim.customer      one row per customer VERSION  (SCD type 2, key 0 = guest)
   RETAIL_DWH.fact.sales        one row per sales line (insert-only, soft deletes)
   RETAIL_DWH.etl.runLog        one row per file processed
   RETAIL_DWH.etl.dataQuality   data-quality counts per run
   ============================================================ */
USE RETAIL_DWH;
GO

IF SCHEMA_ID('dim')  IS NULL EXEC ('CREATE SCHEMA dim');
IF SCHEMA_ID('fact') IS NULL EXEC ('CREATE SCHEMA fact');
IF SCHEMA_ID('etl')  IS NULL EXEC ('CREATE SCHEMA etl');
GO

-- etl -------------------------------------------------------------
IF OBJECT_ID('RETAIL_DWH.etl.runLog') IS NULL
CREATE TABLE RETAIL_DWH.etl.runLog (
    runId             INT IDENTITY,
    fileName          NVARCHAR(260),
    fileHash          CHAR(64),                -- skips a file that was already loaded
    status            VARCHAR(10),             -- loading / success / failed
    startedAt         DATETIME2(0) CONSTRAINT dfRunLogStartedAt DEFAULT SYSDATETIME(),
    finishedAt        DATETIME2(0),
    fileRowCount      INT,                     -- lines in the file
    insertedRowCount  INT,                     -- new lines added to fact.sales
    skippedRowCount   INT,                     -- lines already in fact.sales
    deletedRowCount   INT,                     -- lines soft-deleted (missing from a re-sent invoice)
    factRowCount      INT,                     -- active lines in fact.sales after the run
    errorMessage      NVARCHAR(4000),
    CONSTRAINT pkRunLog PRIMARY KEY (runId)
);

IF OBJECT_ID('RETAIL_DWH.etl.dataQuality') IS NULL
CREATE TABLE RETAIL_DWH.etl.dataQuality (
    runId        INT,
    checkName    VARCHAR(50),
    recordCount  INT,
    action       VARCHAR(100),
    checkedAt    DATETIME2(0) CONSTRAINT dfDataQualityCheckedAt DEFAULT SYSDATETIME(),
    CONSTRAINT pkDataQuality PRIMARY KEY (runId, checkName)
);

-- dim -------------------------------------------------------------
IF OBJECT_ID('RETAIL_DWH.dim.calendar') IS NULL
CREATE TABLE RETAIL_DWH.dim.calendar (
    calendarKey   INT,                         -- 20111209
    calendarDate  DATE,
    yearNo        INT,
    quarterNo     INT,
    monthNo       INT,
    monthName     VARCHAR(10),
    yearMonth     CHAR(7),                     -- 2011-12
    yearQuarter   CHAR(7),                     -- 2011-Q4
    loadedAt      DATETIME2(0) CONSTRAINT dfCalendarLoadedAt DEFAULT SYSDATETIME(),
    CONSTRAINT pkCalendar PRIMARY KEY (calendarKey)
);

-- SCD type 2: a change creates a new row; the old row gets validTo and isCurrent = 0.
IF OBJECT_ID('RETAIL_DWH.dim.product') IS NULL
BEGIN
    CREATE TABLE RETAIL_DWH.dim.product (
        productKey   INT IDENTITY,
        stockCode    NVARCHAR(100),             -- business key
        description  NVARCHAR(1000),
        productType  VARCHAR(20),               -- product, shipping, fee, discount, ...
        validFrom    DATETIME2(0),
        validTo      DATETIME2(0),              -- 9999-12-31 for the current version
        isCurrent    BIT,
        createdAt    DATETIME2(0) CONSTRAINT dfProductCreatedAt DEFAULT SYSDATETIME(),
        updatedAt    DATETIME2(0),              -- when the version was closed
        CONSTRAINT pkProduct PRIMARY KEY (productKey)
    );
    CREATE INDEX ixProductStockCode ON RETAIL_DWH.dim.product (stockCode, validFrom) INCLUDE (productKey, isCurrent);
END;

IF OBJECT_ID('RETAIL_DWH.dim.customer') IS NULL
BEGIN
    CREATE TABLE RETAIL_DWH.dim.customer (
        customerKey  INT IDENTITY(0, 1),        -- 0 = guest (no customer id)
        customerId   INT,                       -- business key
        country      NVARCHAR(100),
        validFrom    DATETIME2(0),
        validTo      DATETIME2(0),              -- 9999-12-31 for the current version
        isCurrent    BIT,
        createdAt    DATETIME2(0) CONSTRAINT dfCustomerCreatedAt DEFAULT SYSDATETIME(),
        updatedAt    DATETIME2(0),              -- when the version was closed
        CONSTRAINT pkCustomer PRIMARY KEY (customerKey)
    );
    CREATE INDEX ixCustomerCustomerId ON RETAIL_DWH.dim.customer (customerId, validFrom) INCLUDE (customerKey, isCurrent);
    INSERT INTO RETAIL_DWH.dim.customer (customerId, country, validFrom, validTo, isCurrent)
    VALUES (NULL, 'Unknown', '1900-01-01', '9999-12-31', 1);
END;

-- fact ------------------------------------------------------------
-- Insert-only. A line is identified by lineHash; existing lines are skipped.
-- Lines missing from a re-sent invoice are soft-deleted (isDeleted = 1), never removed.
IF OBJECT_ID('RETAIL_DWH.fact.sales') IS NULL
BEGIN
    CREATE TABLE RETAIL_DWH.fact.sales (
        salesKey          BIGINT IDENTITY,
        invoiceNo         NVARCHAR(100),
        lineNumber        INT,                  -- line number in the source file
        invoiceAt         DATETIME2(0),         -- invoice date and time (for time-of-day analysis)
        calendarKey       INT,                  -- dim.calendar
        productKey        INT,                  -- dim.product (version valid on the invoice date)
        customerKey       INT,                  -- dim.customer (version valid on the invoice date)
        country           NVARCHAR(100),
        transactionType   VARCHAR(12),          -- sale, cancellation, adjustment
        lineType          VARCHAR(20),          -- product, shipping, fee, ..., stockAdjustment
        quantity          INT,
        unitPrice         DECIMAL(12, 3),
        lineAmount        DECIMAL(18, 2),       -- quantity x unitPrice
        salesAmount       DECIMAL(18, 2),       -- product sales
        cancelledAmount   DECIMAL(18, 2),       -- product cancellations (positive)
        netAmount         DECIMAL(18, 2),       -- salesAmount - cancelledAmount
        lineHash          BINARY(32),           -- fingerprint of the line
        runId             INT,                  -- run that inserted the line
        loadedAt          DATETIME2(0) CONSTRAINT dfSalesLoadedAt DEFAULT SYSDATETIME(),
        isDeleted         BIT CONSTRAINT dfSalesIsDeleted DEFAULT 0,
        deletedAt         DATETIME2(0),
        deletedRunId      INT,                  -- run that soft-deleted the line
        CONSTRAINT pkSales PRIMARY KEY (salesKey)
    );
    CREATE UNIQUE INDEX uxSalesLineHash ON RETAIL_DWH.fact.sales (lineHash) WHERE isDeleted = 0;
    CREATE INDEX ixSalesInvoiceNo ON RETAIL_DWH.fact.sales (invoiceNo) INCLUDE (lineHash, isDeleted);
END;
GO
