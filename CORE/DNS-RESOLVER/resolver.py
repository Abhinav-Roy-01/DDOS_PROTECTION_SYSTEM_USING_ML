"""
DNS-RESOLVER/resolver.py
Async UDP DNS resolver.

Build order for this file (Phase 1 — this is step 1 of 1 for now):
  1. Receive raw UDP packet -> parse with dnspython
  2. Check blacklist (stub set() below -- real feeds land here in Phase 3)
  3. Blocked?  -> build NXDOMAIN, send back immediately
  4. Allowed?  -> forward to upstream resolver, relay the real answer back

NOT yet wired in (later phases, don't build yet):
  - Redis cache check before the blacklist check      (Phase 1, next file)
  - ML anomaly scoring on the domain name              (Phase 4)
  - STIX/TAXII + real blacklist feeds                  (Phase 3)
  - DNS tunnelling detection                            (Phase 5)

Run locally (no root needed on port 5353):
  python resolver.py
Test from another terminal:
  dig @127.0.0.1 -p 5353 google.com
  dig @127.0.0.1 -p 5353 blocked-test.com   <- should return NXDOMAIN
"""

import asyncio
import logging

import dns.message
import dns.rcode
import dns.asyncquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("dns-resolver")

# --- config -----------------------------------------------------------
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 5353          # switch to 53 later, inside the Docker container
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

        # --- step 1: blacklist check (stub for now) ---
        if is_blocked(domain):
            log.info(f"  -> BLOCKED  {domain}")
            response = build_nxdomain_response(query)
            self.transport.sendto(response.to_wire(), addr)
            return

        # --- step 2: forward upstream, relay the real answer back ---
        try:
            reply, _ = await dns.asyncquery.udp_with_fallback(
                query, UPSTREAM_IP, port=UPSTREAM_PORT, timeout=UPSTREAM_TIMEOUT
            )
            self.transport.sendto(reply.to_wire(), addr)
            log.info(f"  -> ALLOWED  {domain}  ({len(reply.answer)} record(s))")
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
