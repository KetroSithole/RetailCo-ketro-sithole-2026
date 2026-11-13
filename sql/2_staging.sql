/* ============================================================
   2_staging.sql  -  RETAIL_STG

   RETAIL_STG.stg.salesRaw     every CSV file as received (text), never changed
   RETAIL_STG.stg.salesClean   view: salesRaw with the cleaning rules

   Note: SQL Server needs USE for CREATE SCHEMA / VIEW;
   every table reference is written as DATABASE.schema.table.
   ============================================================ */
USE RETAIL_STG;
GO

IF SCHEMA_ID('stg') IS NULL EXEC ('CREATE SCHEMA stg');
GO

IF OBJECT_ID('RETAIL_STG.stg.salesRaw') IS NULL
CREATE TABLE RETAIL_STG.stg.salesRaw (
    runId        INT            NOT NULL,   -- RETAIL_DWH.etl.runLog
    lineNumber   INT            NOT NULL,   -- line number in the file
    invoiceNo    NVARCHAR(100),
    stockCode    NVARCHAR(100),
    description  NVARCHAR(1000),
    quantity     NVARCHAR(100),
    invoiceDate  NVARCHAR(100),
    unitPrice    NVARCHAR(100),
    customerId   NVARCHAR(100),
    country      NVARCHAR(200),
    loadedAt     DATETIME2(0)   NOT NULL CONSTRAINT dfSalesRawLoadedAt DEFAULT SYSDATETIME(),
    CONSTRAINT pkSalesRaw PRIMARY KEY (runId, lineNumber)
);
GO

/* Cleaning rules (applied to one file = one runId at a time)
   1. Text trimmed and upper-cased.
   2. Text converted to numbers / dates     -> isInvalid   = 1 if not possible
   3. Country names standardised.
   4. lineHash = fingerprint of the cleaned line (used to skip lines already loaded)
   5. Exact copy of an earlier line in the same file -> isDuplicate = 1
   6. Each line gets a transactionType and a lineType.                          */
CREATE OR ALTER VIEW stg.salesClean AS
WITH converted AS (
    SELECT
        raw.runId,
        raw.lineNumber,
        raw.loadedAt,
        UPPER(TRIM(raw.invoiceNo))                                     AS invoiceNo,
        TRY_CONVERT(DATETIME2(0), raw.invoiceDate, 101)                AS invoiceDate,
        UPPER(TRIM(raw.stockCode))                                     AS stockCode,
        UPPER(TRIM(REPLACE(REPLACE(raw.description, '   ', ' '), '  ', ' '))) AS description,
        TRY_CAST(raw.quantity AS INT)                                  AS quantity,
        TRY_CAST(raw.unitPrice AS DECIMAL(12, 3))                      AS unitPrice,
        TRY_CAST(TRY_CAST(raw.customerId AS DECIMAL(18, 2)) AS INT)    AS customerId,
        CASE TRIM(raw.country)
            WHEN 'EIRE'        THEN 'Ireland'
            WHEN 'RSA'         THEN 'South Africa'
            WHEN 'USA'         THEN 'United States'
            WHEN 'Unspecified' THEN 'Unknown'
            ELSE ISNULL(TRIM(raw.country), 'Unknown')
        END                                                            AS country
    FROM RETAIL_STG.stg.salesRaw AS raw
),
fingerprinted AS (
    SELECT
        *,
        HASHBYTES('SHA2_256', CONCAT(invoiceNo, '|', CONVERT(CHAR(19), invoiceDate, 120), '|', stockCode, '|',
                                     description, '|', quantity, '|', unitPrice, '|', customerId, '|', country)) AS lineHash
    FROM converted
)
SELECT
    runId,
    lineNumber,
    loadedAt,
    invoiceNo,
    invoiceDate,
    stockCode,
    description,
    quantity,
    unitPrice,
    customerId,
    country,
    lineHash,
    CASE LEFT(invoiceNo, 1)
        WHEN 'C' THEN 'cancellation'
        WHEN 'A' THEN 'adjustment'
        ELSE 'sale'
    END                                                                AS transactionType,
    CASE
        WHEN stockCode IN ('POST', 'DOT', 'C2')                 THEN 'shipping'
        WHEN stockCode IN ('BANK CHARGES', 'AMAZONFEE', 'CRUK') THEN 'fee'
        WHEN stockCode = 'D'                                    THEN 'discount'
        WHEN stockCode = 'M'                                    THEN 'manual'
        WHEN stockCode = 'S'                                    THEN 'samples'
        WHEN stockCode = 'B'                                    THEN 'badDebt'
        WHEN stockCode LIKE 'GIFT[_]%'                          THEN 'giftVoucher'
        WHEN unitPrice = 0 AND customerId IS NULL               THEN 'stockAdjustment'  -- "damaged", "?" notes
        ELSE 'product'
    END                                                                AS lineType,
    CAST(ROUND(quantity * unitPrice, 2) AS DECIMAL(18, 2))             AS lineAmount,
    IIF(ROW_NUMBER() OVER (PARTITION BY runId, lineHash ORDER BY lineNumber) > 1, 1, 0) AS isDuplicate,
    IIF(invoiceNo IS NULL OR invoiceDate IS NULL OR stockCode IS NULL
        OR quantity IS NULL OR unitPrice IS NULL, 1, 0)                AS isInvalid
FROM fingerprinted;
GO
