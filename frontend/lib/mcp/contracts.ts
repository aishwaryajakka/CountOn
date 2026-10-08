import { z } from 'zod';

export const toolNames = ['capture_expectation', 'get_expectation', 'list_expectations'] as const;
export type ToolName = typeof toolNames[number];
const expectationType = z.enum(['numeric_comparison', 'boolean', 'temporal', 'event']);
const status = z.enum(['monitoring', 'fulfilled', 'contradicted', 'unknown', 'resolved', 'cancelled']);
const capture = z.strictObject({
  claim: z.string().trim().min(1), type: expectationType,
  metric: z.string().trim().min(1).max(100).nullable().optional(),
  comparison: z.enum(['less_than', 'less_than_or_equal', 'greater_than', 'greater_than_or_equal', 'equal', 'not_equal']).nullable().optional(),
  baseline: z.number().nullable().optional(), target_value: z.number().nullable().optional(),
  deadline: z.iso.datetime({ offset: true }).nullable().optional(),
  evidence_sources: z.array(z.string()).optional(), materiality_threshold: z.number().min(0).max(1).optional(),
});
const list = z.strictObject({ limit: z.number().int().min(1).max(100).optional(), offset: z.number().int().min(0).optional(), status: status.nullable().optional(), type: expectationType.nullable().optional() });
const get = z.strictObject({ expectation_id: z.uuid() });
export const actionSchema = z.union([
  z.strictObject({ action: z.literal('list_tools') }),
  ...toolNames.map(tool => z.strictObject({ action: z.literal('call_tool'), tool: z.literal(tool), arguments: z.strictObject({ request: tool === 'capture_expectation' ? capture : tool === 'get_expectation' ? get : list }) })),
]);
export type McpAction = z.infer<typeof actionSchema>;
export const errorMessages = {
  AUTH_REQUIRED: 'Sign in to use CountOn tools.', AUTH_EXPIRED: 'Your session was rejected. Sign in again.',
  MCP_UNAVAILABLE: 'CountOn tools are temporarily unavailable. Try again later.',
  MCP_PROTOCOL_ERROR: 'CountOn tools returned an unexpected response. Try again later.',
  TOOL_NOT_FOUND: 'This tool is not available.', TOOL_VALIDATION_ERROR: 'Check the structured tool inputs and try again.',
  TOOL_EXECUTION_ERROR: 'CountOn could not complete this tool request.', UNKNOWN: 'The tool request could not be completed.',
} as const;
export type McpErrorCode = keyof typeof errorMessages;
export interface McpMeta { transport: 'streamable-http'; initialized: boolean; toolsDiscovered: boolean; tool?: ToolName; durationMs: number }
export interface McpTool { name: string; description?: string; inputSchema: Record<string, unknown>; outputSchema?: Record<string, unknown> }
export type McpResponse = { meta: McpMeta } & (
  { tools: McpTool[] } | { result: { structuredContent: Record<string, unknown> } } | { error: { code: McpErrorCode; message: string } }
);
