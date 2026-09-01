"""
TESTS/UNIT/test_resolver.py
Tests the pure/testable parts of CORE/DNS-RESOLVER/resolver.py.

What's NOT tested here (needs a running process + real UDP socket,
can't be a clean unit test): the actual asyncio UDP server loop and
upstream forwarding. Verify that manually with:
    python CORE/DNS-RESOLVER/resolver.py
    dig @127.0.0.1 -p 5353 google.com

Run:
    pytest TESTS/UNIT/test_resolver.py -v
"""

import sys
import os
import importlib.util

# resolver.py lives in a hyphenated folder name, which isn't a valid
# Python package path -- load it directly from its file path instead
# of a normal "import".
_here = os.path.dirname(os.path.abspath(__file__))
_resolver_path = os.path.join(_here, "..", "..", "CORE", "DNS-RESOLVER", "resolver.py")
_spec = importlib.util.spec_from_file_location("resolver", _resolver_path)
resolver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(resolver)


def test_blocked_domain_is_detected():
    assert resolver.is_blocked("blocked-test.com.") is True


def test_blocked_domain_is_case_insensitive():
    assert resolver.is_blocked("BLOCKED-TEST.COM.") is True


def test_allowed_domain_is_not_blocked():
    assert resolver.is_blocked("google.com.") is False


def test_nxdomain_response_has_correct_rcode():
    import dns.message
    import dns.rcode

    query = dns.message.make_query("blocked-test.com.", "A")
    response = resolver.build_nxdomain_response(query)
    assert response.rcode() == dns.rcode.NXDOMAIN


def test_nxdomain_response_echoes_query_id():
    import dns.message

    query = dns.message.make_query("blocked-test.com.", "A")
    response = resolver.build_nxdomain_response(query)
    assert response.id == query.id
