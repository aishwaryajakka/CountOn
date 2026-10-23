# CountOn MCP

The canonical developer guide is [docs/mcp.md](../../../docs/mcp.md): architecture,
authentication, tool contracts, local/network smoke and remote deployment.
See [setup](../../../docs/setup.md) and [security](../../../docs/security.md) for
configuration and trust boundaries. Transport tests exercise protocol `2025-06-18`;
this is distinct from the Python SDK 2.x package version.
See [Bedrock integration](../../../docs/bedrock-integration.md) for conversational
orchestration, the durable lifecycle ledger and intelligence rollout.

Local endpoint: `http://127.0.0.1:8003/mcp` (real Streamable HTTP).
From `backend` after configuration and `alembic upgrade head`:

```sh
source .venv/bin/activate
DATABASE_TARGET=local python -m app.mcp
```

The current server registers `capture_expectation`, `get_expectation`,
`list_expectations`, `compile_expectation`, `continue_expectation_compilation`, and
`explain_expectation_mismatch`. Every tool accepts exactly one `request` argument.
It reuses existing JWT verification, ownership checks, services and the canonical
compiler/clarification/investigator. The deterministic evaluator decides outcomes;
Bedrock interprets/explains only. Local implementation does not certify that the
latest intelligence code is deployed or that real Alexa/Echo linking is complete.
