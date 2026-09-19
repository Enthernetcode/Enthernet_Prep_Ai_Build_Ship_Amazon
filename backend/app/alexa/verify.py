"""Amazon Alexa request-signature verification.

Implements the checks documented at
https://developer.amazon.com/en-US/docs/alexa/custom-skills/host-a-custom-skill-as-a-web-service.html

The high level flow, applied by `verify_alexa_request`:

1. Validate the shape of `SignatureCertChainUrl` (scheme, host, port, path).
2. Fetch the PEM cert chain (cached in memory bounded by cert notAfter).
3. Confirm the leaf cert is currently valid and has a SAN matching
   `echo-api.amazon.com`.
4. Verify the RSA-SHA1 signature over the raw request body.
5. Confirm the JSON `request.timestamp` is within the configured window.

Any failure raises `AlexaSignatureError`. Callers translate that to HTTP 400.

Optional dependency injection makes the module testable without live HTTP:
`AlexaVerifier(fetch_cert_chain=...)`.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import unquote, urlparse

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtensionOID

from app.config import settings


ALEXA_SAN = "echo-api.amazon.com"
CERT_CHAIN_HOST = "s3.amazonaws.com"
CERT_CHAIN_PATH_PREFIX = "/echo.api/"


class AlexaSignatureError(Exception):
    """Raised when a request fails any of the Amazon-required checks."""


@dataclass
class _CachedCert:
    cert: x509.Certificate
    chain: list[x509.Certificate]
    expires_at: float


@dataclass
class AlexaVerifier:
    fetch_cert_chain: Callable[[str], Awaitable[bytes]] | None = None
    _cache: dict[str, _CachedCert] = field(default_factory=dict)

    def _validate_cert_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise AlexaSignatureError("cert chain url must use https")
        host = (parsed.hostname or "").lower()
        if host != CERT_CHAIN_HOST:
            raise AlexaSignatureError(f"cert chain host must be {CERT_CHAIN_HOST}")
        if parsed.port not in (None, 443):
            raise AlexaSignatureError("cert chain url must use default https port")
        path = unquote(parsed.path)
        # normalise `//` and `..` traversal.
        segments: list[str] = []
        for segment in path.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                if segments:
                    segments.pop()
                continue
            segments.append(segment)
        normalised = "/" + "/".join(segments)
        if not normalised.startswith(CERT_CHAIN_PATH_PREFIX):
            raise AlexaSignatureError(
                f"cert chain url path must start with {CERT_CHAIN_PATH_PREFIX}"
            )

    async def _load_chain(self, url: str) -> _CachedCert:
        cached = self._cache.get(url)
        if cached and cached.expires_at > time.time():
            return cached
        pem_bytes = await self._download(url)
        chain = _parse_pem_chain(pem_bytes)
        if not chain:
            raise AlexaSignatureError("cert chain empty")
        leaf = chain[0]
        _assert_cert_valid(leaf)
        _assert_alexa_san(leaf)
        for intermediate in chain[1:]:
            _assert_cert_valid(intermediate)
        earliest_notafter = min(
            _cert_notafter(c).timestamp() for c in chain
        )
        cached = _CachedCert(cert=leaf, chain=chain, expires_at=earliest_notafter)
        self._cache[url] = cached
        return cached

    async def _download(self, url: str) -> bytes:
        if self.fetch_cert_chain is not None:
            return await self.fetch_cert_chain(url)
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    def _validate_timestamp(self, body_timestamp: str | None) -> None:
        if not body_timestamp:
            raise AlexaSignatureError("request.timestamp missing")
        # Alexa uses ISO 8601 with a trailing Z.
        try:
            parsed = datetime.fromisoformat(body_timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AlexaSignatureError(f"request.timestamp unparseable: {exc}") from None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = abs((datetime.now(timezone.utc) - parsed).total_seconds())
        if delta > settings.alexa_timestamp_tolerance_seconds:
            raise AlexaSignatureError(
                f"request.timestamp outside {settings.alexa_timestamp_tolerance_seconds}s window"
            )

    async def verify(
        self,
        *,
        body: bytes,
        signature_header: str | None,
        cert_url_header: str | None,
        body_timestamp: str | None,
    ) -> None:
        if not signature_header:
            raise AlexaSignatureError("Signature header missing")
        if not cert_url_header:
            raise AlexaSignatureError("SignatureCertChainUrl header missing")
        try:
            signature = base64.b64decode(signature_header, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise AlexaSignatureError(f"Signature not base64: {exc}") from None

        self._validate_cert_url(cert_url_header)
        cached = await self._load_chain(cert_url_header)
        public_key = cached.cert.public_key()
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise AlexaSignatureError("cert public key is not RSA")
        try:
            public_key.verify(signature, body, padding.PKCS1v15(), hashes.SHA1())
        except InvalidSignature as exc:
            raise AlexaSignatureError(f"signature mismatch: {exc}") from None

        self._validate_timestamp(body_timestamp)


def _parse_pem_chain(pem_bytes: bytes) -> list[x509.Certificate]:
    text = pem_bytes.decode("ascii", errors="strict")
    boundary = "-----BEGIN CERTIFICATE-----"
    parts = text.split(boundary)
    chain: list[x509.Certificate] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        pem = boundary + "\n" + part
        chain.append(x509.load_pem_x509_certificate(pem.encode("ascii")))
    return chain


def _cert_notafter(cert: x509.Certificate) -> datetime:
    # `not_valid_after_utc` exists on cryptography 42+, otherwise fall back.
    naive = getattr(cert, "not_valid_after_utc", None)
    if naive is not None:
        return naive
    legacy = cert.not_valid_after
    if legacy.tzinfo is None:
        legacy = legacy.replace(tzinfo=timezone.utc)
    return legacy


def _cert_notbefore(cert: x509.Certificate) -> datetime:
    naive = getattr(cert, "not_valid_before_utc", None)
    if naive is not None:
        return naive
    legacy = cert.not_valid_before
    if legacy.tzinfo is None:
        legacy = legacy.replace(tzinfo=timezone.utc)
    return legacy


def _assert_cert_valid(cert: x509.Certificate) -> None:
    now = datetime.now(timezone.utc)
    if now < _cert_notbefore(cert):
        raise AlexaSignatureError("cert not yet valid")
    if now > _cert_notafter(cert):
        raise AlexaSignatureError("cert expired")


def _assert_alexa_san(cert: x509.Certificate) -> None:
    try:
        san = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        ).value
    except x509.ExtensionNotFound:
        raise AlexaSignatureError("cert has no SAN extension") from None
    names = san.get_values_for_type(x509.DNSName)
    if ALEXA_SAN not in names:
        raise AlexaSignatureError(f"cert SAN does not include {ALEXA_SAN}")


# Module-level singleton so cert cache persists across requests.
_default_verifier = AlexaVerifier()


def get_verifier() -> AlexaVerifier:
    return _default_verifier
