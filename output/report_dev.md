# Report - dev

## Q1. Top 10 products by net sales last month (November 2011, the last full month in the data)

| stockCode | description | netAmount |
|---|---|---|
| 23084 | RABBIT NIGHT LIGHT | 34,343.77 |
| 22086 | PAPER CHAIN KIT 50'S CHRISTMAS | 28,853.54 |
| 85123A | WHITE HANGING HEART T-LIGHT HOLDER | 14,339.32 |
| 22197 | POPCORN HOLDER | 13,961.94 |
| 22910 | PAPER CHAIN KIT VINTAGE CHRISTMAS | 12,816.79 |
| 22423 | REGENCY CAKESTAND 3 TIER | 12,772.98 |
| 79321 | CHILLI LIGHTS | 11,475.07 |
| 85099B | JUMBO BAG RED RETROSPOT | 11,456.13 |
| 23355 | HOT WATER BOTTLE KEEP CALM | 11,436.52 |
| 23344 | JUMBO BAG 50'S CHRISTMAS | 10,881.90 |

## Q2. Countries with the most orders in Q4 2011 (an order = an invoice with product sales)

| country | orderCount |
|---|---|
| United Kingdom | 5,014 |
| Germany | 137 |
| France | 114 |
| Ireland | 83 |
| Netherlands | 32 |
| Belgium | 26 |
| Spain | 23 |
| Portugal | 21 |
| Finland | 17 |
| Italy | 15 |

## Q3. Average order value by month (order value = everything on the invoice except stock adjustments)

| yearMonth | orderCount | averageOrderAmount |
|---|---|---|
| 2010-12 | 1,550 | 519.43 |
| 2011-01 | 1,081 | 638.03 |
| 2011-02 | 1,093 | 476.99 |
| 2011-03 | 1,440 | 491.67 |
| 2011-04 | 1,235 | 426.25 |
| 2011-05 | 1,668 | 452.88 |
| 2011-06 | 1,525 | 495.11 |
| 2011-07 | 1,452 | 486.46 |
| 2011-08 | 1,339 | 554.62 |
| 2011-09 | 1,818 | 577.48 |
| 2011-10 | 2,005 | 563.33 |
| 2011-11 | 2,751 | 545.56 |
| 2011-12 | 816 | 781.48 |

## Q4. Customers with more than 5 purchases (guests not included)

| customerId | country | orderCount | salesAmount |
|---|---|---|---|
| 12748 | United Kingdom | 206 | 31,650.78 |
| 14911 | Ireland | 198 | 136,161.83 |
| 17841 | United Kingdom | 124 | 40,495.99 |
| 13089 | United Kingdom | 97 | 58,762.08 |
| 15311 | United Kingdom | 91 | 60,632.75 |
| 14606 | United Kingdom | 90 | 11,926.15 |
| 12971 | United Kingdom | 86 | 11,189.91 |
| 14646 | Netherlands | 72 | 279,138.02 |
| 13408 | United Kingdom | 62 | 28,117.04 |
| 16029 | United Kingdom | 62 | 72,708.09 |
| 18102 | United Kingdom | 60 | 259,657.30 |
| 13798 | United Kingdom | 57 | 37,153.85 |
| 14527 | United Kingdom | 55 | 8,506.13 |
| 14156 | Ireland | 54 | 116,560.08 |
| 16422 | United Kingdom | 51 | 34,684.40 |

_865 rows, first 15 shown_

## Data quality (latest run)

| checkName | recordCount | action |
|---|---|---|
| guestRows | 135,037 | kept as customerKey 0 |
| cancellations | 9,251 | kept as cancelledAmount |
| duplicateRows | 5,268 | removed |
| newCustomers | 4,372 | dim.customer row added |
| newProducts | 3,958 | dim.product row added |
| nonProductRows | 2,940 | kept, not in salesAmount |
| stockAdjustments | 2,459 | kept, not in salesAmount |
| largeQuantities | 5 | kept, needs review |
| negativePrices | 2 | kept, needs review |
| changedProducts | 0 | dim.product new version (SCD2) |
| changedCustomers | 0 | dim.customer new version (SCD2) |
| invalidRows | 0 | removed |

## ETL runs

| runId | fileName | status | startedAt | fileRowCount | insertedRowCount | skippedRowCount | deletedRowCount | factRowCount | errorMessage |
|---|---|---|---|---|---|---|---|---|---|
| 1 | online_retail_20261113.csv | success | 2026-11-13 19:47:36 | 541,909 | 536,641 | 0 | 0 | 536,641 |  |
