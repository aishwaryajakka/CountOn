import { defineConfig, globalIgnores } from 'eslint/config';
import { fixupConfigRules } from '@eslint/compat';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTypescript from 'eslint-config-next/typescript';
// Next's React plugin still uses context methods removed in ESLint 10.
export default defineConfig([...fixupConfigRules([...nextVitals, ...nextTypescript]), globalIgnores(['.next/**', 'next-env.d.ts', 'test-results/**', 'playwright-report/**'])]);
