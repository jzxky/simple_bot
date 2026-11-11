"""
hub_errors.py — Explain in plain words why a request to Player Hub failed.

describe(exc, url) turns urllib/socket/ssl errors into one sentence that
says what went wrong and what to check, e.g. a DNS failure, a refused port,
a timeout, a bad certificate or a proxy answering 503.
"""

import errno
import http.client
import socket
import ssl
import urllib.error
from urllib.parse import urlsplit


def _where(url: str) -> str:
    p = urlsplit(url or "")
    host = p.hostname or "the hub"
    port = p.port or (443 if p.scheme == "https" else 80)
    return f"{host}:{port}"


def _host(url: str) -> str:
    return urlsplit(url or "").hostname or "the hub"


def _http(code: int, reason: str, url: str) -> str:
    if code == 401:
        return "The hub rejected this bot's API key (401). Use the key from the hub's Clients page."
    if code == 403:
        return "The hub refused this bot (403). Its API key may have been revoked, or remote access isn't allowed for it."
    if code == 404:
        return (f"{_where(url)} answered 404 Not found. The Server URL may point at the wrong site "
                "(e.g. the bots subdomain instead of the hub), or the hub is too old for this feature.")
    if code in (502, 503, 504):
        return (f"{_where(url)} answered {code} {reason}. A proxy (HAProxy/nginx) is up but can't reach the hub "
                "behind it: the hub isn't running, or the proxy points at the wrong port.")
    if code >= 500:
        return f"The hub hit an error ({code} {reason}). Check the hub's log."
    return f"The hub answered {code} {reason}."


def describe(exc: BaseException, url: str = "") -> str:
    """One plain sentence for a failed hub request."""
    where, host = _where(url), _host(url)
    if isinstance(exc, urllib.error.HTTPError):
        return _http(exc.code, exc.reason or "", url)
    e = exc
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, BaseException):
        e = exc.reason
    if isinstance(e, ssl.SSLCertVerificationError):
        why = getattr(e, "verify_message", "") or str(e)
        tip = ""
        low = why.lower()
        if "expired" in low:
            tip = " The certificate has expired: renew it on the server."
        elif "self" in low and "signed" in low:
            tip = " It's self-signed: use a real certificate (e.g. Let's Encrypt)."
        elif "hostname" in low or "match" in low:
            tip = f" It wasn't issued for {host}: add {host} to the certificate."
        elif "local issuer" in low:
            tip = (" This computer can't check it: the certificate chain is incomplete on the server, "
                   "or (macOS) run Python's 'Install Certificates' once.")
        return f"The HTTPS certificate for {host} isn't trusted ({why}).{tip}"
    if isinstance(e, ssl.SSLError):
        why = getattr(e, "reason", None) or str(e)
        tip = " If this port serves plain HTTP, use http:// in the Server URL." \
            if "WRONG_VERSION_NUMBER" in str(e).upper() else ""
        return f"The secure connection to {where} failed ({why}).{tip}"
    if isinstance(e, socket.gaierror):
        return (f"Can't find {host}: the DNS lookup failed ({e.strerror or e}). "
                "Check the spelling of the Server URL and the domain's DNS record, and that this computer is online.")
    if isinstance(e, ConnectionRefusedError):
        return (f"{where} refused the connection: nothing is listening on that port. "
                "The hub (or HAProxy in front of it) isn't running, or the port in the Server URL is wrong.")
    if isinstance(e, (socket.timeout, TimeoutError)):
        return (f"No answer from {where} (timed out). The server may be down, or a firewall is "
                "blocking that port.")
    if isinstance(e, ConnectionResetError):
        return (f"{where} cut the connection. Often a proxy forwarding to the wrong place, or https:// "
                "used on a plain HTTP port (or the other way round).")
    if isinstance(e, http.client.RemoteDisconnected):
        return f"{where} closed the connection without answering. Check the hub's log and the proxy in front of it."
    if isinstance(e, OSError) and e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
        return f"No route to {where}: this computer can't reach that network ({e.strerror})."
    if "unknown url type" in str(e).lower():
        return "The Server URL must start with https:// (or http:// for a local address)."
    return f"Can't reach the hub at {where} ({e.__class__.__name__}: {e})."
