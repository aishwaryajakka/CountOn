# Local braces security patch

This private, MIT-licensed fork is based on the published `braces@3.0.3`
package. Its original source and copyright are retained in this directory.
It is used **only by the existing Next.js lint dependency chain** through the
root npm `overrides` entry; it is not a production browser dependency.

[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
reports stack exhaustion from deeply nested patterns and has no patched upstream
version as of 2026-10-12. Downgrading the Next lint configuration changes the
project's lint rules. This fork instead retains the original API and rules and
adds a fixed nesting boundary:

- The parser rejects nesting beyond 64 before recursive recovery can run.
- `compile`, `expand` and `stringify` iteratively validate AST depth and cycles
  before invoking recursive walkers, including caller-provided ASTs.
- Callers cannot disable the depth guard through options.
- An upstream debug print in `compile` is removed.

`ERR_BRACES_MAX_DEPTH` and `ERR_BRACES_INVALID_AST` are intentional safe failures
for excessive nesting or invalid graphs. Ordinary patterns retain their behavior.
The private package name/version identify this as a local fork, not an upstream
release. npm audit cannot assess these local modifications; regression tests
verify the guard itself and compare normal pattern behavior with fixtures.

Run `npm ci`, `npm run test`, `npm run lint`, and
`npm audit --audit-level=high` from `frontend/`. Tests resolve `braces` through
the actual installed `micromatch` dependency, so a broken override fails testing.
Third-party source is excluded from project style linting; it has dedicated tests.

When a reviewed upstream fix is published, replace this override with that
version, regenerate the lockfile, remove the fork, and rerun all frontend checks.
