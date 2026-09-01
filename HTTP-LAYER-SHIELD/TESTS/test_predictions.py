import requests

bot_data = {
    'click_count': 50,
    'avg_click_interval': 20,
    'click_interval_variance': 5,
    'click_interval_entropy': 0.5,
    'mouse_velocity_variance': 0.1,
    'max_element_click_rate': 5.0,
    'scroll_events': 0,
    'keystroke_count': 0
}

human_data = {
    'click_count': 5,
    'avg_click_interval': 1200,
    'click_interval_variance': 200000,
    'click_interval_entropy': 3.0,
    'mouse_velocity_variance': 0.55,
    'max_element_click_rate': 1.0,
    'scroll_events': 10,
    'keystroke_count': 8
}

print("=== Bot Data Predict ===")
res1 = requests.post("http://localhost:8080/predict", json=bot_data)
print(res1.status_code, res1.json())

print("=== Human Data Predict ===")
res2 = requests.post("http://localhost:8080/predict", json=human_data)
print(res2.status_code, res2.json())
