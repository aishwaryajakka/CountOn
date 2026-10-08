import type { ExpectationCreate } from './types';
import { actionSchema } from './mcp/contracts';

export type AlexaIntent = { kind: 'list' } | { kind: 'detail'; topic: string } | { kind: 'capture'; payload: ExpectationCreate } | { kind: 'clarify'; message: string };
export interface McpExpectation { id: string; claim: string; type: string; status: string; metric: string | null; created_at: string }
const normalize = (text: string) => text.toLowerCase().replace(/[’]/g, "'").replace(/[?.!]+$/g, '').trim();

// A narrow, replaceable demo compiler. Unsupported conditions need clarification.
export function routeAlexaPrompt(text: string, now = new Date()): AlexaIntent {
  const prompt = normalize(text);
  if (/^(what am i (counting on|tracking)|what are my expectations|what'?s being monitored|what is being monitored|show (me )?my expectations)$/.test(prompt)) return { kind: 'list' };
  const detail = prompt.match(/^(?:tell me about|check|what'?s happening with|what is happening with)\s+(?:my |the )?(.+)$/);
  if (detail) return { kind: 'detail', topic: detail[1].replace(/\s+expectation$/, '') };
  const grocery = prompt.match(/^(?:i'm counting on|i am counting on|i expect) my grocer(?:y|ies) (?:bill|spending) (?:staying|to stay|being|to be) under \$(\d+(?:\.\d{1,2})?) this week$/);
  if (grocery && Number(grocery[1]) > 0 && Number.isFinite(Number(grocery[1]))) {
    const end = new Date(now);
    end.setDate(end.getDate() + (7 - end.getDay()) % 7);
    end.setHours(23, 59, 59, 999);
    const payload: ExpectationCreate = { claim: text.trim(), type: 'numeric_comparison', metric: 'total_cost', comparison: 'less_than', target_value: Number(grocery[1]), deadline: end.toISOString(), evidence_sources: [], materiality_threshold: 0 };
    const validated = actionSchema.safeParse({ action: 'call_tool', tool: 'capture_expectation', arguments: { request: payload } });
    if (validated.success) return { kind: 'capture', payload };
  }
  return { kind: 'clarify', message: "I can list your expectations, check an existing one, or save a grocery bill limit in USD for this week. For example: “I'm counting on my grocery bill staying under $120 this week.” What would you like to do?" };
}
export function matchExpectations(topic: string, rows: McpExpectation[]): McpExpectation[] {
  const terms = normalize(topic).replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(word => word && !['my', 'the', 'a', 'an', 'expectation'].includes(word));
  if (!terms.length) return [];
  return rows.filter(row => {
    const searchable = `${row.claim} ${row.metric ?? ''}`.toLowerCase().replace(/_/g, ' ');
    return terms.every(term => searchable.includes(term));
  });
}
