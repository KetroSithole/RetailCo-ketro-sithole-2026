/* ============================================================
   1_databases.sql
   RETAIL_STG  staging database   - files as received + cleaning
   RETAIL_DWH  data warehouse     - star schema + ETL tracking
   ============================================================ */

IF DB_ID('RETAIL_STG') IS NULL CREATE DATABASE RETAIL_STG;
IF DB_ID('RETAIL_DWH') IS NULL CREATE DATABASE RETAIL_DWH;
GO
