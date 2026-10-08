"""Supabase JWT verification independent of HTTP routes and persistence.

Asymmetric tokens use the configured project's JWKS. Legacy HS256 tokens must
also be verified by Supabase Auth; an API secret key is never a JWT signing key.
"""

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError

# Supabase-issued tokens can be a second ahead of the local clock. Keep the
# allowance narrow; signature and all required claim checks still apply.
JWT_CLOCK_SKEW_SECONDS = 5

@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID


class TokenVerifier:
    def __init__(self, settings: Settings):
        self.issuer = (settings.supabase_url or "").rstrip("/") + "/auth/v1"
        self.audience = "authenticated"
        self.publishable_key = settings.supabase_publishable_key
        self.configured = bool(settings.supabase_url)
        jwks_url = settings.supabase_jwks_url or self.issuer + "/.well-known/jwks.json"
        self.jwks = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=600, cache_keys=False, timeout=10)

    def verify(self, token: str) -> AuthenticatedUser:
        if not self.configured:
            raise AuthenticationError()
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            options = {"require": ["exp", "iat", "iss", "aud", "sub", "role"]}
            if algorithm in ("RS256", "ES256"):
                if not isinstance(header.get("kid"), str) or not header["kid"]:
                    raise AuthenticationError()
                key = self.jwks.get_signing_key_from_jwt(token)
                claims = jwt.decode(token, key.key, algorithms=[algorithm], audience=self.audience,
                                    issuer=self.issuer, options=options, leeway=JWT_CLOCK_SKEW_SECONDS)
            elif algorithm == "HS256" and self.publishable_key:
                # This preliminary decode checks claims, not trust. Only a
                # successful Auth-server check below can authenticate this path.
                claims = jwt.decode(token, algorithms=["HS256"], audience=self.audience, issuer=self.issuer,
                                    leeway=JWT_CLOCK_SKEW_SECONDS,
                                    options=dict(options, verify_signature=False, verify_exp=True,
                                                 verify_iat=True, verify_nbf=True, verify_aud=True, verify_iss=True))
                response = httpx.get(self.issuer + "/user", headers={
                    "apikey": self.publishable_key, "Authorization": f"Bearer {token}",
                }, timeout=10, follow_redirects=False)
                if response.status_code != 200 or response.json().get("id") != claims.get("sub"):
                    raise AuthenticationError()
            else:
                raise AuthenticationError()
            if claims.get("role") != "authenticated":
                raise AuthenticationError()
            return AuthenticatedUser(id=UUID(claims["sub"]))
        except (jwt.PyJWTError, httpx.HTTPError, ValueError, TypeError, KeyError):
            # Token data, server responses, and credential-bearing exceptions
            # are never included in the API response or logs.
            raise AuthenticationError() from None


@lru_cache
def get_token_verifier() -> TokenVerifier:
    return TokenVerifier(get_settings())
