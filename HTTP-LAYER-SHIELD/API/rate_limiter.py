import time
from collections import deque, Counter
import threading
from datetime import datetime

# Optional Supabase import/usage here if needed
import os

RATE_LIMIT      = 30        # max requests per IP per RATE_WINDOW seconds
RATE_WINDOW     = 10        # seconds
BAN_THRESHOLD   = 60        # requests before auto-ban
BAN_DURATION    = 300       # seconds to keep IP banned
MAX_LOG         = 2000      # max in-memory log entries

lock        = threading.Lock()
REQUEST_LOG = deque(maxlen=MAX_LOG)
CLICK_LOG   = deque(maxlen=5000)
ip_windows  = {}           # ip -> deque of timestamps
banned_ips  = {}           # ip -> ban_until (epoch float)
START_TIME  = time.time()

def is_banned(ip):
    with lock:
        if ip in banned_ips:
            if time.time() < banned_ips[ip]:
                return True
            else:
                del banned_ips[ip]
    return False

def check_rate_limit(ip):
    now = time.time()
    with lock:
        if ip not in ip_windows:
            ip_windows[ip] = deque()
        win = ip_windows[ip]
        while win and win[0] < now - RATE_WINDOW:
            win.popleft()
        win.append(now)
        count = len(win)
        if count >= BAN_THRESHOLD:
            banned_ips[ip] = now + BAN_DURATION
            return False
        return count <= RATE_LIMIT

def record_request(ip, path, method, blocked=False, ml_verdict=None, ml_score=None):
    entry = {
        "time":    datetime.now().isoformat(timespec="seconds"),
        "ip":      ip,
        "path":    path,
        "method":  method,
        "blocked": blocked,
        "ml_verdict": ml_verdict,
        "ml_score": ml_score
    }
    with lock:
        REQUEST_LOG.append(entry)

def record_click(data):
    entry = {"time": datetime.now().isoformat(timespec="milliseconds"), **data}
    with lock:
        CLICK_LOG.append(entry)

def get_stats():
    with lock:
        logs   = list(REQUEST_LOG)
        clicks = list(CLICK_LOG)
        bans   = dict(banned_ips)

    total   = len(logs)
    blocked = sum(1 for r in logs if r.get("blocked"))
    uptime  = int(time.time() - START_TIME)

    ip_counts        = Counter(r["ip"]   for r in logs)
    path_counts      = Counter(r["path"] for r in logs)
    blocked_ip_counts = Counter(r["ip"]  for r in logs if r.get("blocked"))

    now    = datetime.now()
    recent = [r for r in logs if (now - datetime.fromisoformat(r["time"])).total_seconds() < 60]
    rps = round(len(recent) / 60, 2)

    return {
        "total_requests":    total,
        "allowed_requests":  total - blocked,
        "blocked_requests":  blocked,
        "unique_ips":        len(ip_counts),
        "banned_ips":        len(bans),
        "uptime_sec":        uptime,
        "req_per_sec":       rps,
        "top_ips":           dict(ip_counts.most_common(10)),
        "top_paths":         dict(path_counts.most_common(10)),
        "top_blocked_ips":   dict(blocked_ip_counts.most_common(5)),
        "recent_requests":   logs[-50:],
        "banned_list":       [
            {"ip": ip, "until": datetime.fromtimestamp(ts).isoformat()}
            for ip, ts in bans.items()
        ]
    }

def get_matrix():
    with lock:
        logs   = list(REQUEST_LOG)
        bans   = dict(banned_ips)

    now = datetime.now()

    # Per-second timeline
    timeline = {}
    for r in logs:
        try:
            t   = datetime.fromisoformat(r["time"])
            sec = int((now - t).total_seconds())
            if 0 <= sec < 60:
                key = 60 - sec
                tl  = timeline.setdefault(key, {"allowed": 0, "blocked": 0})
                if r.get("blocked"):
                    tl["blocked"] += 1
                else:
                    tl["allowed"] += 1
        except Exception:
            pass

    timeline_arr = [
        {"sec": k, **timeline.get(k, {"allowed": 0, "blocked": 0})}
        for k in range(1, 61)
    ]

    # IP threat matrix
    ip_counts  = Counter(r["ip"] for r in logs)
    ip_blocked = Counter(r["ip"] for r in logs if r.get("blocked"))
    ip_matrix  = []
    for ip, total in ip_counts.most_common(20):
        blk    = ip_blocked.get(ip, 0)
        threat = ("critical" if ip in bans else
                  "high"     if blk > 10  else
                  "medium"   if blk > 0   else "low")
        ip_matrix.append({
            "ip": ip, "total": total,
            "blocked": blk, "allowed": total - blk,
            "threat": threat, "banned": ip in bans,
        })

    return {
        "timestamp":       now.isoformat(),
        "timeline":        timeline_arr,
        "ip_matrix":       ip_matrix,
        "summary": {
            "total":   len(logs),
            "blocked": sum(1 for r in logs if r.get("blocked")),
            "banned":  len(bans),
            "uptime":  int(time.time() - START_TIME),
        },
    }

def manual_ban(ip):
    with lock:
        banned_ips[ip] = time.time() + BAN_DURATION
        
def manual_unban(ip):
    with lock:
        if ip in banned_ips:
            del banned_ips[ip]
            return True
    return False
