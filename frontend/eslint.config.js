import js from '@eslint/js'
import globals from 'globals'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    // jsx-a11y's recommended set is the mechanical half of P-WCAG: it catches
    // the defects axe cannot see statically (a click on a div with no key
    // handler, an aria-* attribute a role does not allow). axe over the rendered
    // tree is the other half, in the a11y tests.
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      jsxA11y.flatConfigs.recommended,
    ],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      'no-console': 'error',
      'no-alert': 'error',
      // P-EXPLICIT: an empty block is a swallowed branch. A `catch` that means
      // "the default applies" says so in a comment, which no-empty allows.
      'no-empty': 'error',
      // P-KISS: the catalogue's number. A function that needs more than twenty
      // branches is doing several jobs; the count is a prompt to look, and the
      // fix is to split it, not to raise the number.
      complexity: ['error', 20],
    },
  },
  {
    files: ['src/lib/logger.ts'],
    rules: {
      'no-console': 'off',
    },
  },
)
