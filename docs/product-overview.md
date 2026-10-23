# Product Overview

## Problem

A reminder can tell someone to check a bill. It cannot establish whether the bill
meets the amount they expected. An appointment in a calendar establishes a plan;
it does not prove that a plumber arrived. CountOn separates those assertions from
observed facts and from the conclusion drawn from them.

## Product thesis

Reminders remember what you need to do.
CountOn remembers what you're counting on.

The current product combines a web workspace, an MCP-backed conversation and a
signed Alexa Custom Skill adapter. They share the same owned expectation records.
Live Alexa account linking and device acceptance remain external setup/testing.

## Core loop

**Expectation → Evidence → Evaluation → Exception**

An Expectation is a user's intended outcome, with typed criteria where supported.
Evidence is an observation with its own source and observation time. Evaluation
applies deterministic rules to relevant evidence. An exception is the action that
may follow a meaningful mismatch, initially an in-app notification.

## State model

| Evaluation | Product meaning | Current behavior |
| --- | --- | --- |
| MATCH | The supported facts meet the recorded criteria. | No new mismatch notification. |
| UNKNOWN | The available facts do not justify a conclusion. | Keep watching; explain what is missing. |
| MISMATCH | Supported facts fail the criteria beyond configured materiality. | Update the expectation and create a deduplicated in-app notification when enabled. |

UNKNOWN is intentional. Missing Ring detection cannot establish nondelivery.
Bee conversation context cannot establish that an appointment happened. Stale,
contradictory or unauthorized provider evidence is also insufficient under the
monitoring policies. Unsupported generic temporal/event evaluations remain UNKNOWN.

An Evaluation result is distinct from the Expectation's stored lifecycle status.
Numeric/boolean MATCH normally changes status to `fulfilled`; MISMATCH changes it
to `contradicted`. UNKNOWN preserves an existing lifecycle status, and saved
`resolved`/`cancelled` states remain terminal. The UI displays the latest recorded
Evaluation separately. See [lifecycle](expectation-lifecycle.md).

## Product principles

- Quiet success: alert only when the relevant notification policy calls for it.
- Explicit uncertainty: do not convert incomplete context into a verdict.
- Evidence before conclusion: provider records must be relevant and authorized.
- AI interprets language and explains facts; the backend evaluator remains authoritative.
- Proactive monitoring uses bounded, approved workflows rather than unrestricted autonomy.
- A connected account grants only its approved scopes and source associations.
- Demonstrations identify simulated evidence, even while using real persistence.

## Example use cases

| Domain | Supported demonstration or boundary |
| --- | --- |
| Bills | Compare an observed numeric cost to a target/baseline; investigate a confirmed mismatch. |
| Deliveries | Demonstrate positive delivery observations; supported provider monitoring checks grounded IDs and coverage. |
| Appointments | Monitor supported calendar facts; a scheduled event is not proof of physical attendance. |
| Commitments | Review a Bee commitment as context; require independent outcome evidence. |
| Subscriptions | A possible application of supported bill facts; there is no universal subscription-management connector. |
| Home services | Capture the expectation and its sources; arbitrary real-world arrival detection is not implemented. |

These examples are not a promise of live access to every named provider. The
[integration matrix](integrations.md) separates code, simulation and external setup.

## User journey

1. Describe an expectation in the web conversation or Alexa, or supply structured criteria.
2. Clarify the next missing material fact. An unspecified previous bill requires an amount.
3. Approve conversational capture; persist only a complete expectation.
4. Connect an eligible source and confirm the proposed exact binding where applicable.
5. Normalize and correlate incoming evidence under that user's permissions.
6. Evaluate directly or through an enabled monitoring worker.
7. Notify for a supported mismatch under the user's preferences.
8. Ask Why for a grounded explanation of the recorded result.
9. Review the same evidence, history and safe audit records in the normal workspace.

Creation approval and source approval are separate. Saving a claim does not grant
mailbox access or guarantee an active worker. [Setup](setup.md),
[architecture](architecture.md) and [demo guide](demo-guide.md) explain the working paths.
