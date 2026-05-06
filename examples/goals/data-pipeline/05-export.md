You are a data engineer. The cleaned dataset passed quality checks. Export it.

1. Read `data/sales_cleaned.csv`
2. Export to three formats:
   - `data/export/sales.json` (JSON array of records)
   - `data/export/sales_summary.txt` (human-readable summary with row counts and totals)
   - `data/export/sales.csv` (final copy with a metadata header comment)
3. Create an export manifest at `data/export/manifest.json` listing all exported files with sizes

Submit your result as JSON:
```json
{
  "status": "exported",
  "files": ["data/export/sales.json", "data/export/sales_summary.txt", "data/export/sales.csv"],
  "manifest": "data/export/manifest.json"
}
```
