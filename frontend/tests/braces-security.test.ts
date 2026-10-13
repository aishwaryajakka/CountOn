import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import fixtures from './braces-compatibility.json';

type Ast = { type: string; nodes: Ast[]; value?: string };
type Options = Record<string, unknown>;
type Method = (input: string | Ast, options?: Options) => unknown;
type Braces = ((input: string | string[], options?: Options) => unknown) & {
  parse: Method; compile: Method; expand: Method; stringify: Method;
};
// Resolve from the actual lint dependency, not directly from the vendor folder.
const require = createRequire(import.meta.url);
const transitive = createRequire(require.resolve('micromatch'));
const braces = transitive('braces') as Braces;

it('installs the reviewed local fork for the real lint dependency', () => {
  expect(transitive('braces/package.json').name).toBe('@counton/braces');
});

it.each(fixtures)('preserves upstream behavior for $pattern', fixture => {
  expect(braces.compile(fixture.pattern)).toEqual(fixture.compile);
  expect(braces.expand(fixture.pattern)).toEqual(fixture.expand);
  expect(braces.stringify(fixture.pattern)).toEqual(fixture.stringify);
});

for (const method of ['parse', 'compile', 'expand', 'stringify'] as const) {
  it(`${method} rejects the below-length-limit stack exhaustion pattern before recursion`, () => {
    const pattern = '{'.repeat(4999) + 'x' + '}'.repeat(4999);
    expect(pattern.length).toBeLessThan(10000);
    expect(() => braces[method](pattern, { maxLength: 65536, maxDepth: Infinity }))
      .toThrowError(expect.objectContaining({ code: 'ERR_BRACES_MAX_DEPTH' }));
  });
}

for (const method of ['compile', 'expand', 'stringify'] as const) {
  it(`${method} guards supplied deep ASTs rather than only strings`, () => {
    const ast: Ast = { type: 'root', nodes: [] };
    let node = ast;
    for (let depth = 0; depth < 4000; depth++) {
      const child: Ast = { type: 'brace', nodes: [] }; node.nodes.push(child); node = child;
    }
    expect(() => braces[method](ast))
      .toThrowError(expect.objectContaining({ code: 'ERR_BRACES_MAX_DEPTH' }));
  });
  it(`${method} rejects cyclic supplied ASTs without recursive traversal`, () => {
    const ast: Ast = { type: 'root', nodes: [] }; ast.nodes.push(ast);
    expect(() => braces[method](ast))
      .toThrowError(expect.objectContaining({ code: 'ERR_BRACES_INVALID_AST' }));
  });
}

it('bounds parentheses nesting and array-form inputs too', () => {
  expect(() => braces.compile('('.repeat(4000) + 'x' + ')'.repeat(4000)))
    .toThrowError(expect.objectContaining({ code: 'ERR_BRACES_MAX_DEPTH' }));
  expect(() => braces(['{a,b}', '{'.repeat(4999) + 'x' + '}'.repeat(4999)]))
    .toThrowError(expect.objectContaining({ code: 'ERR_BRACES_MAX_DEPTH' }));
});

it('preserves escaped literal braces and upstream range limits', () => {
  expect(braces.compile('\\{'.repeat(1000))).toBe('{'.repeat(1000));
  expect(() => braces.expand('{1..100}', { rangeLimit: 10 })).toThrow('range limit');
});
