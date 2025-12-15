# app/main.py
from __future__ import annotations

import os
import re
import html as ihtml
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from elasticsearch import Elasticsearch, helpers
from elasticsearch import NotFoundError, BadRequestError
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


# -----------------------------
# Config
# -----------------------------
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
INDEX_NAME = os.getenv("ES_INDEX", "reviews_v1")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 10

TAG_RE = re.compile(r"<[^>]+>")
sent_analyzer = SentimentIntensityAnalyzer()


def get_es() -> Elasticsearch:
    return Elasticsearch(ES_URL)


def clean_text(s: str) -> str:
    s = s or ""
    s = ihtml.unescape(s)
    s = TAG_RE.sub(" ", s)
    return " ".join(s.split()).strip()


def compute_sentiment(text: str) -> tuple[str, float]:
    score = sent_analyzer.polarity_scores(text)["compound"]
    if score >= 0.05:
        return "positive", float(score)
    if score <= -0.05:
        return "negative", float(score)
    return "neutral", float(score)


# -----------------------------
# Pydantic models (single-file)
# -----------------------------
class ReviewIn(BaseModel):
    review_id: str
    product_id: str
    product_name: str
    rating: int = Field(ge=1, le=5)
    review_title: Optional[str] = ""
    review_text: str
    created_at: datetime


class ReviewUpdate(BaseModel):
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    review_title: Optional[str] = None
    review_text: Optional[str] = None
    created_at: Optional[datetime] = None


class ReviewOut(BaseModel):
    review_id: str
    product_id: str
    product_name: str
    rating: int
    review_title: str
    review_text: str
    created_at: datetime
    sentiment: str
    sentiment_score: float


# -----------------------------
# Index mapping (Milestone 4)
# -----------------------------
INDEX_BODY: Dict[str, Any] = {
    "settings": {
        "analysis": {
            "analyzer": {
                "folding": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "review_id": {"type": "keyword"},
            "product_id": {"type": "keyword"},
            "product_name": {
                "type": "text",
                "analyzer": "folding",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "rating": {"type": "integer"},
            "review_title": {"type": "text", "analyzer": "folding"},
            "review_text": {"type": "text", "analyzer": "folding"},
            "created_at": {"type": "date"},
            "sentiment": {"type": "keyword"},
            "sentiment_score": {"type": "float"},
        }
    },
}


# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(
    title="Review Search & Sentiment Trend Analyzer",
    version="1.0.0",
    description="Elasticsearch-backed API for indexing, searching, and analyzing product reviews.",
)


# -----------------------------
# Helpers for ES queries
# -----------------------------
SortType = Literal["relevance", "newest", "oldest", "rating_desc", "rating_asc"]


def build_filters(
    product_id: Optional[str],
    sentiment: Optional[str],
    min_rating: Optional[int],
    max_rating: Optional[int],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> List[Dict[str, Any]]:
    filters: List[Dict[str, Any]] = []

    if product_id:
        filters.append({"term": {"product_id": product_id}})

    if sentiment:
        filters.append({"term": {"sentiment": sentiment}})

    if min_rating is not None or max_rating is not None:
        rng: Dict[str, Any] = {}
        if min_rating is not None:
            rng["gte"] = min_rating
        if max_rating is not None:
            rng["lte"] = max_rating
        filters.append({"range": {"rating": rng}})

    if date_from is not None or date_to is not None:
        rng: Dict[str, Any] = {}
        if date_from is not None:
            rng["gte"] = date_from.isoformat()
        if date_to is not None:
            rng["lte"] = date_to.isoformat()
        filters.append({"range": {"created_at": rng}})

    return filters


def build_query(q: Optional[str], filters: List[Dict[str, Any]]) -> Dict[str, Any]:
    if q and q.strip():
        return {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q,
                            "fields": ["review_title^2", "review_text", "product_name^1.5"],
                            "fuzziness": "AUTO",
                            "operator": "and",
                        }
                    }
                ],
                "filter": filters,
            }
        }
    return {"bool": {"must": [{"match_all": {}}], "filter": filters}}


def build_sort(sort: SortType) -> Optional[List[Dict[str, Any]]]:
    if sort == "newest":
        return [{"created_at": {"order": "desc"}}, {"_score": {"order": "desc"}}]
    if sort == "oldest":
        return [{"created_at": {"order": "asc"}}, {"_score": {"order": "desc"}}]
    if sort == "rating_desc":
        return [{"rating": {"order": "desc"}}, {"_score": {"order": "desc"}}]
    if sort == "rating_asc":
        return [{"rating": {"order": "asc"}}, {"_score": {"order": "desc"}}]
    # relevance
    return None


