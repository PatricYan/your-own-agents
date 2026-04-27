You are a data engineer. Your job is to create and ingest a sample sales dataset.

1. Create a CSV file at `data/sales.csv` with 50 rows of realistic sales data:
   - Columns: `id, date, product, category, quantity, unit_price, total, region, salesperson`
   - Include some intentional data issues: 3-4 duplicate rows, 2-3 rows with missing values (empty cells), 1 row with a negative quantity
   - Dates should span Jan–Jun 2025
   - Products: laptop, mouse, keyboard, monitor, headset
   - Categories: electronics, peripherals, accessories
   - Regions: north, south, east, west

2. Read back the file and count the rows, columns, and file size

3. Submit your result as JSON:
```json
{
  "file": "data/sales.csv",
  "rows": 50,
  "columns": 9,
  "size_bytes": 2400,
  "issues_planted": {"duplicates": 4, "missing_values": 3, "invalid_values": 1}
}
```
