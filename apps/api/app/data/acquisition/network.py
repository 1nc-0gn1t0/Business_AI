"""DNS-pinned TLS, exact server-owned endpoint, no proxies, redirects or decompression."""

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from threading import Semaphore, Thread, Timer
from urllib.parse import urlsplit

from app.data.acquisition.schemas import AcquisitionError

ENDPOINT = "https://overpass-api.de/api/interpreter"
HOST = "overpass-api.de"
DNS_SLOT = Semaphore(1)


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not (
            isinstance(address, ipaddress.IPv6Address)
            and (address.ipv4_mapped or address.sixtofour or address.teredo)
        )
    )


def addresses() -> tuple[str, ...]:
    # One bounded DNS waiter; a stuck OS resolver cannot accumulate new worker threads.
    if not DNS_SLOT.acquire(blocking=False):
        raise AcquisitionError("network_dns_busy", retryable=True)
    result: Queue[tuple[str, ...]] = Queue(maxsize=1)

    def resolve() -> None:
        try:
            result.put(
                tuple(
                    sorted(
                        {
                            str(r[4][0])
                            for r in socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
                        }
                    )
                )
            )
        except OSError:
            result.put(())
        finally:
            DNS_SLOT.release()

    Thread(target=resolve, daemon=True).start()
    try:
        answers = result.get(timeout=5)
    except Empty:
        raise AcquisitionError("network_dns_timeout", retryable=True) from None
    if not answers or not all(public_address(ip) for ip in answers):
        raise AcquisitionError("network_address_forbidden")
    return answers


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, peer: str) -> None:
        super().__init__(HOST, 443, timeout=5, context=ssl.create_default_context())
        self.peer = peer

    def connect(self) -> None:
        if not public_address(self.peer):
            raise AcquisitionError("network_address_forbidden")
        family = socket.AF_INET6 if ":" in self.peer else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        try:
            raw.settimeout(5)
            # Numeric IP only: there is no second DNS resolution at connection time.
            raw.connect((self.peer, 443))
            if raw.getpeername()[0] != self.peer:
                raise AcquisitionError("network_peer_mismatch")
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
            if self.sock.getpeername()[0] != self.peer:
                raise AcquisitionError("network_peer_mismatch")
        except BaseException:
            raw.close()
            raise


def fetch(
    query: str,
    destination: Path,
    max_bytes: int,
    check: Callable[[], None],
    *,
    endpoint: str = ENDPOINT,
) -> int:
    if endpoint != ENDPOINT or urlsplit(endpoint).scheme != "https":
        raise AcquisitionError("network_endpoint_forbidden")
    connection: PinnedHTTPS | None = None
    watchdog: Timer | None = None
    started = time.monotonic()
    try:
        check()
        # All answers validated; one deterministic address, never a fallback to a private peer.
        connection = PinnedHTTPS(addresses()[0])
        connection.connect()
        assert connection.sock is not None
        transport = connection.sock

        def abort() -> None:
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            transport.close()

        watchdog = Timer(max(1, 120 - (time.monotonic() - started)), abort)
        watchdog.daemon = True
        watchdog.start()
        # Public queue may wait 15s plus the 25s query budget. Total deadline stays 120s.
        connection.sock.settimeout(45)
        connection.request(
            "POST",
            "/api/interpreter",
            query.encode(),
            {
                "User-Agent": "BusinessAI-U02/1.0 (+https://github.com/1nc-0gn1t0/Business_AI)",
                "Content-Type": "text/plain",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise AcquisitionError("network_redirect_forbidden")
        if response.status != 200:
            retry = response.getheader("Retry-After", "60")
            raise AcquisitionError(
                "source_http_error",
                retryable=response.status in {429, 502, 503, 504},
                retry_after=int(retry) if retry.isdecimal() else 86400,
            )
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise AcquisitionError("network_encoding_forbidden")
        if response.getheader("Content-Type", "").split(";")[0].strip() != "application/json":
            raise AcquisitionError("source_format_invalid")
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > max_bytes):
            raise AcquisitionError("download_size_exceeded")
        count = 0
        with destination.open("xb") as output:
            while True:
                check()
                if time.monotonic() - started > 120:
                    raise AcquisitionError("download_timeout", retryable=True)
                chunk = response.read1(min(65536, max_bytes - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > max_bytes:
                    raise AcquisitionError("download_size_exceeded")
                output.write(chunk)
        if length is not None and count != int(length):
            raise AcquisitionError("download_truncated", retryable=True)
        return count
    except ssl.SSLCertVerificationError:
        raise AcquisitionError("network_certificate_invalid") from None
    except TimeoutError:
        raise AcquisitionError("network_timeout", retryable=True) from None
    except (OSError, http.client.HTTPException):
        raise AcquisitionError("network_unavailable", retryable=True) from None
    finally:
        if watchdog:
            watchdog.cancel()
        if connection:
            connection.close()
