"""Credential-free Alexa import/native crypto smoke; failures remain fatal.

Run before pytest collection. Both Linux FFI paths must load independently. This
is not live Alexa acceptance; request signature/CA/SAN/expiry tests run in pytest.
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def verify_imports(backend: str) -> None:
    import oscrypto

    if backend == "ctypes":
        oscrypto.use_ctypes()
    from ask_sdk_webservice_support.verifier import RequestVerifier, TimestampVerifier
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from oscrypto import asymmetric
    from pyhanko_certvalidator import CertificateValidator, ValidationContext

    from app.alexa.adapter import AlexaAdapter
    from app.alexa.verification import AlexaRequestVerifier, trust_roots

    # Import asymmetric: unlike top-level oscrypto, this loads its native backend.
    # ASK body signatures and our PKIX path use cryptography, not oscrypto RSA.
    if asymmetric.__name__ != "oscrypto.asymmetric":
        raise RuntimeError("Native oscrypto dependency did not load")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    message = b"CountOn Alexa crypto import smoke"
    signed = private.sign(message, padding.PKCS1v15(), hashes.SHA256())
    public.verify(signed, message, padding.PKCS1v15(), hashes.SHA256())
    try:
        public.verify(
            signed, message + b"tampered", padding.PKCS1v15(), hashes.SHA256()
        )
    except InvalidSignature:
        pass  # Expected rejection, never a libcrypto/import exception.
    else:
        raise RuntimeError("Native crypto accepted a tampered signature")
    verifier = AlexaRequestVerifier()
    if not isinstance(verifier.signature, RequestVerifier) or not isinstance(
        verifier.timestamp, TimestampVerifier
    ):
        raise TypeError("Alexa verifier did not load SDK verification classes")
    if not trust_roots() or not all(
        (AlexaAdapter, CertificateValidator, ValidationContext)
    ):
        raise RuntimeError("Alexa certificate verification dependencies did not load")
    print(f"PASS Alexa adapter, certificate dependencies and native crypto ({backend})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("default", "ctypes"))
    args = parser.parse_args()
    if args.backend:
        verify_imports(args.backend)
        return 0
    # Backend choice must happen before importing oscrypto crypto modules. Fresh
    # interpreters prevent one successful FFI import from masking the other path.
    for backend in ("default", "ctypes"):
        subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--backend", backend],
            check=True,
            timeout=60,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
