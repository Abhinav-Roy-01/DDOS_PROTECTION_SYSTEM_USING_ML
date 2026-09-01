# Game CAPTCHA Module — Redis Setup

## Prerequisites
Redis must be running on `localhost:6379`.

### Option A: Docker (recommended)
```bash
docker run -d --name redis-captcha -p 6379:6379 redis:latest
```

### Option B: WSL
```bash
sudo apt install redis-server
sudo service redis-server start
```

### Option C: Windows native
Download from https://github.com/microsoftarchive/redis/releases

---

## Redis Key Structure

```
captcha:session:{game_id}    →  JSON{secret, ip, created_at, attempts}     TTL: 300s  (5 min)
captcha:verified:{ip}        →  JSON{token, verified_at, expires, game_id} TTL: 3600s (1 hour)
captcha:blocked:{ip}         →  JSON{reason, flagged_at, ip}               TTL: 86400s (24 hrs)
captcha:attempts:{ip}        →  integer counter                            TTL: 900s  (15 min)
```

## Verify Redis is working

```bash
redis-cli ping
# Should return: PONG

redis-cli KEYS "captcha:*"
# Should return: (empty array) initially
```

## Monitor keys in real-time

```bash
redis-cli MONITOR
```

## Clear all CAPTCHA keys (development only)

```bash
redis-cli KEYS "captcha:*" | xargs redis-cli DEL
```

---

## Running the Module

```bash
cd CAPTCHA
pip install -r requirements.txt
python captcha_routes.py
```

Then visit:
- `http://127.0.0.1:5000/captcha/new_game` — generates a game session
- Copy the `redirect_url` from the JSON response and visit it
- Play the game, score ≥ 150 to pass verification
