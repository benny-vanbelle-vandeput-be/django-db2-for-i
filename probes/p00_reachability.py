"""Probe 00: network reachability and TLS certificate check. No sign-on.

- TCP connect (open + close, no data) to the IBM i host server ports.
- TLS handshake on the TLS ports, validated against the container's CA store.
  On failure, the certificate is fetched without validation (handshake only)
  and its subject, issuer and dates are shown, so a certificate problem can be
  told apart from other TLS errors.
"""

from __future__ import annotations

import shutil
import socket
import ssl
import subprocess
from typing import Any

from _common import TCP_TIMEOUT_SECONDS, Settings, tcp_check

NEEDS_CONNECTION = False

PORTS = {
    449: "server mapper (as-svrmap)",
    8471: "database (as-database)",
    8476: "sign-on (as-signon)",
    9471: "database over TLS (as-database-s)",
    9476: "sign-on over TLS (as-signon-s)",
}
TLS_PORTS = (9471, 9476)


def _name(parts: tuple) -> str:
    return ", ".join(f"{key}={value}" for rdn in parts for key, value in rdn)


def _unverified_certificate(host: str, port: int) -> dict[str, Any]:
    """Fetch the server certificate without validation and describe it."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((host, port), timeout=TCP_TIMEOUT_SECONDS) as sock,
            context.wrap_socket(sock, server_hostname=host) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
    except (ssl.SSLError, OSError) as exc:
        return {"certificate_error": f"{type(exc).__name__}: {exc}"}
    if shutil.which("openssl") is None:
        return {"certificate": "openssl not available to decode the certificate"}
    decoded = subprocess.run(
        ["openssl", "x509", "-noout", "-subject", "-issuer", "-dates", "-ext", "subjectAltName"],
        input=ssl.DER_cert_to_PEM_cert(der),
        capture_output=True,
        text=True,
        check=False,
    )
    return {"certificate": decoded.stdout.strip() or decoded.stderr.strip()}


def tls_check(host: str, port: int) -> dict[str, Any]:
    context = ssl.create_default_context()
    try:
        with (
            socket.create_connection((host, port), timeout=TCP_TIMEOUT_SECONDS) as sock,
            context.wrap_socket(sock, server_hostname=host) as tls,
        ):
            cert = tls.getpeercert()
            return {
                "port": port,
                "verified": True,
                "protocol": tls.version(),
                "subject": _name(cert.get("subject", ())),
                "issuer": _name(cert.get("issuer", ())),
                "not_after": cert.get("notAfter"),
            }
    except ssl.SSLCertVerificationError as exc:
        return {
            "port": port,
            "verified": False,
            "category": "tls_certificate",
            "verify_code": exc.verify_code,
            "verify_message": exc.verify_message,
            **_unverified_certificate(host, port),
        }
    except (ssl.SSLError, OSError) as exc:
        return {
            "port": port,
            "verified": False,
            "category": "tls_handshake",
            "error": f"{type(exc).__name__}: {exc}",
        }


def run(settings: Settings, conn: None) -> dict[str, Any]:
    print(f"Reachability of {settings.host}")
    tcp = []
    for port, purpose in PORTS.items():
        result = {**tcp_check(settings.host, port), "purpose": purpose}
        tcp.append(result)
        state = f"open ({result['ms']} ms)" if result["open"] else f"closed: {result['error']}"
        print(f"  {port:>5} {purpose:<36} {state}")

    open_ports = {r["port"] for r in tcp if r["open"]}
    tls = [tls_check(settings.host, port) for port in TLS_PORTS if port in open_ports]
    for result in tls:
        print(f"\nTLS on port {result['port']}:")
        if result["verified"]:
            print(f"  certificate trusted ({result['protocol']})")
            print(f"  subject:  {result['subject']}")
            print(f"  issuer:   {result['issuer']}")
            print(f"  notAfter: {result['not_after']}")
        elif result["category"] == "tls_certificate":
            print(f"  CERTIFICATE NOT TRUSTED: {result['verify_message']}")
            details = result.get("certificate") or result.get("certificate_error", "")
            print("  " + details.replace("\n", "\n  "))
            print(
                "  Options: add the issuing CA to the image, or set DB2I_SSL=0 deliberately"
                " (the password is then sent unencrypted)."
            )
        else:
            print(f"  TLS handshake failed: {result['error']}")
    return {"tcp": tcp, "tls": tls}
