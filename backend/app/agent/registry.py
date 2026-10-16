"""Immutable capability policy. No callable, SQL or client-supplied mapping."""

from collections.abc import Mapping
from types import MappingProxyType

from app.agent.actions import AgentAction, CapabilityTool, ReasonCode

REGISTRY: Mapping[AgentAction, tuple[CapabilityTool, ...]] = MappingProxyType(
    {
        AgentAction.LIST_EXPECTATIONS: (CapabilityTool.LIST,),
        AgentAction.GET_EXPECTATION: (CapabilityTool.GET,),
        AgentAction.COMPILE_EXPECTATION: (CapabilityTool.COMPILE,),
        AgentAction.CONTINUE_CLARIFICATION: (CapabilityTool.CONTINUE,),
        AgentAction.CAPTURE_EXPECTATION: (CapabilityTool.CAPTURE,),
        AgentAction.EXPLAIN_MISMATCH: (CapabilityTool.EXPLAIN,),
        # Active cancellation must consume canonical state through continuation.
        AgentAction.CANCEL: (CapabilityTool.CONTINUE,),
        AgentAction.UNKNOWN: (),
    }
)


def tools_for(action: AgentAction) -> tuple[CapabilityTool, ...]:
    return REGISTRY[action]


REASONS: Mapping[AgentAction, tuple[ReasonCode, ...]] = MappingProxyType(
    {
        AgentAction.LIST_EXPECTATIONS: (ReasonCode.LIST_REQUEST,),
        AgentAction.GET_EXPECTATION: (ReasonCode.DETAIL_REQUEST,),
        AgentAction.COMPILE_EXPECTATION: (ReasonCode.CAPTURE_INTENT,),
        AgentAction.CONTINUE_CLARIFICATION: (ReasonCode.FOLLOW_UP,),
        AgentAction.CAPTURE_EXPECTATION: (ReasonCode.COMPILED_READY,),
        AgentAction.EXPLAIN_MISMATCH: (ReasonCode.WHY_QUESTION,),
        AgentAction.CANCEL: (ReasonCode.CANCEL_REQUEST,),
        AgentAction.UNKNOWN: (
            ReasonCode.UNSUPPORTED_REQUEST,
            ReasonCode.MISSING_REFERENCE,
            ReasonCode.NO_ACTIVE_CLARIFICATION,
            ReasonCode.POLICY_REJECTED,
        ),
    }
)
