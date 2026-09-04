"""
DNS-RESOLVER/resolver.py
Async UDP DNS resolver.

Build order for this file:
  1. Receive raw UDP packet -> parse with dnspython               (done)
  2. Check Redis cache -- skip upstream entirely on a hit         (done, this step)
  3. Check blacklist (stub set() below -- real feeds land here in Phase 3)
  4. Blocked?  -> build NXDOMAIN, send back immediately
  5. Allowed?  -> forward to upstream resolver, cache the answer, relay it back

NOT yet wired in (later phases, don't build yet):
  - ML anomaly scoring on the domain name              (Phase 4)
  - STIX/TAXII + real blacklist feeds                  (Phase 3)
  - DNS tunnelling detection                            (Phase 5)

Run locally (no root needed on port 5353):
  python resolver.py
Test from another terminal:
  dig @127.0.0.1 -p 5353 google.com          <- first call: cache MISS
  dig @127.0.0.1 -p 5353 google.com          <- second call: cache HIT, much faster
  dig @127.0.0.1 -p 5353 blocked-test.com    <- should return NXDOMAIN
"""

import asyncio
import logging
import os
import sys

import dns.message
import dns.rcode
import dns.asyncquery
import dns.rdatatype

# dns_cache.py lives in ../CACHE/ -- add it to sys.path the same way we did
# for CAPTCHA/ and DASHBOARD/ in the HTTP-layer server.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "CACHE"))
import dns_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("dns-resolver")

# --- config -----------------------------------------------------------
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 15353          # switch to 53 later, inside the Docker container
UPSTREAM_IP = "8.8.8.8"
UPSTREAM_PORT = 53
UPSTREAM_TIMEOUT = 2.0       # seconds

# --- stub blacklist -----------------------------------------------------
# TODO Phase 3: replace this set with THREAT-INTEL/BLACKLISTS/loader.py
# reading from Redis (key pattern: blacklist:<domain>)
BLOCKED_DOMAINS = {
    "blocked-test.com.",     # dnspython names always end in a dot
    "malware-example.com.",
}


def is_blocked(domain: str) -> bool:
    """Phase 1 stub. Real version checks Redis set populated by THREAT-INTEL."""
    return domain.lower() in BLOCKED_DOMAINS


def build_nxdomain_response(query: dns.message.Message) -> dns.message.Message:
    """Builds a response that tells the client 'this domain does not exist'."""
    response = dns.message.make_response(query)
    response.set_rcode(dns.rcode.NXDOMAIN)
    return response


class UDPResolverProtocol(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        self.transport = transport
        log.info(f"Listening on {LISTEN_HOST}:{LISTEN_PORT} (upstream: {UPSTREAM_IP})")

    def datagram_received(self, data: bytes, addr):
        # Fire off the handling coroutine without blocking the event loop
        asyncio.create_task(self._handle_query(data, addr))

    async def _handle_query(self, data: bytes, addr):
        try:
            query = dns.message.from_wire(data)
        except Exception as e:
            log.warning(f"Malformed packet from {addr}: {e}")
            return

        if not query.question:
            return

        domain = query.question[0].name.to_text()
        qtype = dns.rdatatype.to_text(query.question[0].rdtype)
        log.info(f"{addr[0]:15s}  {domain:35s}  {qtype}")

        # --- step 1: cache check -- skip everything else on a hit ---
        cached = dns_cache.get_cached_response(domain, qtype)
        if cached is not None:
            # DNS responses MUST echo the query's own ID (RFC 1035) --
            # a client rejects a response whose ID doesn't match what it
            # sent, and each client query uses a fresh random ID (this is
            # also part of what prevents cache-poisoning/spoofing). The
            # cached bytes carry whatever ID the ORIGINAL upstream request
            # used, so we patch just those first 2 bytes to match THIS
            # query before replaying -- found via actual testing, not
            # something that would've been obvious from reading the code.
            patched = query.id.to_bytes(2, "big") + cached[2:]
            self.transport.sendto(patched, addr)
            log.info(f"  -> CACHE HIT  {domain}")
            return

        # --- step 2: blacklist check (stub for now) ---
        if is_blocked(domain):
            log.info(f"  -> BLOCKED  {domain}")
            response = build_nxdomain_response(query)
            self.transport.sendto(response.to_wire(), addr)
            return

        # --- step 3: forward upstream, cache the answer, relay it back ---
        try:
            reply, _ = await dns.asyncquery.udp_with_fallback(
                query, UPSTREAM_IP, port=UPSTREAM_PORT, timeout=UPSTREAM_TIMEOUT
            )
            wire = reply.to_wire()
            self.transport.sendto(wire, addr)
            dns_cache.store_response(domain, qtype, wire, dns_cache.extract_min_ttl(reply))
            log.info(f"  -> ALLOWED  {domain}  ({len(reply.answer)} record(s), cached)")
        except Exception as e:
            log.error(f"  -> upstream failure for {domain}: {e}")


async def main():
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        UDPResolverProtocol,
        local_addr=(LISTEN_HOST, LISTEN_PORT),
    )
    try:
        await asyncio.Future()  # run forever
    finally:
        transport.close()


if __name__ == "__main__":
    import dns.rdatatype  # imported here to keep the top import block clean
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down.")