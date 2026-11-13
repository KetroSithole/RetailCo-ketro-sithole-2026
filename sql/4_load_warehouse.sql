/* ============================================================
   4_load_warehouse.sql  -  RETAIL_DWH.etl.loadWarehouse

   Loads ONE file (one runId) from RETAIL_STG into RETAIL_DWH.
   Nothing is truncated or physically deleted:

     dim.calendar   add days that are missing
     dim.product    SCD type 2 - new product -> insert; changed description/type -> close old row, insert new version
     dim.customer   SCD type 2 - new customer -> insert; changed country -> close old row, insert new version
     fact.sales     line already loaded (same lineHash) -> skip
                    new line                            -> insert
                    invoice re-sent without a line      -> soft delete (isDeleted = 1, deletedAt)

   One transaction: if a step fails, nothing changes and the error is saved
   in RETAIL_DWH.etl.runLog. Running the same runId again is safe (all lines are skipped).

   Run by hand:  EXEC RETAIL_DWH.etl.loadWarehouse @runId = 1;
   ============================================================ */
USE RETAIL_DWH;
GO

CREATE OR ALTER PROCEDURE etl.loadWarehouse
    @runId INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @now                  DATETIME2(0) = SYSDATETIME();
    DECLARE @openEnded            DATETIME2(0) = '9999-12-31';
    DECLARE @insertedCount        INT = 0;
    DECLARE @deletedCount         INT = 0;
    DECLARE @newProductCount      INT = 0;
    DECLARE @productVersionCount  INT = 0;
    DECLARE @newCustomerCount     INT = 0;
    DECLARE @customerVersionCount INT = 0;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 1. This file's cleaned rows ---------------------------------------------
        SELECT * INTO #fileRows  FROM RETAIL_STG.stg.salesClean WHERE runId = @runId;
        SELECT * INTO #validRows FROM #fileRows WHERE isDuplicate = 0 AND isInvalid = 0;

        -- 2. dim.calendar: add missing days -------------------------------------------
        DECLARE @firstDate DATE = (SELECT DATEFROMPARTS(YEAR(MIN(invoiceDate)), 1, 1)   FROM #validRows);
        DECLARE @lastDate  DATE = (SELECT DATEFROMPARTS(YEAR(MAX(invoiceDate)), 12, 31) FROM #validRows);

        IF @firstDate IS NOT NULL
            INSERT INTO RETAIL_DWH.dim.calendar
                (calendarKey, calendarDate, yearNo, quarterNo, monthNo, monthName, yearMonth, yearQuarter)
            SELECT
                CONVERT(CHAR(8), dayList.calendarDate, 112),
                dayList.calendarDate,
                YEAR(dayList.calendarDate),
                DATEPART(QUARTER, dayList.calendarDate),
                MONTH(dayList.calendarDate),
                DATENAME(MONTH, dayList.calendarDate),
                FORMAT(dayList.calendarDate, 'yyyy-MM'),
                CONCAT(YEAR(dayList.calendarDate), '-Q', DATEPART(QUARTER, dayList.calendarDate))
            FROM GENERATE_SERIES(0, DATEDIFF(DAY, @firstDate, @lastDate)) AS dayOffset
            CROSS APPLY (SELECT DATEADD(DAY, dayOffset.value, @firstDate) AS calendarDate) AS dayList
            WHERE NOT EXISTS (SELECT 1 FROM RETAIL_DWH.dim.calendar AS calendar
                              WHERE calendar.calendarDate = dayList.calendarDate);

        -- 3. dim.product (SCD type 2) ---------------------------------------------------
        -- The product as it appears in this file: most used real description per stock code.
        SELECT stockCode, description, productType, firstSeenDate, isRealDescription
        INTO #fileProducts
        FROM (
            SELECT
                stockCode,
                description,
                IIF(lineType = 'stockAdjustment', 'product', lineType)                AS productType,
                MIN(MIN(invoiceDate)) OVER (PARTITION BY stockCode)                   AS firstSeenDate,
                IIF(lineType = 'stockAdjustment' OR description IS NULL, 0, 1)        AS isRealDescription,
                ROW_NUMBER() OVER (
                    PARTITION BY stockCode
                    ORDER BY IIF(lineType = 'stockAdjustment' OR description IS NULL, 1, 0),
                             COUNT(*) DESC, MAX(invoiceDate) DESC
                ) AS popularityRank
            FROM #validRows
            GROUP BY stockCode, description, lineType
        ) AS rankedProducts
        WHERE popularityRank = 1;

        -- Changed products: a real description or type that differs from the current version.
        SELECT
            fileProduct.stockCode,
            fileProduct.description,
            fileProduct.productType,
            GREATEST(fileProduct.firstSeenDate, DATEADD(SECOND, 1, currentProduct.validFrom)) AS newValidFrom
        INTO #changedProducts
        FROM #fileProducts AS fileProduct
        JOIN RETAIL_DWH.dim.product AS currentProduct
          ON currentProduct.stockCode = fileProduct.stockCode
         AND currentProduct.isCurrent = 1
        WHERE fileProduct.isRealDescription = 1
          AND (ISNULL(currentProduct.description, '') <> ISNULL(fileProduct.description, '')
               OR currentProduct.productType <> fileProduct.productType);

        UPDATE currentProduct
        SET validTo   = changedProduct.newValidFrom,
            isCurrent = 0,
            updatedAt = @now
        FROM RETAIL_DWH.dim.product AS currentProduct
        JOIN #changedProducts AS changedProduct ON changedProduct.stockCode = currentProduct.stockCode
        WHERE currentProduct.isCurrent = 1;

        INSERT INTO RETAIL_DWH.dim.product (stockCode, description, productType, validFrom, validTo, isCurrent)
        SELECT stockCode, description, productType, newValidFrom, @openEnded, 1
        FROM #changedProducts;
        SET @productVersionCount = @@ROWCOUNT;

        -- New products: first version is valid from the beginning.
        INSERT INTO RETAIL_DWH.dim.product (stockCode, description, productType, validFrom, validTo, isCurrent)
        SELECT stockCode, ISNULL(description, 'UNKNOWN'), productType, '1900-01-01', @openEnded, 1
        FROM #fileProducts AS fileProduct
        WHERE NOT EXISTS (SELECT 1 FROM RETAIL_DWH.dim.product AS product WHERE product.stockCode = fileProduct.stockCode);
        SET @newProductCount = @@ROWCOUNT;

        -- 4. dim.customer (SCD type 2) --------------------------------------------------
        -- The customer as it appears in this file: the most recent country.
        SELECT customerId, country, countryFirstSeenDate
        INTO #fileCustomers
        FROM (
            SELECT
                customerId,
                country,
                MIN(invoiceDate) OVER (PARTITION BY customerId, country)              AS countryFirstSeenDate,
                ROW_NUMBER() OVER (PARTITION BY customerId ORDER BY invoiceDate DESC) AS recencyRank
            FROM #validRows
            WHERE customerId IS NOT NULL
        ) AS rankedCustomers
        WHERE recencyRank = 1;

        SELECT
            fileCustomer.customerId,
            fileCustomer.country,
            GREATEST(fileCustomer.countryFirstSeenDate, DATEADD(SECOND, 1, currentCustomer.validFrom)) AS newValidFrom
        INTO #changedCustomers
        FROM #fileCustomers AS fileCustomer
        JOIN RETAIL_DWH.dim.customer AS currentCustomer
          ON currentCustomer.customerId = fileCustomer.customerId
         AND currentCustomer.isCurrent = 1
        WHERE currentCustomer.country <> fileCustomer.country;

        UPDATE currentCustomer
        SET validTo   = changedCustomer.newValidFrom,
            isCurrent = 0,
            updatedAt = @now
        FROM RETAIL_DWH.dim.customer AS currentCustomer
        JOIN #changedCustomers AS changedCustomer ON changedCustomer.customerId = currentCustomer.customerId
        WHERE currentCustomer.isCurrent = 1;

        INSERT INTO RETAIL_DWH.dim.customer (customerId, country, validFrom, validTo, isCurrent)
        SELECT customerId, country, newValidFrom, @openEnded, 1
        FROM #changedCustomers;
        SET @customerVersionCount = @@ROWCOUNT;

        INSERT INTO RETAIL_DWH.dim.customer (customerId, country, validFrom, validTo, isCurrent)
        SELECT customerId, country, '1900-01-01', @openEnded, 1
        FROM #fileCustomers AS fileCustomer
        WHERE NOT EXISTS (SELECT 1 FROM RETAIL_DWH.dim.customer AS customer WHERE customer.customerId = fileCustomer.customerId);
        SET @newCustomerCount = @@ROWCOUNT;

        -- 5. fact.sales: soft delete lines missing from a re-sent invoice ----------------
        -- A file holds complete invoices, so for every invoice in this file,
        -- an active line that is not in the file any more has been removed at the source.
        UPDATE sales
        SET isDeleted    = 1,
            deletedAt    = @now,
            deletedRunId = @runId
        FROM RETAIL_DWH.fact.sales AS sales
        WHERE sales.isDeleted = 0
          AND sales.invoiceNo IN (SELECT invoiceNo FROM #validRows)
          AND NOT EXISTS (SELECT 1 FROM #validRows AS fileLine WHERE fileLine.lineHash = sales.lineHash);
        SET @deletedCount = @@ROWCOUNT;

        -- 6. fact.sales: insert new lines, skip lines that are already loaded -------------
        INSERT INTO RETAIL_DWH.fact.sales (
            invoiceNo, lineNumber, invoiceAt, calendarKey, productKey, customerKey, country, transactionType, lineType,
            quantity, unitPrice, lineAmount, salesAmount, cancelledAmount, netAmount, lineHash, runId)
        SELECT
            fileLine.invoiceNo,
            fileLine.lineNumber,
            fileLine.invoiceDate,
            CONVERT(CHAR(8), fileLine.invoiceDate, 112),
            productVersion.productKey,
            ISNULL(customerVersion.customerKey, 0),
            fileLine.country,
            fileLine.transactionType,
            fileLine.lineType,
            fileLine.quantity,
            fileLine.unitPrice,
            fileLine.lineAmount,
            IIF(fileLine.lineType = 'product' AND fileLine.transactionType = 'sale',          fileLine.lineAmount, 0),
            IIF(fileLine.lineType = 'product' AND fileLine.transactionType = 'cancellation', -fileLine.lineAmount, 0),
            IIF(fileLine.lineType = 'product',                                                fileLine.lineAmount, 0),
            fileLine.lineHash,
            @runId
        FROM #validRows AS fileLine
        OUTER APPLY (   -- product version that was valid on the invoice date
            SELECT TOP 1 product.productKey
            FROM RETAIL_DWH.dim.product AS product
            WHERE product.stockCode = fileLine.stockCode AND product.validFrom <= fileLine.invoiceDate
            ORDER BY product.validFrom DESC
        ) AS productVersion
        OUTER APPLY (   -- customer version that was valid on the invoice date
            SELECT TOP 1 customer.customerKey
            FROM RETAIL_DWH.dim.customer AS customer
            WHERE customer.customerId = fileLine.customerId AND customer.validFrom <= fileLine.invoiceDate
            ORDER BY customer.validFrom DESC
        ) AS customerVersion
        WHERE NOT EXISTS (SELECT 1 FROM RETAIL_DWH.fact.sales AS sales
                          WHERE sales.lineHash = fileLine.lineHash AND sales.isDeleted = 0);
        SET @insertedCount = @@ROWCOUNT;

        -- 7. etl.dataQuality -----------------------------------------------------------------
        DELETE FROM RETAIL_DWH.etl.dataQuality WHERE runId = @runId;

        INSERT INTO RETAIL_DWH.etl.dataQuality (runId, checkName, recordCount, action)
        SELECT @runId, checkList.checkName, checkList.recordCount, checkList.action
        FROM (
            SELECT
                SUM(isDuplicate)                                                      AS duplicateCount,
                SUM(IIF(isDuplicate = 0, isInvalid, 0))                               AS invalidCount,
                SUM(IIF(isDuplicate = 0 AND customerId IS NULL, 1, 0))                AS guestCount,
                SUM(IIF(isDuplicate = 0 AND transactionType = 'cancellation', 1, 0))  AS cancellationCount,
                SUM(IIF(isDuplicate = 0 AND lineType NOT IN ('product', 'stockAdjustment'), 1, 0)) AS nonProductCount,
                SUM(IIF(isDuplicate = 0 AND lineType = 'stockAdjustment', 1, 0))      AS stockAdjustmentCount,
                SUM(IIF(isDuplicate = 0 AND ABS(quantity) >= 10000, 1, 0))            AS largeQuantityCount,
                SUM(IIF(isDuplicate = 0 AND unitPrice < 0, 1, 0))                     AS negativePriceCount
            FROM #fileRows
        ) AS totals
        CROSS APPLY (VALUES
            ('duplicateRows',          duplicateCount,        'removed'),
            ('invalidRows',            invalidCount,          'removed'),
            ('guestRows',              guestCount,            'kept as customerKey 0'),
            ('cancellations',          cancellationCount,     'kept as cancelledAmount'),
            ('nonProductRows',         nonProductCount,       'kept, not in salesAmount'),
            ('stockAdjustments',       stockAdjustmentCount,  'kept, not in salesAmount'),
            ('largeQuantities',        largeQuantityCount,    'kept, needs review'),
            ('negativePrices',         negativePriceCount,    'kept, needs review'),
            ('newProducts',            @newProductCount,      'dim.product row added'),
            ('changedProducts',        @productVersionCount,  'dim.product new version (SCD2)'),
            ('newCustomers',           @newCustomerCount,     'dim.customer row added'),
            ('changedCustomers',       @customerVersionCount, 'dim.customer new version (SCD2)')
        ) AS checkList (checkName, recordCount, action);

        -- 8. etl.runLog: success ---------------------------------------------------------------
        UPDATE RETAIL_DWH.etl.runLog
        SET status           = 'success',
            finishedAt       = SYSDATETIME(),
            insertedRowCount = @insertedCount,
            skippedRowCount  = (SELECT COUNT(*) FROM #validRows) - @insertedCount,
            deletedRowCount  = @deletedCount,
            factRowCount     = (SELECT COUNT(*) FROM RETAIL_DWH.fact.sales WHERE isDeleted = 0),
            errorMessage     = NULL
        WHERE runId = @runId;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;

        UPDATE RETAIL_DWH.etl.runLog
        SET status       = 'failed',
            finishedAt   = SYSDATETIME(),
            errorMessage = ERROR_MESSAGE()
        WHERE runId = @runId;
    END CATCH;

    SELECT status, insertedRowCount, skippedRowCount, deletedRowCount, factRowCount, errorMessage
    FROM RETAIL_DWH.etl.runLog
    WHERE runId = @runId;
END;
GO
