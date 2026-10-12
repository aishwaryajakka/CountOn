'use strict';

// Fixed security boundary: options must never disable it.
const MAX_DEPTH = 64;
const checkDepth = depth => {
  if (depth > MAX_DEPTH) {
    const error = new RangeError('Brace AST exceeds the supported nesting depth');
    error.code = 'ERR_BRACES_MAX_DEPTH';
    throw error;
  }
};

// Public compile/expand/stringify also accept caller-supplied ASTs. Validate
// them iteratively before any upstream recursive walker executes.
const validateAst = ast => {
  const pending = [[ast, 0]];
  const seen = new Set();
  while (pending.length) {
    const [node, depth] = pending.pop();
    checkDepth(depth);
    if (!node || typeof node !== 'object') continue;
    if (seen.has(node)) {
      const error = new TypeError('Brace AST contains a repeated or cyclic node');
      error.code = 'ERR_BRACES_INVALID_AST';
      throw error;
    }
    seen.add(node);
    if (Array.isArray(node.nodes)) {
      for (const child of node.nodes) pending.push([child, depth + 1]);
    }
  }
};

module.exports = { checkDepth, validateAst };
