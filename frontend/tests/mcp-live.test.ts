// @vitest-environment node
import { expect, it } from 'vitest';
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
  const listed = await invoke({ action: 'call_tool', tool: 'list_expectations', arguments: { request: { limit: 50, offset: 0 } } });
  const rows = listed.result.structuredContent.expectations;
  expect(Array.isArray(rows)).toBe(true);
  if (rows.length) await invoke({ action: 'call_tool', tool: 'get_expectation', arguments: { request: { expectation_id: rows[0].id } } });
}, 90_000);
