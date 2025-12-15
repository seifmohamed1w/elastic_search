import json
import re
import html as ihtml
from pathlib import Path
from datetime import datetime
from elasticsearch import Elasticsearch, helpers
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

INDEX = "reviews_v1"
ES_URL = "http://localhost:9200"

TAG_RE = re.compile(r"<[^>]+>")
analyzer = SentimentIntensityAnalyzer()

def clean_text(s: str) -> str:
    s = s or ""
    s = ihtml.unescape(s)
    s = TAG_RE.sub(" ", s)
    return " ".join(s.split()).strip()

def sentiment_label(text: str) -> tuple[str, float]:
    score = analyzer.polarity_scores(text)["compound"]
    if score >= 0.05:
        return "positive", float(score)
    if score <= -0.05:
        return "negative", float(score)
    return "neutral", float(score)

def main():
    project_root = Path(__file__).resolve().parents[1]
    data_path = project_root / "data" / "reviews_sample.json"

    es = Elasticsearch(ES_URL)

    # Minimal mapping (you can expand this later)
    if not es.indices.exists(index=INDEX):
        es.indices.create(
            index=INDEX,
            body={
                "mappings": {
                    "properties": {
                        "review_id": {"type": "keyword"},
                        "product_id": {"type": "keyword"},
                        "product_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "rating": {"type": "integer"},
                        "review_title": {"type": "text"},
                        "review_text": {"type": "text"},
                        "created_at": {"type": "date"},
                        "sentiment": {"type": "keyword"},
                        "sentiment_score": {"type": "float"},
                    }
                }
            },
        )

    reviews = json.loads(data_path.read_text(encoding="utf-8"))

    def actions():
        for r in reviews:
            title = clean_text(r.get("review_title", ""))
            text = clean_text(r.get("review_text", ""))
            label, score = sentiment_label(f"{title} {text}".strip())
            doc = {
                **r,
                "review_title": title,
                "review_text": text,
                "sentiment": label,
                "sentiment_score": score,
            }
            yield {"_index": INDEX, "_id": r["review_id"], "_source": doc}

    helpers.bulk(es, actions(), chunk_size=500, request_timeout=120)
    es.indices.refresh(index=INDEX)
    print("Loaded reviews into", INDEX)

if __name__ == "__main__":
    main()
