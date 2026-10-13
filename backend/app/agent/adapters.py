"""Approved adapter to the existing MCP tools; no direct persistence or inference."""

import re
from builtins import BaseExceptionGroup
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, SecretStr, ValidationError

from app.agent.actions import CapabilityTool, FailureCode
from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.mcp.schemas import (
    CaptureExpectationInput,
    CompilationResult,
    CompileExpectationInput,
    ContinueCompilationInput,
    ExpectationListResult,
    ExpectationResult,
    ExplainMismatchInput,
    ExplanationResult,
    GetExpectationInput,
    ListExpectationsInput,
)
from app.mcp.tools import SessionFactory

CapabilityRequest = (
    CaptureExpectationInput
    | CompileExpectationInput
    | ContinueCompilationInput
    | ExplainMismatchInput
    | GetExpectationInput
    | ListExpectationsInput
)
CapabilityResponse = (
    ExpectationResult | ExpectationListResult | CompilationResult | ExplanationResult
)

_REQUESTS: Mapping[CapabilityTool, type[BaseModel]] = MappingProxyType(
    {
        CapabilityTool.LIST: ListExpectationsInput,
        CapabilityTool.GET: GetExpectationInput,
        CapabilityTool.COMPILE: CompileExpectationInput,
        CapabilityTool.CONTINUE: ContinueCompilationInput,
        CapabilityTool.CAPTURE: CaptureExpectationInput,
        CapabilityTool.EXPLAIN: ExplainMismatchInput,
    }
)
_RESPONSES: Mapping[CapabilityTool, type[CapabilityResponse]] = MappingProxyType(
    {
        CapabilityTool.LIST: ExpectationListResult,
        CapabilityTool.GET: ExpectationResult,
        CapabilityTool.COMPILE: CompilationResult,
        CapabilityTool.CONTINUE: CompilationResult,
        CapabilityTool.CAPTURE: ExpectationResult,
        CapabilityTool.EXPLAIN: ExplanationResult,
    }
)


class CapabilityError(Exception):
    def __init__(self, code: FailureCode) -> None:
        self.code = code
        super().__init__(code.value)


class CapabilityAdapter(Protocol):
    async def call(
        self, user: AuthenticatedUser, tool: CapabilityTool, request: CapabilityRequest
    ) -> CapabilityResponse: ...


class CountOnMcpAdapter:
    """In-process SDK client using existing MCP registration and owned services.

    The host must supply an already JWT-verified principal. This is not an auth
    bypass endpoint: no principal can be supplied in tool JSON. Local callers use
    this adapter; the web route uses StreamableMcpAdapter with current bearer auth.
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    async def call(
        self, user: AuthenticatedUser, tool: CapabilityTool, request: CapabilityRequest
    ) -> CapabilityResponse:
        if not isinstance(user, AuthenticatedUser):
            raise AuthenticationError()
        if not isinstance(tool, CapabilityTool) or type(request) is not _REQUESTS[tool]:
            raise CapabilityError(FailureCode.INVALID_REQUEST)
        try:
            async with self._client(user) as client:
                output = await client.call_tool(
                    tool.value, {"request": request.model_dump(mode="json")}
                )
            if output.is_error:
                # Match only safe codes. Never forward raw MCP/provider errors.
                text = " ".join(
                    block.text for block in output.content if block.type == "text"
                )
                code = (
                    FailureCode.NOT_FOUND
                    if re.search(r"\bNOT_FOUND:", text)
                    else FailureCode.UNAUTHORIZED
                    if re.search(r"\bUNAUTHORIZED:", text)
                    else FailureCode.STATE_REJECTED
                    if re.search(
                        r"\b(?:CLARIFICATION_EXPIRED|CLARIFICATION_UNAVAILABLE|TOOL_VALIDATION_ERROR):",
                        text,
                    )
                    else FailureCode.INVALID_REQUEST
                    if re.search(r"\b(?:INVALID_ARGUMENTS|INVALID_EXPECTATION):", text)
                    else FailureCode.UNAVAILABLE
                )
                raise CapabilityError(code)
            if not isinstance(output.structured_content, dict):
                raise CapabilityError(FailureCode.PROTOCOL_ERROR)
            return _RESPONSES[tool].model_validate(output.structured_content)
        except CapabilityError:
            raise
        except ValidationError:
            raise CapabilityError(FailureCode.PROTOCOL_ERROR) from None
        except Exception as error:  # noqa: BLE001 -- mask transport/provider details

            def safe_code(exc: BaseException) -> FailureCode:
                if isinstance(exc, CapabilityError):
                    return exc.code
                if isinstance(exc, BaseExceptionGroup):
                    for nested in exc.exceptions:
                        code = safe_code(nested)
                        if code != FailureCode.UNAVAILABLE:
                            return code
                return FailureCode.UNAVAILABLE

            raise CapabilityError(safe_code(error)) from None

    @asynccontextmanager
    async def _client(self, user: AuthenticatedUser) -> AsyncIterator[Client]:
        from app.mcp.server import create_server

        kwargs = (
            {}
            if self._session_factory is None
            else {"session_factory": self._session_factory}
        )
        server = create_server(user_resolver=lambda ctx: user, **kwargs)
        async with Client(server, raise_exceptions=False, cache=None) as client:
            yield client


class StreamableMcpAdapter(CountOnMcpAdapter):
    """Request-scoped bearer forwarding to a configured MCP endpoint only.

    The verified principal comes from existing FastAPI JWT validation. Credentials
    stay in this ephemeral adapter, never in the long-lived conversation store.
    No remote URL is accepted from browser input and redirects are rejected.
    """

    def __init__(self, settings: Settings, token: SecretStr) -> None:
        super().__init__()
        self._settings = settings
        self._token = token

    @asynccontextmanager
    async def _client(self, user: AuthenticatedUser) -> AsyncIterator[Client]:
        endpoint = self._settings.mcp_public_url
        if not endpoint:
            raise CapabilityError(FailureCode.UNAVAILABLE)
        url = urlsplit(endpoint)
        if url.scheme != "https" and not (
            self._settings.environment != "production"
            and url.scheme == "http"
            and url.hostname in ("localhost", "127.0.0.1", "::1")
        ):
            raise CapabilityError(FailureCode.UNAVAILABLE)

        async def check_status(response: httpx.Response) -> None:
            if response.status_code in (401, 403):
                raise CapabilityError(FailureCode.UNAUTHORIZED)
            if response.is_redirect:
                raise CapabilityError(FailureCode.UNAVAILABLE)

        async with (
            httpx.AsyncClient(
                headers={"Authorization": "Bearer " + self._token.get_secret_value()},
                follow_redirects=False,
                timeout=180,
                event_hooks={"response": [check_status]},
            ) as http,
            Client(
                streamable_http_client(endpoint, http_client=http),
                raise_exceptions=False,
                cache=None,
                read_timeout_seconds=180,
            ) as client,
        ):
            discovered = await client.list_tools()
            if not set(_REQUESTS).issubset({tool.name for tool in discovered.tools}):
                raise CapabilityError(FailureCode.PROTOCOL_ERROR)
            yield client
