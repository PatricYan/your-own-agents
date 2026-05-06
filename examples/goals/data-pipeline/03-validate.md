You are a data engineer. Validate the ingested sales dataset against business rules.

The previous task created `data/sales.csv`. Your job:

1. Read `data/sales.csv` using Python
2. Run these validation checks:
   - Schema: all 9 expected columns exist
   - Types: dates are valid, quantities are integers, prices are positive numbers
   - Ranges: quantity 1–1000, unit_price 1.00–10000.00
   - Referential: category matches product (e.g., "laptop" → "electronics")
   - Completeness: no critical fields (id, date, product, total) are empty
3. Log each violation found
4. Save a validation report to `data/validation_report.txt`
5. Calculate a data quality score:
   - Start at 1.0
   - Subtract 0.03 for each schema/type violation
   - Subtract 0.05 for each range violation
   - Subtract 0.1 for each referential integrity violation
   - Clamp to [0.0, 1.0]

6. Submit your result as JSON:
```json
{
  "input_file": "data/sales.csv",
  "report_file": "data/validation_report.txt",
  "total_rows": 50,
  "violations_found": 7,
  "violation_types": {"schema": 0, "type": 2, "range": 1, "referential": 1, "completeness": 3},
  "data_quality": 0.62
}
```

The `data_quality` score determines the next step:
- Above 0.8 → generate a quality report
- 0.8 or below → fix the validation errors
