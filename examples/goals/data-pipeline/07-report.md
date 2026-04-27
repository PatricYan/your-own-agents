You are a data analyst. The dataset passed validation. Generate a quality report.

1. Read `data/validation_report.txt` for the validation results
2. Read `data/sales.csv` for the source data
3. Generate a comprehensive data quality report at `data/quality_report.md` including:
   - Executive summary (1 paragraph)
   - Data profile: row count, column types, null percentages
   - Validation results: checks passed vs failed
   - Distribution summaries for numeric columns
   - Recommendations for data governance
4. Include a quality scorecard table

Submit your result as JSON:
```json
{
  "status": "reported",
  "report_file": "data/quality_report.md",
  "checks_passed": 43,
  "checks_failed": 7,
  "overall_grade": "B+"
}
```
