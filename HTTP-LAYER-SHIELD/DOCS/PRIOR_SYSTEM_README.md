# AetherCept — DDoS Protection Dashboard

ML-powered DDoS / bot detection system using Isolation Forest.

## Project Structure

```
aethercept/
├── app.py                    # Flask backend (API + serves dashboard)
├── requirements.txt
├── aethercept_model.pkl      # ← place your model here
├── aethercept_scaler.pkl     # ← place your scaler here
├── templates/
│   └── index.html            # Jinja2 dashboard template
└── static/
    ├── css/
    │   └── dashboard.css
    └── js/
        └── dashboard.js
```

## Setup

### 1. Place model files
Copy `aethercept_model.pkl` and `aethercept_scaler.pkl` into the project root.

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run locally
```bash
python app.py
```
Open http://localhost:5000

### 4. Production (gunicorn)
```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

## API Endpoints

| Method | Path       | Description                    |
|--------|------------|--------------------------------|
| GET    | `/`        | Dashboard UI                   |
| POST   | `/predict` | Classify a session (JSON body) |
| GET    | `/health`  | Health check                   |

### `/predict` Request Body
```json
{
  "click_count": 5,
  "avg_click_interval": 1200,
  "click_interval_variance": 200000,
  "click_interval_entropy": 3.0,
  "mouse_velocity_variance": 0.55,
  "max_element_click_rate": 1.0,
  "scroll_events": 10,
  "keystroke_count": 8
}
```

### `/predict` Response
```json
{
  "prediction": "human",
  "anomaly_score": 0.1471
}
```

`prediction` is either `"human"` or `"bot"`.  
`anomaly_score` < 0 → bot (negative = anomalous in Isolation Forest).

## Notes
- The dashboard runs in **demo mode** automatically if the backend is unreachable (useful for presentations).
- The live feed and charts use simulated data; wire up real telemetry via the `/predict` endpoint for production.
