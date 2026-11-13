-- Q2. Countries with the most orders in Q4 2011 (an order = an invoice with product sales)
SELECT TOP 10
    sales.country,
    COUNT(DISTINCT sales.invoiceNo) AS orderCount
FROM RETAIL_DWH.fact.sales    AS sales
JOIN RETAIL_DWH.dim.calendar  AS calendar ON calendar.calendarKey = sales.calendarKey
WHERE sales.isDeleted = 0
  AND calendar.yearQuarter = '2011-Q4'
  AND sales.salesAmount > 0
GROUP BY sales.country
ORDER BY orderCount DESC;
