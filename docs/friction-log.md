## 1. Stateful MCP debugging through a web proxy

Task attempted:
Connect the CountOn web agent to the Python MCP server over Streamable HTTP while preserving authentication and multi-turn state.

Steps taken:
- Configured the MCP client and server.
- Forwarded authenticated user context.
- Routed requests through the web application's server layer.
- Tested tool discovery and execution.

Expected result:
The MCP client and server should maintain a stable session and pass tool calls through the proxy cleanly.

Actual result:
Session handling, streaming behavior, header forwarding, and request-shape differences required additional custom proxy logic and debugging.

Severity:
High

Workaround:
We added a dedicated server-side agent proxy, standardized MCP tool arguments around a single nested request object, and added focused smoke tests around tool discovery and execution.

Actionable suggestion:
Provide an official Alexa+/MCP debugging console that shows session state, tool selection, tool arguments, responses, and transport errors end to end.

## 2. Bedrock structured-output reliability

Task attempted:
Convert natural-language expectations into strongly typed Pydantic objects through Amazon Bedrock.

Steps taken:
- Sent structured prompts through the Converse API.
- Validated returned JSON against Pydantic schemas.
- Tested malformed and incomplete model outputs.

Expected result:
The model should consistently return data matching the required schema.

Actual result:
Some responses required additional validation, normalization, or retry handling before they could safely enter the application.

Severity:
High

Workaround:
We added strict schema validation, repair/retry handling, and deterministic fallbacks before anything could be persisted.

Actionable suggestion:
Provide more first-party examples for production structured-output pipelines with schema validation, repair, retries, and model fallback patterns.

## 3. Multi-turn clarification before persistence

Task attempted:
Let users create expectations naturally even when their first request is incomplete, such as "make sure my bill is lower."

Steps taken:
- Sent incomplete requests through the language layer.
- Tested how missing thresholds, dates, and verification conditions were handled.

Expected result:
The system should ask for the missing information before saving an expectation.

Actual result:
A one-shot LLM flow could infer or invent missing values, which was not acceptable for a monitoring system.

Severity:
High

Workaround:
We built a stateful clarification flow that asks one focused question at a time and does not persist the expectation until required fields are confirmed.

Actionable suggestion:
Provide more reference patterns for persistent slot-filling and multi-turn state in Alexa+/MCP experiences.

## 4. Distinguishing missing evidence from failure

Task attempted:
Evaluate expectations whose evidence may arrive asynchronously, such as a package delivery or utility bill.

Steps taken:
- Created expectations with deadlines.
- Evaluated them before evidence arrived.
- Tested notification behavior.

Expected result:
The system should remain undecided while evidence is still legitimately pending.

Actual result:
A naive two-state design made it too easy to treat missing evidence as failure.

Severity:
Medium

Workaround:
We introduced a deterministic three-state model: MATCH, UNKNOWN, and MISMATCH. Missing evidence remains UNKNOWN until the evaluation conditions justify a final result.

Actionable suggestion:
Provide more event-driven examples that distinguish "not yet observed" from "failed" when building proactive agent workflows.