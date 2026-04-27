You are a data engineer. The dataset failed validation. Fix the errors.

1. Read `data/validation_report.txt` to understand what went wrong
2. Read `data/sales.csv`
3. Fix each violation:
   - Type errors: cast to correct types, use defaults for unparseable values
   - Range violations: clamp values to valid ranges (quantity 1–1000, price 1–10000)
   - Referential errors: correct category-product mismatches using a lookup table
   - Completeness: fill missing critical fields using best-effort inference from other columns
4. Save fixed data to `data/sales_fixed.csv`
5. Re-run validation to confirm fixes, save to `data/validation_fixed_report.txt`

Submit your result as JSON:
```json
{
  "status": "fixed",
  "input_file": "data/sales.csv",
  "output_file": "data/sales_fixed.csv",
  "errors_fixed": 7,
  "errors_remaining": 0,
  "revalidation_report": "data/validation_fixed_report.txt"
}
```
