export type AlexaIntent = { kind: 'list' } | { kind: 'detail' | 'explain'; topic: string } | { kind: 'capture'; text: string } | { kind: 'clarify'; message: string };
export interface McpExpectation { id: string; claim: string; type: string; status: string; metric: string | null; created_at: string }
const normalize = (text: string) => text.toLowerCase().replace(/[’]/g, "'").replace(/[?.!]+$/g, '').trim();

// Routing chooses intent only. Bedrock compiles captures; no static capture payloads.
export function routeAlexaPrompt(text: string): AlexaIntent {
  const prompt = normalize(text);
  if (/^(what am i (counting on|tracking)|what are my expectations|what'?s being monitored|what is being monitored|show (me )?my expectations)$/.test(prompt)) return { kind: 'list' };
  const explain = prompt.match(/^why (?:did|has)\s+(?:my |the )?(.+?)\s+(?:fail|failed|not match)$/)
    ?? prompt.match(/^why (?:didn't|did not)\s+(?:my |the )?(.+?)\s+match$/)
    ?? prompt.match(/^why (?:was|is)\s+(?:my |the )?(.+?)\s+(?:higher|lower|different)$/);
  if (explain) {
    const topic = explain[1].replace(/\s+expectation$/, '');
    return { kind: 'explain', topic: /^(?:it|this|that)$/.test(topic) ? '' : topic };
  }
  const detail = prompt.match(/^(?:tell me about|check|what'?s happening with|what is happening with)\s+(?:my |the )?(.+)$/);
  if (detail) return { kind: 'detail', topic: detail[1].replace(/\s+expectation$/, '') };
  if (/^(?:i'm counting on|i am counting on|i expect|i'm expecting|save|monitor|track)\s/.test(prompt)) return { kind: 'capture', text: text.trim() };
  return { kind: 'clarify', message: 'Ask what you’re counting on, check an existing expectation, ask why it failed, or tell me one new expectation to monitor.' };
}
export function matchExpectations(topic: string, rows: McpExpectation[]): McpExpectation[] {
  const terms = normalize(topic).replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(word => word && !['my', 'the', 'a', 'an', 'expectation'].includes(word));
  if (!terms.length) return [];
  return rows.filter(row => {
    const searchable = `${row.claim} ${row.metric ?? ''}`.toLowerCase().replace(/_/g, ' ');
    return terms.every(term => searchable.includes(term));
  });
}
