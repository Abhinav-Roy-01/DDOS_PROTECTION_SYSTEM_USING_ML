from flask import Flask, request, jsonify
import pickle
import numpy as np

app = Flask(__name__)

with open('aethercept_model.pkl', 'rb') as f:
    model = pickle.load(f)

with open('aethercept_scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

FEATURES = [
    'click_count', 'avg_click_interval', 'click_interval_variance',
    'click_interval_entropy', 'mouse_velocity_variance',
    'max_element_click_rate', 'scroll_events', 'keystroke_count'
]

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json
    features = [[data[f] for f in FEATURES]]
    scaled = scaler.transform(features)
    pred = model.predict(scaled)[0]
    score = model.decision_function(scaled)[0]
    return jsonify({
        'prediction': 'bot' if pred == -1 else 'human',
        'anomaly_score': round(float(score), 4)
    })

@app.route('/')
def home():
    return jsonify({'status': 'AetherCept API running ✅'})

if __name__ == '__main__':
    app.run(debug=True)