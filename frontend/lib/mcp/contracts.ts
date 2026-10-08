import { z } from 'zod';

export const toolNames = ['capture_expectation', 'get_expectation', 'list_expectations', 'compile_expectation', 'continue_expectation_compilation', 'explain_expectation_mismatch'] as const;
export type ToolName = typeof toolNames[number];
const expectationType = z.enum(['numeric_comparison', 'boolean', 'temporal', 'event']);
const status = z.enum(['monitoring', 'fulfilled', 'contradicted', 'unknown', 'resolved', 'cancelled']);
const capture = z.strictObject({
  claim: z.string().trim().min(1), type: expectationType,
  compilation_state: z.string().max(24000).optional(),
  metric: z.string().trim().min(1).max(100).nullable().optional(),
  comparison: z.enum(['less_than', 'less_than_or_equal', 'greater_than', 'greater_than_or_equal', 'equal', 'not_equal']).nullable().optional(),
  baseline: z.number().nullable().optional(), target_value: z.number().nullable().optional(),
  deadline: z.iso.datetime({ offset: true }).nullable().optional(),
  evidence_sources: z.array(z.string()).optional(), materiality_threshold: z.number().min(0).max(1).optional(),
});
const list = z.strictObject({ limit: z.number().int().min(1).max(100).optional(), offset: z.number().int().min(0).optional(), status: status.nullable().optional(), type: expectationType.nullable().optional() });
const get = z.strictObject({ expectation_id: z.uuid() });
const compile = z.strictObject({ conversational: z.boolean().optional(), compilation_id: z.uuid().optional(), text: z.string().trim().min(1).max(2000), timezone: z.string().min(1).max(100), locale: z.string().regex(/^[a-z]{2}(?:-[A-Z]{2})?$/).nullable().optional() });
const continuation = z.strictObject({ state: z.string().min(1).max(24000), answer: z.string().trim().min(1).max(2000) });
export const compilationSchema = z.strictObject({ status: z.enum(['compiled', 'clarification', 'cancelled', 'expired', 'unsupported', 'error']), message: z.string(), expectation: capture.nullable().optional(), state: z.string().max(24000).nullable().optional(), capture_state: z.string().max(24000).nullable().optional(), code: z.string().nullable().optional(), bedrock_used: z.boolean(), prompt_version: z.string(), clarification_turn: z.number().int().min(0) });
export const conversationSchema = z.strictObject({ status: z.enum(['compiled', 'clarification', 'cancelled', 'expired', 'unsupported', 'error']), message: z.string(), state: z.string().max(24000).nullable(), saved: z.object({ id: z.uuid(), claim: z.string(), type: z.string(), metric: z.string().nullable(), status: z.string(), created_at: z.string() }).nullable(), bedrock_used: z.boolean(), clarification_turn: z.number().int().min(0), code: z.string().nullable().optional() });
export const explanationSchema = z.strictObject({ expectation_id: z.uuid().optional(), evidence_ids: z.array(z.uuid()).max(12).optional(), fallback_used: z.boolean().optional(), evaluation_id: z.uuid().nullable().optional(), result: z.enum(['MATCH', 'UNKNOWN', 'MISMATCH']).nullable(), message: z.string(), code: z.string().nullable().optional(), bedrock_used: z.boolean(), explanation: z.object({ summary: z.string(), key_factors: z.array(z.object({ description: z.string(), evidence_refs: z.array(z.string()) })), caveats: z.array(z.string()), confidence_note: z.string(), generation: z.enum(['bedrock', 'deterministic']) }).nullable() });
const inputs = { capture_expectation: capture, get_expectation: get, list_expectations: list, compile_expectation: compile, continue_expectation_compilation: continuation, explain_expectation_mismatch: get };
export const actionSchema = z.union([
  z.strictObject({ action: z.literal('list_tools') }),
  z.strictObject({ action: z.literal('converse'), text: z.string().trim().min(1).max(2000), state: z.string().max(24000).nullable(), turn_id: z.uuid(), timezone: z.string().min(1).max(100), locale: z.string().regex(/^[a-z]{2}(?:-[A-Z]{2})?$/).nullable() }),
  ...toolNames.map(tool => z.strictObject({ action: z.literal('call_tool'), tool: z.literal(tool), arguments: z.strictObject({ request: inputs[tool] }) })),
]);
export type McpAction = z.infer<typeof actionSchema>;
export const errorMessages = {
  AUTH_REQUIRED: 'Sign in to use CountOn tools.', AUTH_EXPIRED: 'Your session was rejected. Sign in again.',
  MCP_UNAVAILABLE: 'CountOn tools are temporarily unavailable. Try again later.',
  MCP_PROTOCOL_ERROR: 'CountOn tools returned an unexpected response. Try again later.',
  TOOL_NOT_FOUND: 'This tool is not available.', TOOL_VALIDATION_ERROR: 'Check the structured tool inputs and try again.',
  BEDROCK_DISABLED: "I couldn't interpret that expectation right now. Please try again.",
  BEDROCK_UNAVAILABLE: "I couldn't interpret that expectation right now. Please try again.",
  BEDROCK_THROTTLED: 'The interpreter is busy. Please try again shortly.',
  COMPILER_INVALID_OUTPUT: "I couldn't interpret that safely. Please restate your expectation.",
  CLARIFICATION_REQUIRED: 'I need a little more information.', CLARIFICATION_EXPIRED: 'That conversation expired. Please start again.',
  CLARIFICATION_UNAVAILABLE: 'Clarification is temporarily unavailable. Please try again.',
  UNSUPPORTED_EXPECTATION: 'Please describe one expectation with a clear subject, amount and timing.',
  NO_EXPECTATION: "I couldn't find an expectation about that.", NO_EVALUATION: 'This expectation has not been evaluated yet.',
  NO_EVIDENCE: 'CountOn has insufficient supporting evidence to explain why.', NOT_MISMATCH: 'The recorded evaluation does not indicate a mismatch.',
  INVESTIGATION_UNAVAILABLE: 'The AI explanation is unavailable; the recorded evaluation is still available.',
  TOOL_EXECUTION_ERROR: 'CountOn could not complete this tool request.', UNKNOWN: 'The tool request could not be completed.',
} as const;
export type McpErrorCode = keyof typeof errorMessages;
export interface McpMeta { transport: 'streamable-http'; initialized: boolean; toolsDiscovered: boolean; tool?: ToolName; durationMs: number; requestId?: string; steps?: McpMeta[] }
export interface McpTool { name: string; description?: string; inputSchema: Record<string, unknown>; outputSchema?: Record<string, unknown> }
export type McpResponse = { meta: McpMeta } & (
  { tools: McpTool[] } | { result: { structuredContent: Record<string, unknown> } } | { error: { code: McpErrorCode; message: string } }
);