def ensure_index_exists(es: Elasticsearch) -> None:
    if not es.indices.exists(index=INDEX_NAME):
        raise HTTPException(
            status_code=400,
            detail=f"Index '{INDEX_NAME}' does not exist. Call POST /admin/index/create first.",
        )


# -----------------------------
# Endpoints
# -----------------------------
@app.get("/health")
def health():
    es = get_es()
    try:
        info = es.info()
        return {
            "status": "ok",
            "es_url": ES_URL,
            "index": INDEX_NAME,
            "elasticsearch_version": info.get("version", {}).get("number"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/index/create")
def create_index():
    es = get_es()
    try:
        if es.indices.exists(index=INDEX_NAME):
            return {"created": False, "index": INDEX_NAME, "message": "already exists"}
        es.indices.create(index=INDEX_NAME, body=INDEX_BODY)
        return {"created": True, "index": INDEX_NAME}
    except BadRequestError as e:
        raise HTTPException(status_code=400, detail=e.info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reviews/bulk")
def bulk_ingest(reviews: List[ReviewIn]):
    es = get_es()
    ensure_index_exists(es)

    def actions():
        for r in reviews:
            title = clean_text(r.review_title or "")
            text = clean_text(r.review_text or "")
            label, score = compute_sentiment(f"{title} {text}".strip())
            doc = {
                "review_id": r.review_id,
                "product_id": r.product_id,
                "product_name": r.product_name,
                "rating": r.rating,
                "review_title": title,
                "review_text": text,
                "created_at": r.created_at.isoformat(),
                "sentiment": label,
                "sentiment_score": score,
            }
            yield {"_index": INDEX_NAME, "_id": r.review_id, "_source": doc}

    try:
        helpers.bulk(es, actions(), chunk_size=500, request_timeout=120)
        es.indices.refresh(index=INDEX_NAME)
        return {"ingested": len(reviews), "index": INDEX_NAME}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reviews", response_model=ReviewOut)
def create_review(review: ReviewIn):
    es = get_es()
    ensure_index_exists(es)

    title = clean_text(review.review_title or "")
    text = clean_text(review.review_text or "")
    label, score = compute_sentiment(f"{title} {text}".strip())

    doc = {
        "review_id": review.review_id,
        "product_id": review.product_id,
        "product_name": review.product_name,
        "rating": review.rating,
        "review_title": title,
        "review_text": text,
        "created_at": review.created_at.isoformat(),
        "sentiment": label,
        "sentiment_score": score,
    }

    try:
        es.index(index=INDEX_NAME, id=review.review_id, document=doc, refresh=True)
        return ReviewOut(**{**doc, "created_at": review.created_at})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reviews/{review_id}", response_model=ReviewOut)
def get_review(review_id: str):
    es = get_es()
    ensure_index_exists(es)

    try:
        res = es.get(index=INDEX_NAME, id=review_id)
        src = res["_source"]
        return ReviewOut(
            **{
                **src,
                "created_at": datetime.fromisoformat(src["created_at"].replace("Z", "+00:00")),
            }
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Review not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/reviews/{review_id}", response_model=ReviewOut)
def update_review(review_id: str, patch: ReviewUpdate):
    es = get_es()
    ensure_index_exists(es)

    try:
        existing = es.get(index=INDEX_NAME, id=review_id)["_source"]
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Review not found")

    updated = dict(existing)

    # Apply patch fields if provided
    if patch.product_id is not None:
        updated["product_id"] = patch.product_id
    if patch.product_name is not None:
        updated["product_name"] = patch.product_name
    if patch.rating is not None:
        updated["rating"] = patch.rating
    if patch.review_title is not None:
        updated["review_title"] = clean_text(patch.review_title)
    if patch.review_text is not None:
        updated["review_text"] = clean_text(patch.review_text)
    if patch.created_at is not None:
        updated["created_at"] = patch.created_at.isoformat()

    # Recompute sentiment if title/text changed
    title = updated.get("review_title", "")
    text = updated.get("review_text", "")
    label, score = compute_sentiment(f"{title} {text}".strip())
    updated["sentiment"] = label
    updated["sentiment_score"] = score
    updated["review_id"] = review_id

    try:
        es.index(index=INDEX_NAME, id=review_id, document=updated, refresh=True)
        return ReviewOut(
            **{
                **updated,
                "created_at": datetime.fromisoformat(updated["created_at"].replace("Z", "+00:00")),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/reviews/{review_id}")
def delete_review(review_id: str):
    es = get_es()
    ensure_index_exists(es)

    try:
        es.delete(index=INDEX_NAME, id=review_id, refresh=True)
        return {"deleted": True, "review_id": review_id}
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Review not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search")
def search_reviews(
    q: Optional[str] = None,
    productId: Optional[str] = None,
    minRating: Optional[int] = Query(default=None, ge=1, le=5),
    maxRating: Optional[int] = Query(default=None, ge=1, le=5),
    sentiment: Optional[str] = Query(default=None, pattern="^(positive|negative|neutral)$"),
    dateFrom: Optional[datetime] = None,
    dateTo: Optional[datetime] = None,
    sort: SortType = "relevance",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    es = get_es()
    ensure_index_exists(es)

    filters = build_filters(productId, sentiment, minRating, maxRating, dateFrom, dateTo)
    query = build_query(q, filters)
    sort_body = build_sort(sort)

    body: Dict[str, Any] = {
        "query": query,
        "from": (page - 1) * size,
        "size": size,
        "highlight": {
            "fields": {
                "review_text": {"fragment_size": 160, "number_of_fragments": 3},
                "review_title": {"fragment_size": 120, "number_of_fragments": 2},
            }
        },
    }
    if sort_body:
        body["sort"] = sort_body

    try:
        res = es.search(index=INDEX_NAME, body=body)
        hits = res["hits"]["hits"]
        total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]

        items = []
        for h in hits:
            src = h["_source"]
            items.append(
                {
                    **src,
                    "_score": h.get("_score"),
                    "highlights": h.get("highlight", {}),
                }
            )

        return {
            "page": page,
            "size": size,
            "total": total,
            "items": items,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/summary")
def analytics_summary(
    q: Optional[str] = None,
    productId: Optional[str] = None,
    minRating: Optional[int] = Query(default=None, ge=1, le=5),
    maxRating: Optional[int] = Query(default=None, ge=1, le=5),
    dateFrom: Optional[datetime] = None,
    dateTo: Optional[datetime] = None,
):
    es = get_es()
    ensure_index_exists(es)

    filters = build_filters(productId, None, minRating, maxRating, dateFrom, dateTo)
    query = build_query(q, filters)

    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "avg_rating": {"avg": {"field": "rating"}},
            "sentiments": {"terms": {"field": "sentiment", "size": 10}},
        },
    }

    try:
        res = es.search(index=INDEX_NAME, body=body)
        total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]
        avg_rating = res["aggregations"]["avg_rating"]["value"]
        buckets = res["aggregations"]["sentiments"]["buckets"]

        return {
            "total_reviews": total,
            "avg_rating": avg_rating,
            "sentiment_counts": {b["key"]: b["doc_count"] for b in buckets},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/trends")
def analytics_trends(
    q: Optional[str] = None,
    productId: Optional[str] = None,
    interval: Literal["day", "week", "month"] = "month",
    minRating: Optional[int] = Query(default=None, ge=1, le=5),
    maxRating: Optional[int] = Query(default=None, ge=1, le=5),
    dateFrom: Optional[datetime] = None,
    dateTo: Optional[datetime] = None,
):
    es = get_es()
    ensure_index_exists(es)

    filters = build_filters(productId, None, minRating, maxRating, dateFrom, dateTo)
    query = build_query(q, filters)

    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "trend": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": interval,
                    "min_doc_count": 0,
                },
                "aggs": {
                    "avg_rating": {"avg": {"field": "rating"}},
                    "sentiments": {"terms": {"field": "sentiment", "size": 10}},
                },
            }
        },
    }

    try:
        res = es.search(index=INDEX_NAME, body=body)
        buckets = res["aggregations"]["trend"]["buckets"]

        out = []
        for b in buckets:
            sent_counts = {sb["key"]: sb["doc_count"] for sb in b["sentiments"]["buckets"]}
            out.append(
                {
                    "date": b.get("key_as_string"),
                    "doc_count": b["doc_count"],
                    "avg_rating": b["avg_rating"]["value"],
                    "sentiment_counts": sent_counts,
                }
            )

        return {"interval": interval, "items": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
