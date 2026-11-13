-- Q3. Average order value by month (order value = everything on the invoice except stock adjustments)
WITH orders AS (
    SELECT
        invoiceNo,
        MIN(calendarKey)                                       AS calendarKey,
        SUM(IIF(lineType <> 'stockAdjustment', lineAmount, 0)) AS orderAmount
    FROM RETAIL_DWH.fact.sales
    WHERE isDeleted = 0
      AND transactionType = 'sale'
    GROUP BY invoiceNo
    HAVING SUM(salesAmount) > 0
)
SELECT
    calendar.yearMonth,
    COUNT(*)                                        AS orderCount,
    CAST(AVG(orders.orderAmount) AS DECIMAL(18, 2)) AS averageOrderAmount
FROM orders
JOIN RETAIL_DWH.dim.calendar AS calendar ON calendar.calendarKey = orders.calendarKey
GROUP BY calendar.yearMonth
ORDER BY calendar.yearMonth;
