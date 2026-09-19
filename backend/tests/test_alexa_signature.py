from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from httpx import AsyncClient

from app.alexa.verify import (
    ALEXA_SAN,
    AlexaSignatureError,
    AlexaVerifier,
)
from app.config import settings


PASSWORD = "hunter2hunter2"


def _make_cert(
    *,
    san: str = ALEXA_SAN,
    not_before_delta: timedelta = timedelta(days=-1),
    not_after_delta: timedelta = timedelta(days=1),
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "echo-api.amazon.com")]
    )
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + not_before_delta)
        .not_valid_after(now + not_after_delta)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(san)]),
            critical=False,
        )
    )
    cert = builder.sign(private_key=key, algorithm=hashes.SHA256())
    return key, cert


def _pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def _sign(key: rsa.RSAPrivateKey, body: bytes) -> str:
    signature = key.sign(body, padding.PKCS1v15(), hashes.SHA1())
    return base64.b64encode(signature).decode("ascii")


def _make_body() -> bytes:
    return json.dumps(
        {
            "version": "1.0",
            "session": {"attributes": {}, "user": {"accessToken": "x"}},
            "context": {},
            "request": {
                "type": "IntentRequest",
                "intent": {"name": "StartInterviewIntent"},
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        }
    ).encode()


@pytest.mark.asyncio
async def test_verify_accepts_signed_request() -> None:
    key, cert = _make_cert()
    pem = _pem(cert)
    body = _make_body()
    signature = _sign(key, body)
    verifier = AlexaVerifier(fetch_cert_chain=lambda url: _return(pem))
    await verifier.verify(
        body=body,
        signature_header=signature,
        cert_url_header="https://s3.amazonaws.com/echo.api/echo-api-cert.pem",
        body_timestamp=json.loads(body)["request"]["timestamp"],
    )


@pytest.mark.asyncio
async def test_verify_rejects_missing_signature_header() -> None:
    verifier = AlexaVerifier()
    with pytest.raises(AlexaSignatureError, match="Signature header missing"):
        await verifier.verify(
            body=b"{}",
            signature_header=None,
            cert_url_header="https://s3.amazonaws.com/echo.api/x.pem",
            body_timestamp=None,
        )


@pytest.mark.asyncio
async def test_verify_rejects_bad_cert_url_scheme() -> None:
    verifier = AlexaVerifier()
    with pytest.raises(AlexaSignatureError, match="https"):
        await verifier.verify(
            body=b"{}",
            signature_header="AAAA",
            cert_url_header="http://s3.amazonaws.com/echo.api/x.pem",
            body_timestamp=None,
        )


@pytest.mark.asyncio
async def test_verify_rejects_bad_cert_url_host() -> None:
    verifier = AlexaVerifier()
    with pytest.raises(AlexaSignatureError, match="host must be"):
        await verifier.verify(
            body=b"{}",
            signature_header="AAAA",
            cert_url_header="https://evil.example.com/echo.api/x.pem",
            body_timestamp=None,
        )


@pytest.mark.asyncio
async def test_verify_rejects_bad_cert_url_path_traversal() -> None:
    verifier = AlexaVerifier()
    with pytest.raises(AlexaSignatureError, match="path must start with"):
        await verifier.verify(
            body=b"{}",
            signature_header="AAAA",
            cert_url_header="https://s3.amazonaws.com/attacker/../not-echo.api/x.pem",
            body_timestamp=None,
        )


@pytest.mark.asyncio
async def test_verify_rejects_wrong_san() -> None:
    key, cert = _make_cert(san="attacker.example.com")
    verifier = AlexaVerifier(fetch_cert_chain=lambda url: _return(_pem(cert)))
    body = _make_body()
    with pytest.raises(AlexaSignatureError, match="SAN does not include"):
        await verifier.verify(
            body=body,
            signature_header=_sign(key, body),
            cert_url_header="https://s3.amazonaws.com/echo.api/x.pem",
            body_timestamp=json.loads(body)["request"]["timestamp"],
        )


@pytest.mark.asyncio
async def test_verify_rejects_expired_cert() -> None:
    key, cert = _make_cert(
        not_before_delta=timedelta(days=-10),
        not_after_delta=timedelta(days=-1),
    )
    verifier = AlexaVerifier(fetch_cert_chain=lambda url: _return(_pem(cert)))
    body = _make_body()
    with pytest.raises(AlexaSignatureError, match="expired"):
        await verifier.verify(
            body=body,
            signature_header=_sign(key, body),
            cert_url_header="https://s3.amazonaws.com/echo.api/x.pem",
            body_timestamp=json.loads(body)["request"]["timestamp"],
        )


@pytest.mark.asyncio
async def test_verify_rejects_tampered_body() -> None:
    key, cert = _make_cert()
    body = _make_body()
    signature = _sign(key, body)
    tampered = body.replace(b"IntentRequest", b"Attackerequest")
    verifier = AlexaVerifier(fetch_cert_chain=lambda url: _return(_pem(cert)))
    with pytest.raises(AlexaSignatureError, match="signature mismatch"):
        await verifier.verify(
            body=tampered,
            signature_header=signature,
            cert_url_header="https://s3.amazonaws.com/echo.api/x.pem",
            body_timestamp=json.loads(body)["request"]["timestamp"],
        )


@pytest.mark.asyncio
async def test_verify_rejects_stale_timestamp() -> None:
    key, cert = _make_cert()
    stale = (
        datetime.now(timezone.utc) - timedelta(seconds=600)
    ).isoformat().replace("+00:00", "Z")
    body = json.dumps(
        {
            "version": "1.0",
            "session": {},
            "context": {},
            "request": {"type": "LaunchRequest", "timestamp": stale},
        }
    ).encode()
    verifier = AlexaVerifier(fetch_cert_chain=lambda url: _return(_pem(cert)))
    with pytest.raises(AlexaSignatureError, match="outside"):
        await verifier.verify(
            body=body,
            signature_header=_sign(key, body),
            cert_url_header="https://s3.amazonaws.com/echo.api/x.pem",
            body_timestamp=stale,
        )


# ─── endpoint-level tests ──────────────────────────────────────────────────


async def _register_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_endpoint_rejects_missing_signature_when_flag_on(
    client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alexa_verify_signature", True)
    resp = await client.post(
        "/api/v1/alexa",
        json={"version": "1.0", "session": {}, "context": {}, "request": {"type": "LaunchRequest"}},
    )
    assert resp.status_code == 400
    assert "Signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_endpoint_still_accepts_bearer_when_flag_off(client: AsyncClient) -> None:
    token = await _register_login(client, f"al-{uuid.uuid4().hex[:8]}@example.com")
    resp = await client.post(
        "/api/v1/alexa",
        headers={"Authorization": f"Bearer {token}"},
        json={"version": "1.0", "session": {}, "context": {}, "request": {"type": "LaunchRequest"}},
    )
    assert resp.status_code == 200


async def _return(payload: bytes):
    return payload
