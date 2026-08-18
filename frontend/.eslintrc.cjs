/* ESLint flat-config is deferred to Phase 6 polish; classic config keeps the
   scaffold lintable now without pulling extra plugins. */
module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-refresh'],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs'],
  rules: {
    // Underscore-prefixed args/vars are intentional placeholders (e.g. params a
    // later phase will use).
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    // Off by design: lib files (auth.tsx, inputs.tsx) colocate a provider/component
    // with its hooks/helpers. Fast-refresh HMR granularity is a dev-only trade-off.
    'react-refresh/only-export-components': 'off',
  },
};
