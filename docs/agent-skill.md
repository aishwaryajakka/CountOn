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
intent routing and trusted compiler/clarification orchestration. Both use the
same six existing tools:

| Intent | Mapping |
| --- | --- |
| List | `list_expectations` |
| Detail | `list_expectations` → match → `get_expectation` |
| Clear, complete save intent | `compile_expectation` → `capture_expectation` |
| Ambiguous lower bill | `compile_expectation` → ask one question → `continue_expectation_compilation`; no expectation write until compiled |
| Explain failure | List/match → `explain_expectation_mismatch`; only recorded MISMATCH enables investigation |

Every tool argument is nested under exactly one `request` key. Real transport
remains **Streamable HTTP**. This does not make `/alexa` load skills, configure runtime Bedrock access, register tools or certify MCP Apps compliance.
Bedrock compiler/clarification/investigation already exist in the backend. See
[MCP docs](mcp.md) and the [simulator guide](../frontend/docs/alexa-demo.md).

## Validation

The specification recommends the official reference CLI:

```sh
skills-ref validate .agents/skills/counton
skills-ref read-properties .agents/skills/counton
```

Format validation does not certify host discovery, authentication or agent decisions.
Examples should also be checked against discovered schemas and service rules.
Relevant backend MCP and frontend tests cover the implementation independently.
This cleanup does not install a validator or make production mutations; rerun the
commands above when changing the skill artifact. Current test results belong in
validation reports, rather than a fixed test count here.
