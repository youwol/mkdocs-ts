import {
    fromMarkdown,
    Router,
    Views,
    installCodeApiModule,
    installNotebookModule,
    Navigation,
} from '@youwol/mkdocs-ts'
import { setup } from '../auto-generated'
import { firstValueFrom } from 'rxjs'
import { example1 } from './js-plaground-examples'

const tableOfContent = Views.tocView

const project = {
    name: 'mkdocs-ts',
    docBasePath: `/api/assets-gateway/cdn-backend/resources/${setup.assetId}/${setup.version}/assets/api`,
}

const url = (restOfPath: string) =>
    `/api/assets-gateway/cdn-backend/resources/${setup.assetId}/${setup.version}/assets/${restOfPath}`

const placeholders = {
    '{{project}}': project.name,
    '{{mkdocs-version}}': setup.version,
    '{{URL-example1}}': `/applications/@youwol/js-playground/latest?content=${encodeURIComponent(example1)}`,
    '{{assetsBasePath}}': `/api/assets-gateway/raw/package/${setup.assetId}/${setup.version}/assets`,
}
function fromMd(file: string) {
    return fromMarkdown({
        url: url(file),
        placeholders,
    })
}
const CodeApiModule = await installCodeApiModule()
const NotebookModule = await installNotebookModule()
const notebookOptions = {
    runAtStart: true,
    defaultCellAttributes: {
        lineNumbers: false,
    },
    markdown: {
        latex: true,
        placeholders,
    },
}
await Promise.all([
    firstValueFrom(
        NotebookModule.SnippetEditorView.fetchCmDependencies$('javascript'),
    ),
    firstValueFrom(
        NotebookModule.SnippetEditorView.fetchCmDependencies$('python'),
    ),
])

export const navigation: Navigation = {
    name: 'Home',
    tableOfContent,
    decoration: {
        icon: {
            tag: 'i',
            class: 'fas fa-home me-1',
        },
    },
    html: fromMd('index.md'),
    '/how-to': {
        name: 'How to',
        decoration: {
            icon: {
                tag: 'i',
                class: 'fas fa-question-circle me-1',
            },
        },
        tableOfContent,
        html: fromMd('how-to.md'),
        '/install': {
            name: 'Install',
            tableOfContent,
            html: fromMd('how-to.install.md'),
        },
        '/api-backend': {
            name: 'Code API backends',
            tableOfContent,
            html: fromMd('how-to.api-backend.md'),
        },
    },
    '/tutorials': {
        name: 'Tutorials',
        decoration: {
            icon: {
                tag: 'i',
                class: 'fas fa-graduation-cap me-1',
            },
        },
        tableOfContent,
        html: fromMd('tutorials.md'),
        '/basics': {
            name: 'Getting started',
            tableOfContent,
            html: ({ router }) =>
                new NotebookModule.NotebookPage({
                    url: url('tutorials.basics.md'),
                    router,
                    options: notebookOptions,
                }),
        },
        '/markdown': {
            name: 'Markdown',
            tableOfContent,
            html: ({ router }) =>
                new NotebookModule.NotebookPage({
                    url: url('tutorials.markdown.md'),
                    router,
                    options: notebookOptions,
                }),
        },
        '/code-api': {
            name: 'Code API',
            tableOfContent,
            html: fromMd('tutorials.code-api.md'),
        },
        '/notebook': {
            name: 'Notebook',
            tableOfContent,
            html: ({ router }) =>
                new NotebookModule.NotebookPage({
                    url: url('tutorials.notebook.md'),
                    router,
                    options: notebookOptions,
                }),
            '/import': {
                name: 'Import',
                tableOfContent,
                html: ({ router }) =>
                    new NotebookModule.NotebookPage({
                        url: url('tutorials.notebook.import.md'),
                        router,
                        options: notebookOptions,
                    }),
            },
            '/scope': {
                name: 'Scope & Mutations',
                tableOfContent,
                html: ({ router }) =>
                    new NotebookModule.NotebookPage({
                        url: url('tutorials.notebook.scope.md'),
                        router,
                        options: notebookOptions,
                    }),
            },
            '/python': {
                name: 'Python',
                tableOfContent,
                html: ({ router }) =>
                    new NotebookModule.NotebookPage({
                        url: url('tutorials.notebook.python.md'),
                        router,
                        options: notebookOptions,
                    }),
                '/matplotlib': {
                    name: 'Matplotlib',
                    tableOfContent,
                    html: ({ router }) =>
                        new NotebookModule.NotebookPage({
                            url: url('tutorials.notebook.python.matplotlib.md'),
                            router,
                            options: notebookOptions,
                        }),
                },
            },
            '/workers': {
                name: "Workers' Pool",
                tableOfContent,
                html: ({ router }) =>
                    new NotebookModule.NotebookPage({
                        url: url('tutorials.notebook.workers.md'),
                        router,
                        options: notebookOptions,
                    }),
            },
            '/interpreter': {
                name: 'Interpreter',
                tableOfContent,
                html: ({ router }) =>
                    new NotebookModule.NotebookPage({
                        url: url('tutorials.notebook.interpreter.md'),
                        router,
                        options: notebookOptions,
                    }),
            },
            '/import-utils': {
                name: 'Import Utilities',
                tableOfContent,
                html: ({ router }) =>
                    new NotebookModule.NotebookPage({
                        url: url('tutorials.notebook.import-utils.md'),
                        router,
                        options: notebookOptions,
                    }),
            },
        },
    },
    '/api': {
        name: 'API',
        decoration: {
            icon: {
                tag: 'i',
                class: 'fas fa-code me-1',
            },
        },
        html: fromMd('api.md'),
        tableOfContent,
        '...': ({ path, router }: { path: string; router: Router }) =>
            CodeApiModule.docNavigation({
                modulePath: path,
                router,
                project,
                configuration: {
                    ...CodeApiModule.configurationTsTypedoc,
                    notebook: true,
                },
            }),
    },
}
