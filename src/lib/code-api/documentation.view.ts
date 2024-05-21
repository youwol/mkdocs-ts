import { ChildrenLike, VirtualDOM } from '@youwol/rx-vdom'
import { parseMd } from '../index'
import type { Router } from '../index'
import { Configuration } from './configurations'
import { Documentation, DocumentationSection } from './models'
import { NotebookTypes, installNotebookModule } from '../../index'
import { from } from 'rxjs'

export class DocumentationView implements VirtualDOM<'div'> {
    public readonly documentation?: Documentation
    public readonly router: Router
    public readonly configuration: Configuration
    public readonly tag = 'div'
    public readonly clas = 'mkapi-doc'
    public readonly children: ChildrenLike
    constructor(params: {
        documentation: Documentation
        router: Router
        configuration: Configuration
    }) {
        Object.assign(this, params)

        this.children = this.documentation.sections.map((section) => {
            return new SectionView({
                section,
                router: this.router,
                configuration: this.configuration,
            })
        })
    }
}

export class SectionView implements VirtualDOM<'div'> {
    public readonly tag = 'div'
    public readonly children: ChildrenLike = []
    public readonly class = 'mkapi-section'

    constructor({
        section,
        router,
        configuration,
    }: {
        section: DocumentationSection
        router: Router
        configuration: Configuration
    }) {
        if (!section) {
            return
        }
        const redirect = (
            link: HTMLAnchorElement,
            target: string,
            i: number,
        ) => {
            const href = link.href.split(target)[1]
            let path =
                i == 0
                    ? `/references/${href.split('.').join('/')}`
                    : `/references/${href.split('.').slice(0, -i).join('/')}.${
                          href.split('.').slice(-i)[0]
                      }.${href.split('.').slice(-i)[1]}`
            if (i > 2) {
                path += `.${href.split('.').slice(-2)[1]}`
            }
            router.navigateTo({ path })
        }
        const navigations = {
            'yw-nav-mod': (link: HTMLAnchorElement) =>
                redirect(link, '@yw-nav-mod:', 0),
            'yw-nav-class': (link: HTMLAnchorElement) =>
                redirect(link, '@yw-nav-class:', 2),
            'yw-nav-func': (link: HTMLAnchorElement) =>
                redirect(link, '@yw-nav-func:', 2),
            'yw-nav-attr': (link: HTMLAnchorElement) =>
                redirect(link, '@yw-nav-attr:', 3),
            'yw-nav-glob': (link: HTMLAnchorElement) =>
                redirect(link, '@yw-nav-glob:', 2),
            'yw-nav-meth': (link: HTMLAnchorElement) =>
                redirect(link, '@yw-nav-meth:', 3),
        }

        this.children = [
            section.title && new SectionHeader(section),
            configuration.notebook
                ? {
                      source$: from(installNotebookModule()),
                      vdomMap: (mdle: typeof NotebookTypes) => {
                          return new mdle.NotebookPage({
                              src: section.content,
                              router,
                              options: { runAtStart: true },
                          })
                      },
                  }
                : parseMd({
                      src: section.content,
                      router: router,
                      navigations,
                  }),
        ]
    }
}

export class SectionHeader implements VirtualDOM<'div'> {
    public readonly tag = 'div'
    public readonly children: ChildrenLike
    public readonly class =
        'mkapi-section-header w-100 p-2 my-3 d-flex align-items-center text-dark border-bottom'

    constructor(section: DocumentationSection) {
        const factory = {
            warning: 'fas fa-exclamation fv-text-focus',
            example: 'fas fa-code fv-text-success',
            todos: 'fas fa-forward fv-text-success',
        }
        this.children = [
            {
                tag: 'div',
                class:
                    factory[section.semantic.role] ||
                    'fas fa-info fv-text-success',
            },
            { tag: 'div', class: 'mx-2' },
            {
                tag: 'div',
                innerText: section.title,
            },
        ]
    }
}
