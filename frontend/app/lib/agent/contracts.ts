import { z } from 'zod';
import { toolNames } from '@/lib/mcp/contracts';
export const actions = ['LIST_EXPECTATIONS', 'GET_EXPECTATION', 'COMPILE_EXPECTATION', 'CONTINUE_CLARIFICATION', 'CAPTURE_EXPECTATION', 'EXPLAIN_MISMATCH', 'CANCEL', 'UNKNOWN'] as const;
export const agentInputSchema = z.strictObject({ text: z.string().trim().min(1).max(2000), session_reference: z.string().regex(/^[A-Za-z0-9_-]{43}$/).nullable() });
export type AgentInput = z.infer<typeof agentInputSchema>;
const row = z.strictObject({ id: z.uuid(), claim: z.string().max(4000), type: z.enum(['numeric_comparison', 'boolean', 'temporal', 'event']), status: z.enum(['monitoring', 'fulfilled', 'contradicted', 'unknown', 'resolved', 'cancelled']), metric: z.string().nullable(), created_at: z.iso.datetime({ offset: true }) });
const trace = z.union([
  z.strictObject({ layer: z.literal('Agent'), label: z.enum(actions) }),
  z.strictObject({ layer: z.literal('MCP'), label: z.enum(toolNames) }),
  z.strictObject({ layer: z.literal('Bedrock'), label: z.enum(['compiled', 'clarification', 'grounded explanation', 'interpretation']) }),
  z.strictObject({ layer: z.literal('CountOn'), label: z.literal('grounded fallback') }),
]);
export const provenanceSchema = z.strictObject({
  run_id: z.uuid(), expectation_label: z.string().max(120).nullable(),
  evaluator_result: z.enum(['MATCH', 'UNKNOWN', 'MISMATCH']).nullable(),
  sources_used: z.array(z.enum(['Utility', 'Billing', 'Delivery', 'Ring', 'Calendar', 'Outlook', 'Bee', 'Declared source'])).max(8),
  evidence_count: z.number().int().min(0).max(12), bedrock_used: z.boolean(),
  fallback_used: z.boolean(), grounded: z.boolean(),
});
export const agentResponseSchema = z.strictObject({ action: z.enum(actions), status: z.enum(['SUCCESS', 'CLARIFICATION', 'CANCELLED', 'UNSUPPORTED', 'REJECTED', 'FAILED', 'DISAMBIGUATION_REQUIRED']), answer: z.string().min(1).max(4000), code: z.string().max(80).nullable(), session_reference: z.string().regex(/^[A-Za-z0-9_-]{43}$/).nullable(), captured: z.boolean(), clarification_required: z.boolean(), rows: z.array(row).max(100), saved_id: z.uuid().nullable(), traces: z.array(trace).max(25), provenance: provenanceSchema.optional() }).superRefine((value, context) => {
  if (value.captured && (!value.saved_id || !value.rows.some(row => row.id === value.saved_id))) context.addIssue({ code: 'custom', message: 'Missing captured record' });
});
export type AgentResponse = z.infer<typeof agentResponseSchema>;
export const agentErrors = {
  AUTH_REQUIRED: 'Sign in to talk with CountOn.', AUTH_EXPIRED: 'Your CountOn session expired. Please sign in again.',
  UNAVAILABLE: "CountOn can't reach its tools right now. Check CountOn before retrying a save.",
  INVALID_REQUEST: 'Please restate your request.', INVALID_RESPONSE: "I couldn't read that response safely. Check CountOn before retrying a save.",
} as const;
export type AgentErrorCode = keyof typeof agentErrors;
