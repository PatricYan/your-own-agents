You are a data analyst. The aggregations passed quality checks. Generate a dashboard.

1. Read `data/aggregations.json`
2. Create a text-based dashboard at `data/dashboard.md` with:
   - Revenue by region (bar chart using ASCII characters)
   - Monthly trend (line representation using ASCII)
   - Top 5 products table
   - Key metrics: total revenue, avg order value, total orders
3. Also create `data/dashboard_data.json` with all chart data structured for frontend rendering

Submit your result as JSON:
```json
{
  "status": "dashboard_created",
  "dashboard_file": "data/dashboard.md",
  "data_file": "data/dashboard_data.json",
  "metrics": {"total_revenue": 125000, "total_orders": 46, "avg_order_value": 2717}
}
```
