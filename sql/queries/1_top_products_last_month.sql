-- Q1. Top 10 products by net sales last month (November 2011, the last full month in the data)
WITH productSales AS (
    SELECT
        product.stockCode,
        SUM(sales.netAmount) AS netAmount
    FROM RETAIL_DWH.fact.sales    AS sales
    JOIN RETAIL_DWH.dim.product   AS product  ON product.productKey   = sales.productKey
    JOIN RETAIL_DWH.dim.calendar  AS calendar ON calendar.calendarKey = sales.calendarKey
    WHERE sales.isDeleted = 0
      AND calendar.yearMonth = '2011-11'
    GROUP BY product.stockCode
)
SELECT TOP 10
    productSales.stockCode,
    currentProduct.description,           -- current version of the product (SCD2)
    productSales.netAmount
FROM productSales
JOIN RETAIL_DWH.dim.product AS currentProduct
  ON currentProduct.stockCode = productSales.stockCode
 AND currentProduct.isCurrent = 1
ORDER BY productSales.netAmount DESC;
