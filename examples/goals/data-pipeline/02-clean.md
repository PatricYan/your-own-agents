You are a data engineer. Clean the ingested sales dataset.

The previous task created `data/sales.csv` with intentional issues. Your job:

1. Read `data/sales.csv` using Python (pandas or csv module)
2. Remove duplicate rows
3. Handle missing values — fill numeric fields with 0, text fields with "unknown"
4. Remove or fix rows with invalid values (e.g., negative quantities → set to 0)
5. Save the cleaned data to `data/sales_cleaned.csv`
6. Calculate a data quality score:
   - Start at 1.0
   - Subtract 0.05 for each duplicate found
   - Subtract 0.08 for each missing value found
   - Subtract 0.1 for each invalid value found
   - Clamp to [0.0, 1.0]

7. Submit your result as JSON:
```json
{
  "input_file": "data/sales.csv",
  "output_file": "data/sales_cleaned.csv",
  "rows_before": 50,
  "rows_after": 46,
  "duplicates_removed": 4,
  "missing_filled": 3,
  "invalid_fixed": 1,
  "data_quality": 0.56
}
```

The `data_quality` score determines the next step:
- Above 0.8 → data is clean enough to export directly
- 0.8 or below → data needs a deeper cleaning pass
