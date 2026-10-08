# CountOn Agent Skill

Inspect [SKILL.md](../.agents/skills/counton/SKILL.md) and its
[tool reference](../.agents/skills/counton/references/tools.md). They teach agents
when to read/capture expectations, preserve intent, and avoid fabricated evidence,
evaluation results or explanations.

The hackathon's [Build with Agent Skills page](https://apps.extensions.modelcontextprotocol.io/api/#build-with-agent-skills)
offers builders for MCP App UIs. They are unnecessary here: this artifact adds
usage instructions to the existing MCP service and web simulator. No MCP App
resources, extension metadata, backend routes or dependencies are added.

## Format and consumption

The artifact follows the [Agent Skills specification](https://agentskills.io/specification):
a directory named `counton` with YAML `name` and `description` in `SKILL.md`,
Markdown instructions and an optional `references/` file. It contains no custom
frontmatter keys, experimental permissions, credentials or connection metadata.

The specification defines contents, not a mandatory installation root. The
[client guide](https://agentskills.io/client-implementation/adding-skills-support)
describes `.agents/skills/` as the cross-client project convention used here.
Hosts discover metadata, activate `SKILL.md` when relevant, and load the reference
when constructing calls. Reload the host's catalog after adding files; discovery
and invocation syntax vary. For another skills root, copy the entire `counton`
directory there. No global installation is performed by this repository change.

Judges can inspect both files directly or select `counton` in a compatible host.
Hosts supporting `$skill-name` can try `$counton What am I counting on?`; that
syntax is host-specific.

Configure the host's CountOn Streamable HTTP endpoint and current Supabase bearer
session separately through its secure credential mechanism. The skill does not
install or authenticate a connection. If the host cannot forward a bearer token,
report that limitation; do not introduce shared credentials or assume an OAuth
flow CountOn has not implemented. Never paste tokens into skill files/chat.

## Complement to the simulator

The skill guides compatible agents; `/alexa` provides deterministic browser
conversation. Both use the existing tools:

| Intent | Mapping |
| --- | --- |
| List | `list_expectations` |
| Detail | `list_expectations` → match → `get_expectation` |
| Clear, complete save intent | Compile/validate → `capture_expectation` |
| Ambiguous lower bill | Clarification, no write |
| Explain failure | Stored record only; disclose absent reasoning tools |

Every tool argument is nested under exactly one `request` key. Real transport
remains **Streamable HTTP**. This does not make `/alexa` load skills, enable
Bedrock, register extra tools or certify MCP Apps compliance. See
[MCP docs](mcp.md) and the [simulator guide](../frontend/docs/alexa-demo.md).

## Validation

The specification recommends the official reference CLI:

```sh
skills-ref validate .agents/skills/counton
skills-ref read-properties .agents/skills/counton
```

For this pass the validator is installed in a temporary environment, without
changing project dependencies. Format validation does not certify host discovery,
authentication or agent decisions. JSON examples are additionally checked against
actual Pydantic contracts and numeric service rules; relative links and directory
name matching are checked. Relevant existing MCP/frontend tests provide regression
checks. Validating this documentation requires no production mutations.

Verified on 2026-10-08: `skills-ref` 0.1.0 (official repository commit
`69ef37e9424c0a7ea9dd2293b559e43ec8176379`) and the installed skill-creator
validator both passed. All three JSON examples passed Pydantic validation;
the numeric capture also passed service rules. Naming, supported metadata and
local documentation links passed structural checks.

Regression results: 28 backend MCP tests passed, with 10 dedicated-database
tests skipped without their opt-in configuration; 89 frontend tests passed,
with the endpoint/token-gated live test skipped. These checks do not claim
that a particular host has loaded or behaviorally evaluated the skill.
