"""
AetherCept — DDoS Bot Detection API
====================================
Run locally:   python aethercept_api.py
Run on Colab:  already running via ngrok (paste URL into dashboard)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import pickle, numpy as np

app = Flask(__name__)
CORS(app)   # allow browser dashboard to call this

# ── Load model & scaler ───────────────────────────────────────────────────
with open('aethercept_model.pkl', 'rb') as f:
    model = pickle.load(f)

with open('aethercept_scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

FEATURES = [
    'click_count',
    'avg_click_interval',
    'click_interval_variance',
    'click_interval_entropy',
    'mouse_velocity_variance',
    'max_element_click_rate',
    'scroll_events',
    'keystroke_count'
]

# ── Routes ────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return jsonify({'status': 'AetherCept API running', 'model': 'IsolationForest', 'features': FEATURES})

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json
    try:
        features = [[data[f] for f in FEATURES]]
        scaled   = scaler.transform(features)
        pred     = model.predict(scaled)[0]          # -1 = bot, 1 = human
        score    = model.decision_function(scaled)[0] # negative = more anomalous
        return jsonify({
            'prediction':    'bot' if pred == -1 else 'human',
            'anomaly_score': round(float(score), 4),
            'raw_pred':      int(pred)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/health')
def health():
    return jsonify({'ok': True})

if __name__ == '__main__':
    print("\n  AetherCept API → http://localhost:5000\n")
    app.run(debug=False, port=5000)
