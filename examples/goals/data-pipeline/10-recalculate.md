You are a data engineer. The aggregations had quality issues. Recalculate from scratch.

1. Read `data/sales.csv` (the raw data)
2. First clean the data in-memory:
   - Remove duplicates
   - Fix invalid values (negative quantities → absolute value)
   - Fill missing prices with category average
3. Then recompute all aggregations:
   - Total revenue by region
   - Top 5 products by quantity
   - Monthly trend
   - Average order value by category
4. Verify: region totals must sum to grand total (within $0.01 tolerance)
5. Save corrected results to `data/aggregations_corrected.json`
6. Save reconciliation proof to `data/reconciliation.txt`

Submit your result as JSON:
```json
{
  "status": "recalculated",
  "output_file": "data/aggregations_corrected.json",
  "reconciliation_file": "data/reconciliation.txt",
  "total_revenue": 124850.00,
  "reconciled": true,
  "corrections_applied": 5
}
```
