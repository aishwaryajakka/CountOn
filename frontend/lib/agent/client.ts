import { agentResponseSchema, agentErrors, type AgentInput, type AgentResponse, type AgentErrorCode } from './contracts';
export class AgentClientError extends Error {
  constructor(public code: AgentErrorCode) { super(agentErrors[code]); }
}
export async function requestAgent(token: string | undefined, input: AgentInput): Promise<AgentResponse> {
  if (!token) throw new AgentClientError('AUTH_REQUIRED');
  let response: Response;
  try { response = await fetch('/api/agent', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(input), cache: 'no-store' }); }
  catch { throw new AgentClientError('UNAVAILABLE'); }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const code = response.status === 401 ? 'AUTH_EXPIRED' : response.status >= 500 ? 'UNAVAILABLE' : 'INVALID_REQUEST';
    throw new AgentClientError(code);
  }
  const parsed = agentResponseSchema.safeParse(body);
  if (!parsed.success) throw new AgentClientError('INVALID_RESPONSE');
  return parsed.data;
}
