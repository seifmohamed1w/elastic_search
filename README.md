# Review Search & Sentiment Trend Analyzer (Elasticsearch + FastAPI)

## 1) Project Description (Milestone 1)

This project is a local web API that allows users to **search and analyze customer reviews for products**. Reviews are indexed into **Elasticsearch** for fast full-text retrieval and aggregation-based analytics. The system computes a simple **sentiment label** (positive/negative/neutral) for each review and enables analytics such as **sentiment distribution** and **rating/sentiment trends over time**.

**Why Elasticsearch**
- Full-text search on review text with relevance ranking, typo tolerance, and highlighting
- Structured filtering on fields like product, rating, date, and sentiment
- Aggregations to compute analytics (counts, averages, time-series)

**Architecture**
- Docker: Elasticsearch + Kibana
- Python: FastAPI REST API (Swagger/OpenAPI)
- Dataset: Kaggle reviews CSV → prepared JSON sample (5,000 reviews) → indexed into Elasticsearch

---

## 2) Milestones Coverage Summary

### Milestone 1 — Project description
Covered in this README (Section 1).

### Milestone 2 — List of use cases
Covered in Section 3.

### Milestone 3 — REST API + Swagger
FastAPI provides:
- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Milestone 4 — Elasticsearch Mapping
Index mapping is implemented in `app/main.py` as `INDEX_BODY` and applied via:
- `POST /admin/index/create`

### Milestone 5 — Implementation
Implemented:
- Docker Compose for Elasticsearch + Kibana
- FastAPI API with ingestion, CRUD, search, analytics
- Sentiment computation (VADER)
- Bulk indexing and search/analytics queries in Elasticsearch

### Milestone 6 — Postman Testing
A Postman collection should call endpoints in Section 9 (recommended flow).

---

## 3) Use Cases (Milestone 2)

1. **Keyword search** reviews by text (e.g., "coconut", "taste", "bad packaging").
2. **Typo-tolerant search** using fuzziness (handles misspellings).
3. **Filter** search results by `productId`.
4. **Filter** by rating range (`minRating`, `maxRating`).
5. **Filter** by sentiment (`positive`, `negative`, `neutral`).
6. **Filter** by date range (`dateFrom`, `dateTo`).
7. **Sort** results by relevance/newest/oldest/rating asc/desc.
8. **Paginate** results using `page` + `size`.
9. **Highlight** matched terms in returned results.
10. **Bulk ingest** a dataset of reviews.
11. **CRUD** operations for individual reviews (create, read, update, delete).
12. **Analytics summary**: sentiment distribution and average rating.
13. **Trend analytics**: sentiment and average rating over time (day/week/month).

---

## 4) Requirements

- Windows 11
- WSL2 installed and working
- Docker Desktop installed (CLI works)
- Python 3.10+ (recommended)
- PyCharm (IDE)

---

## 5) Local Setup

### 5.1 Start Elasticsearch + Kibana (Docker)
From the project root:

```bash
cd infra
docker compose up -d
docker ps
```

Expected ports:
- Elasticsearch: `http://localhost:9200`
- Kibana: `http://localhost:5601`

### 5.2 Python environment
Create/activate your venv, then install dependencies:

```bash
pip install fastapi uvicorn[standard] elasticsearch vaderSentiment python-dateutil
```

### 5.3 Run the API
From project root:

```bash
uvicorn app.main:app --reload --port 8000
```

Open Swagger:
- `http://localhost:8000/docs`

---

## 6) Data

### 6.1 Source
Dataset originated from Kaggle `Reviews.csv` (large).  
A prepared sample was created as JSON:

- `data/reviews_sample.json` (5,000 reviews across ~50 products)

### 6.2 Fields indexed
Each indexed document contains:

- `review_id` (string) — unique ID (document `_id`)
- `product_id` (string)
- `product_name` (string)
- `rating` (int 1–5)
- `review_title` (string)
- `review_text` (string)
- `created_at` (ISO datetime)
- `sentiment` (keyword: positive|negative|neutral)
- `sentiment_score` (float)

---

## 7) Endpoint Documentation (How to Call Each Endpoint)

Base URL:
- `http://localhost:8000`

### 7.1 Health

#### `GET /health`
Checks that the API is running and Elasticsearch is reachable.

**Example**
```bash
curl http://localhost:8000/health
```

---

### 7.2 Index Management

#### `POST /admin/index/create`
Creates the Elasticsearch index `reviews_v1` with the mapping.

**Example**
```bash
curl -X POST http://localhost:8000/admin/index/create
```

---

### 7.3 Bulk Ingest

#### `POST /reviews/bulk`
Bulk ingests a list (JSON array) of reviews.

**Behavior**
- Cleans HTML from text fields
- Computes sentiment label + score
- Indexes each review with `_id = review_id`

**Example (load prepared sample)**
```bash
curl -X POST http://localhost:8000/reviews/bulk \
  -H "Content-Type: application/json" \
  --data-binary @data/reviews_sample.json
```

---

### 7.4 CRUD for Reviews

#### `POST /reviews`
Creates a single review.

**Example**
```bash
curl -X POST http://localhost:8000/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "review_id":"demo-1",
    "product_id":"P-DEMO",
    "product_name":"Product P-DEMO",
    "rating":5,
    "review_title":"Great",
    "review_text":"Works perfectly, excellent quality.",
    "created_at":"2025-12-15T10:00:00+00:00"
  }'
```

