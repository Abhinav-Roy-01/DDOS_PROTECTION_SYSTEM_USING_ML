"""
REPUTATION/domain_reputation.py
Multi-source domain reputation lookup: Redis cache, local blacklist,
STIX/TAXII, VirusTotal, AbuseIPDB. Returns score 0-100 with sources.
"""
