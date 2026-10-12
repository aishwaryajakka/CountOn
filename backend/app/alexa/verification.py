"""Amazon ASK verification on the original HTTP body; never a development bypass."""

import asyncio
import json
import re
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import certifi
import httpx
from ask_sdk_core.serialize import DefaultSerializer
from ask_sdk_model.request_envelope import RequestEnvelope
from ask_sdk_webservice_support.verifier import RequestVerifier, TimestampVerifier
from asn1crypto import pem, x509
from cryptography.hazmat.primitives.hashes import SHA256
from pyhanko_certvalidator import CertificateValidator, ValidationContext


class InvalidAlexaRequest(Exception):
    """Safe transport failure; never retain the body, headers or SDK exception."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidAlexaRequest()
        result[key] = value
    return result


@lru_cache(maxsize=1)
def trust_roots() -> tuple[x509.Certificate, ...]:
    """Mozilla CA bundle, not certificates supplied by an Alexa request."""
    return tuple(
        x509.Certificate.load(der)
        for kind, _, der in pem.unarmor(
            Path(certifi.where()).read_bytes(), multiple=True
        )
        if kind == "CERTIFICATE"
    )


class _BoundedRequestVerifier(RequestVerifier):
    """Keep SDK cryptography/CA/SAN checks; bound certificate I/O and caching."""

    def __init__(self) -> None:
        super().__init__(signature_key="Signature-256", hash_algorithm=SHA256())
        self._bounded_cache: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    def _validate_certificate_url(self, cert_url: str) -> None:
        super()._validate_certificate_url(cert_url)
        parsed = urlsplit(cert_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc not in ("s3.amazonaws.com", "s3.amazonaws.com:443")
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"/echo\.api/[A-Za-z0-9_-]+\.pem", parsed.path)
        ):
            raise InvalidAlexaRequest()

    def _load_cert_chain(self, cert_url: str) -> bytes:
        cached = self._bounded_cache.get(cert_url)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        # No redirects, ambient proxy credentials or unbounded urlopen/read.
        with (
            httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client,
            client.stream("GET", cert_url) as response,
        ):
            if response.status_code != 200:
                raise InvalidAlexaRequest()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 65536:
                    raise InvalidAlexaRequest()
        data = bytes(body)
        self._bounded_cache[cert_url] = (time.monotonic() + 3600, data)
        self._bounded_cache.move_to_end(cert_url)
        while len(self._bounded_cache) > 128:
            self._bounded_cache.popitem(last=False)
        return data

    def _validate_cert_chain(self, cert_chain: bytes) -> None:
        # Use the maintained PKIX/digital-signature validator. ASK still imports
        # legacy certvalidator/oscrypto; its native import is pinned/tested in CI.
        # SDK URL, expiry, Alexa SAN and SHA-256 body verification remain intact.
        certs = [
            x509.Certificate.load(der)
            for kind, _, der in pem.unarmor(cert_chain, multiple=True)
            if kind == "CERTIFICATE"
        ]
        if not certs or len(certs) > 10:
            raise InvalidAlexaRequest()
        validator = CertificateValidator(
            certs[0],
            certs[1:],
            validation_context=ValidationContext(
                trust_roots=trust_roots(), allow_fetching=False
            ),
        )
        # Called only in the verifier worker thread, never in the ASGI loop.
        asyncio.run(validator.async_validate_usage({"digital_signature"}))  # type: ignore[no-untyped-call]


class AlexaRequestVerifier:
    def __init__(self) -> None:
        self.signature = _BoundedRequestVerifier()
        self.timestamp = TimestampVerifier(tolerance_in_millis=150000)

    def verify(
        self, headers: dict[str, str], body: bytes, skill_id: str
    ) -> dict[str, Any]:
        try:
            serialized = body.decode("utf-8")
            data = json.loads(serialized, object_pairs_hook=_unique_object)
            if not isinstance(data, dict) or data.get("version") != "1.0":
                raise InvalidAlexaRequest()
            context = data["context"]["System"]
            session = data["session"]
            if (
                context["application"]["applicationId"] != skill_id
                or session["application"]["applicationId"] != skill_id
                or session["user"]["userId"] != context["user"]["userId"]
            ):
                raise InvalidAlexaRequest()
            envelope = DefaultSerializer().deserialize(serialized, RequestEnvelope)
            # Timestamp first to reject stale requests before certificate I/O.
            self.timestamp.verify(headers, serialized, envelope)
            self.signature.verify(headers, serialized, envelope)
            return data
        except Exception:  # noqa: BLE001 - Mask untrusted input and third-party SDK errors
            # Do not propagate SDK text (it may include attacker-controlled URLs).
            raise InvalidAlexaRequest() from None


@lru_cache(maxsize=1)
def get_alexa_verifier() -> AlexaRequestVerifier:
    return AlexaRequestVerifier()
