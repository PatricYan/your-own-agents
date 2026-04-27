You are a data engineer. The initial cleaning wasn't sufficient. Apply a deeper cleaning pass.

1. Read `data/sales_cleaned.csv` (or `data/sales.csv` if cleaned version doesn't exist)
2. Apply aggressive cleaning:
   - Standardize all text to lowercase and strip whitespace
   - Normalize date formats to YYYY-MM-DD
   - Recalculate `total` column as `quantity × unit_price` (don't trust existing values)
   - Flag and remove any statistical outliers (values > 3 standard deviations from mean)
   - Fill remaining gaps using column median (numeric) or mode (categorical)
3. Save to `data/sales_deep_cleaned.csv`
4. Write a cleaning log to `data/deep_clean_log.txt` listing every change made

Submit your result as JSON:
```json
{
  "status": "deep_cleaned",
  "input_file": "data/sales_cleaned.csv",
  "output_file": "data/sales_deep_cleaned.csv",
  "log_file": "data/deep_clean_log.txt",
  "outliers_removed": 2,
  "totals_recalculated": 46,
  "formats_standardized": 46
}
```
