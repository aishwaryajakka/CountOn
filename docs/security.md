# Security and Trust Boundaries

This describes implemented controls and their limits, not a security certification.
The detailed storage inventory is in [data policy](data-minimization-and-audit-policy.md).

## Authenticated user context and ownership

Supabase Auth owns passwords, sessions, confirmation, recovery and OAuth issuance.
The backend's `TokenVerifier` checks configured issuer, `aud=authenticated`,
signature, expiry/issued-at, UUID `sub`, authenticated role and allowed OAuth client
claims; anonymous/service-role identities cannot act as ordinary users. Asymmetric
tokens use project JWKS. The legacy HS256 path requires successful verification
against Supabase Auth as well as claim checks.

API dependencies, MCP context and ASK resolve the same `AuthenticatedUser`.
Owned queries and composite database relationships constrain expectations,
connections, evidence-linked actions and notifications. RLS policies provide
additional protection for direct hosted-database access; backend database roles
still require the service's authorization checks. The browser does not write
domain tables directly. Tests exercise two-user denial and session isolation.

Alexa's request signature establishes the transport, not CountOn ownership. The
linked access token must match the configured Alexa OAuth client; its `sub`
selects the CountOn profile. Alexa `userId`, `apiAccessToken`, a spoken token or an
untrusted JSON owner cannot authenticate a CountOn user. No production demo-user
fallback exists on that path. [ASK verification](traditional-alexa.md).

## Bounded execution and approval

The deterministic orchestrator has an allowlisted typed capability set. Public
conversation input is text, optional selected expectation and opaque session
reference; the browser cannot supply a tool/plan/trusted identity. Its MCP browser
route is discovery-only. Registered MCP tools enforce one nested `request` object,
validation and existing service ownership checks.

Web conversation and configured production ASK require capture confirmation.
Source-plan confirmation is separate; compilation alone cannot expand OAuth
scopes, connect accounts or approve evidence. Direct structured API/MCP capture
remains a supported authenticated action and is not a universal confirmation gate.

Request bodies, external I/O, model retries, token/concurrency budgets and worker
leases are bounded. Compiler tickets are owner-bound and replay-safe; direct
unticketed capture is not generically idempotent. Rate limits are process-local.
Reconcile uncertain saves rather than automatically creating another record.

## AI and external content

Only language compilation, clarification and grounded mismatch investigation call
Bedrock. Typed parsing, quote/value grounding and evidence citations constrain
output. No model can set an Evaluation outcome, execute arbitrary commands or
directly mutate SQL. Imported source text is data, not trusted instructions.
Deterministic provider extraction cannot use an email/Bee prompt injection as
permission to change a rule or issue a new tool call.

Why checks the owned latest Evaluation before selecting evidence. MATCH/UNKNOWN
do not invoke the investigator. Unsupported citations, conflicts or model failure
produce a conservative response. Response parsing rejects reasoning blocks; there
is no chain-of-thought persistence/logging feature. AWS still receives the selected
language/facts required for authorized inference; document that processing for users.

## State and token storage: important distinctions

| Storage | Implemented boundary |
| --- | --- |
| `conversation_records` | AES-GCM encrypted bounded Agent/Alexa context and replay receipts; owner binding, digests, expiry and fenced leases. Production requires this store. |
| `compilation_sessions` | Typed **JSON** clarification/capture ledger, owner/digest/expiry and resulting expectation ID. It is not application-layer encrypted; may contain the original utterance and extracted facts. Signing is not encryption. |
| `integration_credentials` / OAuth state | AES-GCM tokens/PKCE material with a separate private integration key and account binding. |
| Source projections/checkpoints | Encrypted provider facts/checkpoints, scoped by connection/generation and retention settings. |
| Bee local bridge | Bee authentication remains with the local CLI; CountOn pairing and revocable connector credentials use digests. Local bridge credential file is private and must not be shared. |

Do not put bearer/Supabase/AWS credentials in clarification answers, state, prompts
or audit metadata. The engine rejects recognized sensitive input patterns; that
does not justify sending secrets to it. Expiry rejects state reuse; it is not a
guarantee of immediate physical erasure of all compilation ledger rows. Review
retention/cleanup, database encryption and backups for production. Do not describe
all application state as encrypted or all private text as absent from SQL.

## Evidence provenance and minimization

Provider adapters retain relevant normalized facts and safe identity/version/time
references. `evidence_minimization.py` allowlists operational `raw_data`; public
evidence submissions cannot assert verified LIVE provider provenance. Simulator
endpoints stamp `SIMULATED_RING`/`SIMULATED_BEE`; no-detection and promises are not
outcome proofs. Matching a provider type alone never authorizes arbitrary correlation.

The public Evidence API accepts a JSON `value`. Its caller must submit minimum
necessary facts; the schema is not a universal sanitizer of arbitrary personal text.
Bounded summaries and user-authored claims can themselves be sensitive. Full email
bodies, audio/video, unrelated contacts and transcripts are not needed by the
provider workflows and should not be supplied or archived as evidence.

## Logging, audit and secrets

Structured application logs contain whitelisted operational labels and correlation
IDs, not Authorization, session cookies, raw ASK bodies, prompts or provider errors.
Audit metadata is allowlisted and source references are pseudonymous hashes.
User-facing audit joins may show already-authorized minimal evidence facts. Exact
previous explanation wording is not returned by the audit receipt API.

These controls do not certify platform/load-balancer/Supabase/AWS logging policies.
Review cloud logs, third-party monitoring and operator access separately. Do not
enable request-body/header debugging in production.

Keep `.env.local`, credentials and private keys ignored; tracked examples contain
placeholders and safe defaults only. Never expose privileged Supabase keys, database
URLs, AWS credentials or OAuth secrets through `NEXT_PUBLIC_*`. Frontend config
rejects recognized privileged Supabase key forms. The root Apache-2.0 license does
not replace vendored dependency licenses.

## Secret review and incident response

Run `python3 scripts/secret_scan.py` for redacted Gitleaks history/source scans.
Report filenames/rules, never values. Confirm whether a finding is a public test
constant, placeholder or actual credential. Replace exposed docs/sample values
with placeholders and rotate genuine credentials through their provider.
Do not rewrite Git history or production identity data automatically.

If history contains a potential credential, report: **“Potential credential exists
in git history. Manual credential rotation/history cleanup required.”** A clean
scanner run is useful evidence, not proof that every possible secret pattern or
external store has been audited. [Testing](testing.md) records the actual scan result.
