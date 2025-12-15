import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "Reviews.csv"
OUT_PATH = PROJECT_ROOT / "data" / "reviews_sample.json"

TOP_PRODUCTS = 50
MAX_REVIEWS_PER_PRODUCT = 100

def to_iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()

def main():
    # Read only needed columns (faster, less RAM)
    usecols = ["Id", "ProductId", "Score", "Time", "Summary", "Text"]
    df = pd.read_csv(CSV_PATH, usecols=usecols)

    # Pick top products by review count
    top_product_ids = df["ProductId"].value_counts().head(TOP_PRODUCTS).index.tolist()

    # Filter to those products
    df = df[df["ProductId"].isin(top_product_ids)].copy()

    # Sample per product to control size
    df = (
        df.groupby("ProductId", group_keys=False)
          .apply(lambda g: g.sample(n=min(len(g), MAX_REVIEWS_PER_PRODUCT), random_state=42))
    )

    # Clean nulls
    df["Summary"] = df["Summary"].fillna("")
    df["Text"] = df["Text"].fillna("")

    # Convert to your API schema
    records = []
    for row in df.itertuples(index=False):
        records.append({
            "review_id": str(row.Id),
            "product_id": str(row.ProductId),
            "product_name": f"Product {row.ProductId}",  # placeholder
            "rating": int(row.Score),
            "review_title": row.Summary,
            "review_text": row.Text,
            "created_at": to_iso(row.Time)
        })

    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} reviews to: {OUT_PATH}")

if __name__ == "__main__":
    main()
