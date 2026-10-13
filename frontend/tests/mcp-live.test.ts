// @vitest-environment node
import { expect, it } from 'vitest';
import { POST as converse } from '@/app/api/agent/route';
import { POST } from '@/app/api/mcp/route';

const endpoint = process.env.COUNTON_MCP_URL;
const token = process.env.COUNTON_MCP_TEST_ACCESS_TOKEN;
it.skipIf(!endpoint || !token)('live initialize → tools/list → tools/call using the actual MCP SDK (read-only)', async () => {
  const invoke = async (body: unknown) => {
    const response = await POST(new Request('http://localhost/api/mcp', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }));
    const result = await response.json();
    // Never print response data or tokens on failure.
    expect(response.status, result.error?.code ?? 'MCP request status').toBe(200);
    expect(result.meta.initialized).toBe(true); expect(result.meta.toolsDiscovered).toBe(true);
    expect(JSON.stringify(result).includes(token!)).toBe(false);
    return result;
  };
  const discovered = await invoke({ action: 'list_tools' });
  expect(discovered.tools.map((tool: { name: string }) => tool.name)).toEqual(expect.arrayContaining(['capture_expectation', 'get_expectation', 'list_expectations']));
  const response = await converse(new Request('http://localhost/api/agent', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ text: 'What am I counting on?', session_reference: null }) }));
  expect(response.status).toBe(200);
  const listed = await response.json();
  expect(listed.status).toBe('SUCCESS'); expect(Array.isArray(listed.rows)).toBe(true);
  expect(JSON.stringify(listed).includes(token!)).toBe(false);
}, 90_000);
