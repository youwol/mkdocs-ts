/* eslint-env node -- eslint-comment add exception because the running context is node environment */
module.exports = {
    entryPoints: [
        './src/index.ts',
        './src/lib/code-api/index.ts',
        './src/lib/notebook/index.ts',
        './src/backends/index.ts',
    ],
    exclude: ['src/tests'],
    out: 'dist/docs',
    theme: 'default',
    categorizeByGroup: false,
    categoryOrder: [
        'Getting Started',
        'Entry Point',
        'State',
        'View',
        'HTTP',
        'Error',
        '*',
    ],
}
