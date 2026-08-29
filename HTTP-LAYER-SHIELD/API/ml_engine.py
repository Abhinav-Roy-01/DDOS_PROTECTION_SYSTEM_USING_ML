import pickle
import numpy as np
import os

FEATURES = [
    'click_count', 'avg_click_interval', 'click_interval_variance',
    'click_interval_entropy', 'mouse_velocity_variance',
    'max_element_click_rate', 'scroll_events', 'keystroke_count'
]

class MLEngine:
    def __init__(self, model_path='aethercept_model.pkl', scaler_path='aethercept_scaler.pkl'):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, model_path), 'rb') as f:
            self.model = pickle.load(f)
        with open(os.path.join(base_dir, scaler_path), 'rb') as f:
            self.scaler = pickle.load(f)
            
    def predict(self, features_dict):
        features = [[features_dict.get(f, 0) for f in FEATURES]]
        scaled = self.scaler.transform(features)
        pred = self.model.predict(scaled)[0]
        score = self.model.decision_function(scaled)[0]
        return {
            'prediction': 'bot' if pred == -1 else 'human',
            'anomaly_score': round(float(score), 4),
            'raw_pred': pred
        }

    def get_features_list(self):
        return FEATURES

# Global instance for easy import
engine = MLEngine()

def predict(features_dict):
    return engine.predict(features_dict)

def get_features_list():
    return engine.get_features_list()