#### `GET /reviews/{review_id}`
Fetch a review by id.

**Example**
```bash
curl http://localhost:8000/reviews/demo-1
```

#### `PUT /reviews/{review_id}`
Partially updates a review (recomputes sentiment if title/text changes).

**Example**
```bash
curl -X PUT http://localhost:8000/reviews/demo-1 \
  -H "Content-Type: application/json" \
  -d '{
    "rating": 2,
    "review_text": "Stopped working after two days. Disappointed."
  }'
```

#### `DELETE /reviews/{review_id}`
Deletes a review.

**Example**
```bash
curl -X DELETE http://localhost:8000/reviews/demo-1
```

---

### 7.5 Search

#### `GET /search`
Full-text search with filters, sorting, pagination, highlighting.

**Query parameters**
- `q` (optional): keyword query
- `productId` (optional): filter by product id
- `minRating` / `maxRating` (optional): rating range
- `sentiment` (optional): `positive|negative|neutral`
- `dateFrom` / `dateTo` (optional): ISO datetime range
- `sort` (optional): `relevance|newest|oldest|rating_desc|rating_asc`
- `page` (default 1)
- `size` (default 10, max 100)

**Examples**

Keyword search:
```bash
curl "http://localhost:8000/search?q=coconut&size=5"
```

Filter by product + rating + newest:
```bash
curl "http://localhost:8000/search?productId=B003B3OOPA&minRating=4&sort=newest&size=10"
```

Filter by sentiment:
```bash
curl "http://localhost:8000/search?sentiment=negative&q=bad&size=10"
```

Filter by date range:
```bash
curl "http://localhost:8000/search?dateFrom=2011-01-01T00:00:00+00:00&dateTo=2012-01-01T00:00:00+00:00&size=10"
```

**Response**
- `total`: total matching documents
- `items`: each item includes `_score` and `highlights` (snippets)

---

### 7.6 Analytics

#### `GET /analytics/summary`
Returns:
- total reviews considered
- average rating
- sentiment distribution (counts)

Supports the same filters as search (except sentiment itself is not required here).

**Examples**
Overall:
```bash
curl "http://localhost:8000/analytics/summary"
```

Per product:
```bash
curl "http://localhost:8000/analytics/summary?productId=B003B3OOPA"
```

Per query:
```bash
curl "http://localhost:8000/analytics/summary?q=coconut"
```

---

#### `GET /analytics/trends`
Time series analytics using a date histogram.

**Query parameters**
- `interval`: `day|week|month` (default `month`)
- `productId` (optional)
- `q` (optional)
- `minRating`, `maxRating`, `dateFrom`, `dateTo` (optional)

**Examples**
Monthly trend overall:
```bash
curl "http://localhost:8000/analytics/trends?interval=month"
```

Monthly trend per product:
```bash
curl "http://localhost:8000/analytics/trends?productId=B003B3OOPA&interval=month"
```

---

## 8) Elasticsearch Mapping (Milestone 4 details)

Index: `reviews_v1`

Field type choices:
- `review_text`, `review_title`, `product_name`: `text` (full-text search)
- `product_id`, `review_id`, `sentiment`: `keyword` (exact match + aggregations)
- `rating`: `integer` (range filtering + average rating aggregation)
- `created_at`: `date` (date histogram trends)
- `sentiment_score`: `float` (optional scoring)

Text analyzer:
- lowercase + asciifolding (better matching for case/accent variants)

The mapping is created via `POST /admin/index/create`.

---

## 9) Postman Testing Plan (Milestone 6)

Recommended execution order for Postman:

1. `POST /admin/index/create`
2. `GET /health`
3. `POST /reviews/bulk` (load `data/reviews_sample.json`)
4. `GET /search?q=coconut&size=5`
5. `GET /search?productId=B003B3OOPA&minRating=4&sort=newest&size=10`
6. `GET /analytics/summary`
7. `GET /analytics/trends?interval=month`
8. CRUD flow:
   - `POST /reviews`
   - `GET /reviews/{id}`
   - `PUT /reviews/{id}`
   - `DELETE /reviews/{id}`

Add Postman assertions (optional but recommended):
- status code 200
- `total > 0` for known keyword queries
- analytics responses contain non-null values

---

## 10) Run/Stop Commands

Start infrastructure:
```bash
cd infra
docker compose up -d
```

Stop infrastructure:
```bash
cd infra
docker compose down
```

Run API:
```bash
uvicorn app.main:app --reload --port 8000
```

---

## 11) Troubleshooting

### Elasticsearch/Kibana not accessible
Check containers:
```bash
docker ps
docker logs es01 --tail 200
docker logs kb01 --tail 200
```

### Memory issues
If Elasticsearch fails to start, reduce heap in `docker-compose.yml`:
- `ES_JAVA_OPTS=-Xms768m -Xmx768m`
Then restart:
```bash
docker compose down
docker compose up -d
```

---

## 12) What was built, in one sentence
A FastAPI + Elasticsearch system that indexes product reviews, enriches them with sentiment, supports advanced search, and provides sentiment/rating analytics and trends over time.
