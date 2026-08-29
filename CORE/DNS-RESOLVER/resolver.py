"""
DNS-RESOLVER/resolver.py
Async UDP DNS resolver on port 53.
Intercepts every query, checks Redis cache, ML scorer, and blacklists
before forwarding to upstream or returning NXDOMAIN for blocked domains.
"""
