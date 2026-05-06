You are a data engineer. Transform the ingested sales dataset into analytics-ready aggregations.

The previous task created `data/sales.csv`. Your job:

1. Read `data/sales.csv` using Python
2. Compute these aggregations:
   - Total revenue by region
   - Top 5 products by quantity sold
   - Monthly revenue trend (Jan–Jun 2025)
   - Average order value by category
3. Save results to `data/aggregations.json`
4. Verify the numbers add up (total of region revenues = grand total)
5. Calculate a data quality score:
   - Start at 1.0
   - Subtract 0.15 if totals don't reconcile
   - Subtract 0.05 for each aggregation that has null/NaN values
   - Subtract 0.1 if any negative revenue appears
   - Clamp to [0.0, 1.0]

6. Submit your result as JSON:
```json
{
  "input_file": "data/sales.csv",
  "output_file": "data/aggregations.json",
  "total_revenue": 125000.00,
  "regions": 4,
  "months": 6,
  "reconciled": true,
  "data_quality": 0.85
}
```

The `data_quality` score determines the next step:
- Above 0.8 → generate a dashboard
- 0.8 or below → recalculate with corrections
