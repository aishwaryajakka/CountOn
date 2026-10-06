# CountOn MCP

The canonical integration and developer guide is [docs/mcp.md](../../../docs/mcp.md).
It covers architecture, local startup, auth, contracts, smoke/testing,
Person 2's compiler seam, future tools, and Alexa+ next steps.

Endpoint: `http://127.0.0.1:8003/mcp` (Streamable HTTP).
From `backend`, start with:

```bash
source .venv/bin/activate
DATABASE_TARGET=local python -m app.mcp
```

This uses existing services, repositories, and JWT verification. Only
`capture_expectation`, `get_expectation`, and `list_expectations` are registered.
The compiler Protocol is a future handoff contract, not an implementation.
