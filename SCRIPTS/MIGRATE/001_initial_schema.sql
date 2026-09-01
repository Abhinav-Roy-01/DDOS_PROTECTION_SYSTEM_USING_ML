CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE dns_queries (
  time TIMESTAMPTZ NOT NULL, source_ip INET, domain TEXT, qtype TEXT,
  response TEXT, blocked BOOLEAN, threat_score FLOAT, ml_label TEXT, latency_ms FLOAT
);
SELECT create_hypertable('dns_queries', 'time');

CREATE TABLE blocked_domains (
  domain TEXT PRIMARY KEY, reason TEXT, source TEXT, confidence FLOAT,
  added_at TIMESTAMPTZ DEFAULT NOW(), expires_at TIMESTAMPTZ
);

CREATE TABLE threat_feeds (
  id SERIAL PRIMARY KEY, name TEXT UNIQUE, url TEXT,
  last_synced TIMESTAMPTZ, domain_count INTEGER, status TEXT
);

-- HTTP-layer shield request log (mirrors in-memory REQUEST_LOG from HTTP-LAYER-SHIELD/API/rate_limiter.py)
CREATE TABLE http_shield_requests (
  time TIMESTAMPTZ NOT NULL, ip INET, path TEXT, method TEXT,
  blocked BOOLEAN, ml_verdict TEXT, ml_score FLOAT
);
SELECT create_hypertable('http_shield_requests', 'time');
