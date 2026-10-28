# Prediction API Specification (Gate 9)

Local HTTP prediction service built on **BentoML 1.4.40**, serving the baseline purchase-conversion model.

---

## 1. Service Overview

- **Service Class:** `services.prediction.service:ConversionService`
- **Model Artifact:** `models/baseline_logreg.joblib` (Git-ignored)
- **Model Version:** `baseline-logreg-v1`
- **Default Port:** `3000`
- **Binding Address:** `127.0.0.1` (localhost only; non-production POC)
- **Input Feature Schema:** Matches `models/feature_schema.json` (13 features: 8 categoricals, 5 numerics)

---

## 2. Endpoints

### 2.1. Health Check

- **Route:** `POST /health` (or `GET /healthz` built-in)
- **Description:** Returns service status, active model version, and loaded artifact path.

#### Example Response (200 OK)
```json
{
  "status": "ok",
  "model_version": "baseline-logreg-v1",
  "model_path": "D:\\MLOps\\models\\baseline_logreg.joblib"
}
```

---

### 2.2. Predict Conversion

- **Route:** `POST /predict`
- **Content-Type:** `application/json`
- **Description:** Evaluates session-level features and returns conversion probability and classification.

#### Request JSON Schema
```json
{
  "type": "object",
  "required": [
    "channelGrouping", "device_category", "browser", "operating_system",
    "country", "continent", "traffic_source", "traffic_medium",
    "visitNumber", "visits", "hits", "pageviews", "time_on_site"
  ],
  "properties": {
    "channelGrouping": {"type": "string", "minLength": 1, "example": "Organic Search"},
    "device_category": {"type": "string", "minLength": 1, "example": "desktop"},
    "browser": {"type": "string", "minLength": 1, "example": "Chrome"},
    "operating_system": {"type": "string", "minLength": 1, "example": "Windows"},
    "country": {"type": "string", "minLength": 1, "example": "United States"},
    "continent": {"type": "string", "minLength": 1, "example": "Americas"},
    "traffic_source": {"type": "string", "minLength": 1, "example": "google"},
    "traffic_medium": {"type": "string", "minLength": 1, "example": "organic"},
    "visitNumber": {"type": "integer", "minimum": 1, "example": 1},
    "visits": {"type": "integer", "minimum": 0, "example": 1},
    "hits": {"type": "integer", "minimum": 0, "example": 10},
    "pageviews": {"type": "integer", "minimum": 0, "example": 8},
    "time_on_site": {"type": "integer", "minimum": 0, "example": 150}
  }
}
```

#### Response JSON Schema (200 OK)
```json
{
  "prediction": 0,
  "conversion_probability": 0.0215,
  "model_version": "baseline-logreg-v1",
  "request_id": "d8049e62-8bd0-4a8c-b62f-fe387d315433"
}
```

#### Status Codes
- `200 OK`: Successful inference.
- `422 Unprocessable Entity`: Input validation failure (missing fields, empty string, invalid numeric bounds like `hits < 0` or `visitNumber < 1`).
- `500 Internal Server Error`: Server-side runtime error or missing model artifact.

---

## 3. How to Run Locally

### 3.1. In-Process Python Client
```powershell
.\.venv\Scripts\python.exe services/prediction/client.py
```

### 3.2. Start BentoML HTTP Server
```powershell
.\.venv\Scripts\bentoml.exe serve services.prediction.service:ConversionService --host 127.0.0.1 --port 3000
```

### 3.3. Test via cURL
```bash
curl -X POST http://127.0.0.1:3000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "channelGrouping": "Organic Search",
    "device_category": "desktop",
    "browser": "Chrome",
    "operating_system": "Windows",
    "country": "United States",
    "continent": "Americas",
    "traffic_source": "google",
    "traffic_medium": "organic",
    "visitNumber": 1,
    "visits": 1,
    "hits": 10,
    "pageviews": 8,
    "time_on_site": 150
  }'
```

---

## 4. Security and Privacy
- Endpoints bind exclusively to localhost (`127.0.0.1`).
- Logs record `request_id`, predicted class, conversion probability, and latency in milliseconds.
- Raw payload features and visitor identifiers are **never logged** to prevent sensitive data leakage.
