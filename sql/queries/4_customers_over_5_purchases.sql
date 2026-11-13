-- Q4. Customers with more than 5 purchases (guests not included)
WITH customerOrders AS (
    SELECT
        customer.customerId,
        COUNT(DISTINCT sales.invoiceNo) AS orderCount,
        SUM(sales.salesAmount)          AS salesAmount
    FROM RETAIL_DWH.fact.sales    AS sales
    JOIN RETAIL_DWH.dim.customer  AS customer ON customer.customerKey = sales.customerKey
    WHERE sales.isDeleted = 0
      AND sales.customerKey <> 0
      AND sales.salesAmount > 0
    GROUP BY customer.customerId          -- all versions of the customer (SCD2) together
    HAVING COUNT(DISTINCT sales.invoiceNo) > 5
)
SELECT
    customerOrders.customerId,
    currentCustomer.country,              -- current version of the customer
    customerOrders.orderCount,
    customerOrders.salesAmount
FROM customerOrders
JOIN RETAIL_DWH.dim.customer AS currentCustomer
  ON currentCustomer.customerId = customerOrders.customerId
 AND currentCustomer.isCurrent = 1
ORDER BY customerOrders.orderCount DESC;
