"""
The python backend module to produce API files from python modules.

"""

import dataclasses
import functools
import json
import pprint
import re
from collections import defaultdict
from pathlib import Path, PosixPath
from typing import Any, Literal, NamedTuple, Sequence, cast

import griffe
from griffe.dataclasses import Alias as AstAlias
from griffe.dataclasses import Attribute as AstAttribute
from griffe.dataclasses import Class as AstClass
from griffe.dataclasses import Docstring as AstDocstring
from griffe.dataclasses import Function as AstFunction
from griffe.dataclasses import Module as AstModule
from griffe.docstrings.dataclasses import (DocstringSection,
                                           DocstringSectionAdmonition,
                                           DocstringSectionParameters,
                                           DocstringSectionReturns,
                                           DocstringSectionText)
from griffe.enumerations import Kind
from griffe.exceptions import AliasResolutionError
from griffe.expressions import ExprName

from mkdocs_py_griffe.models import (Attribute, Callable, ChildModule, Code,
                                     Documentation, DocumentationSection, File,
                                     Module, Semantic, Type)

INIT_FILENAME = "__init__.py"
"""
The '__init__.py' filename to recognize module.
"""


class Configuration(NamedTuple):
    """
    Represents the configuration to generate API files using
    :func:`mkdocs_py_griffe.py_griffe.generate_api`.
    """

    base_nav: str
    """
    The base URL for the navigation.
    """
    out: Path
    """
    Path of the output folder in which API files are generated.
    """
    external_links: dict[str, str] = {}
    """
    External links to cross-reference, e.g.:
    ```
    {   
        "float": "https://docs.python.org/fr/3/library/stdtypes.html#numeric-types-int-float-complex",
        "list": "https://docs.python.org/3/library/stdtypes.html#lists",
        "dict": "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict",
    }
    ```
    The function :func:`mkdocs_py_griffe.std_links.std_links` is available, it includes common standard Python links.
    """


type SymbolKind = Literal[
    "function", "attribute", "class", "property", "method", "module"
]


class SymbolRef(NamedTuple):
    """
    Represents a reference of a symbol in the library.
    Initialized from the function :func:`mkdocs_py_griffe.py_griffe.init_symbols`.
    """

    kind: SymbolKind
    """
    Kind of the symbol.
    """
    navigation_path: str
    """
    Navigation path.
    """


class Project(NamedTuple):
    """
    Represents the project, holding global symbols.
    """

    config: Configuration
    """
    The configuration.
    """
    root_ast: AstModule
    """
    The root AST from griffe of the documented module.
    """
    all_symbols: dict[str, SymbolRef]
    """
    The list of all symbols defined in the documented module.
    """
    all_aliases: dict[str, str]
    """
    The list of aliases defined in the documented module (from the library).
    """


NO_SEMANTIC = Semantic(role="", labels=[], attributes={}, relations={})
"""
No semantic.
"""

MODULE_SEMANTIC = Semantic(role="module", labels=[], attributes={}, relations={})
"""
Semantic for global variables.
"""

GLOBAL_SEMANTIC = Semantic(role="global", labels=[], attributes={}, relations={})
"""
Semantic for global variables.
"""

FUNCTION_GLOBAL_SEMANTIC = Semantic(
    role="function", labels=[], attributes={}, relations={}
)
"""
Semantic for globals functions.
"""

CLASS_SEMANTIC = Semantic(role="class", labels=[], attributes={}, relations={})
"""
Semantic for class's attributes.
"""

ATTR_SEMANTIC = Semantic(role="attribute", labels=[], attributes={}, relations={})
"""
Semantic for class's attributes.
"""

METHOD_SEMANTIC = Semantic(role="method", labels=[], attributes={}, relations={})
"""
Semantic for class's method.
"""

SphinxCrossLinkTag = Literal["mod", "class", "func", "attr", "meth", "glob"]
"""
Type of supported tags for sphinx like cross links.
"""

SUPPORTED_CROSS_LINK_TAGS: set[SphinxCrossLinkTag] = {
    "mod",
    "class",
    "func",
    "attr",
    "meth",
    "glob",
}
"""
The supported tags for sphinx like cross links.

*E.g.*:
```
*  :tag:`symbol`
*  :tag:`a custom text <symbol>`
*  :tag:`a custom text <foo.bar.symbol>`
```
"""


class DocReporter:
    errors: dict[str, set[str]] = defaultdict(set)
    external_cross_ref_errors: set[str] = set()
    internal_cross_ref_errors: set[str] = set()
    no_docstrings_errors: set[str] = set()
    sphinx_tag_unknown: set[str] = set()
    sphinx_links_unresolved: dict[str, list[str]] = {}

    @staticmethod
    def add_error(symbol_path: str, description: str):
        DocReporter.errors[symbol_path].add(description)

    @staticmethod
    def add_external_cross_ref_error(symbol_path: str):
        DocReporter.external_cross_ref_errors.add(symbol_path)

    @staticmethod
    def add_internal_cross_ref_error(symbol_path: str):
        DocReporter.internal_cross_ref_errors.add(symbol_path)

    @staticmethod
    def add_no_docstring(symbol_path: str):
        DocReporter.no_docstrings_errors.add(symbol_path)

    @staticmethod
    def add_sphinx_tag_unknown(parent: str, tag: str):
        DocReporter.sphinx_tag_unknown.add(f"[{parent}] => `{tag}` unknown")

    @staticmethod
    def add_sphinx_link_unresolved(parent: str, link: str, candidates: list[str]):
        DocReporter.sphinx_links_unresolved[f"{parent}=>{link}"] = candidates


def canonical_path(
    ast: AstModule | AstAttribute | AstClass | AstFunction | ExprName,
    project: Project,
):
    return ast.canonical_path.replace(f"{project.root_ast.name}.", "")


def navigation_path(
    ast: AstModule | AstAttribute | AstClass | AstFunction | ExprName, project: Project
) -> str | None:

    def lib_nav_path(path: str):
        base = path.replace(f"{project.root_ast.name}.", "")
        symbol = project.all_symbols.get(base, None)
        if symbol:
            return symbol.navigation_path
        alias = project.all_aliases.get(path, None)
        if alias:
            return lib_nav_path(alias)
        return None

    py_path = ast.canonical_path

    if py_path.startswith(project.root_ast.name):
        nav_path = lib_nav_path(path=ast.canonical_path)
        if not nav_path:
            DocReporter.add_internal_cross_ref_error(ast.canonical_path)
            return None
        return f"@nav{project.config.base_nav}/{nav_path}"
    if py_path in project.config.external_links:
        return project.config.external_links[py_path]

    DocReporter.add_external_cross_ref_error(py_path)
    return None


class ModuleElements(NamedTuple):
    modules: list[AstModule]
    files: list[AstModule]
    classes: list[AstClass]
    functions: list[AstFunction]
    attributes: list[AstAttribute]


def extract_module(ast: AstModule) -> ModuleElements:

    no_alias = {
        k: v
        for k, v in ast.modules.items()
        if not isinstance(v, griffe.dataclasses.Alias)
    }

    modules = [
        v
        for k, v in no_alias.items()
        if isinstance(v.filepath, PosixPath)
        and v.filepath.name == INIT_FILENAME
        and v.docstring
    ]

    files = [v for k, v in no_alias.items() if k not in modules]
    classes = [
        c
        for v in files
        for c in v.classes.values()
        if isinstance(c, AstClass) and c.docstring
    ]
    functions = [
        f
        for v in files
        for f in v.functions.values()
        if isinstance(f, AstFunction) and f.docstring
    ]
    attributes = [
        a
        for v in files
        for a in v.attributes.values()
        if isinstance(a, AstAttribute) and a.docstring
    ]
    return ModuleElements(
        modules=modules,
        files=files,
        classes=classes,
        functions=functions,
        attributes=attributes,
    )


def is_leaf_module(path: str, project: Project) -> bool:
    module_doc: AstModule = functools.reduce(
        lambda acc, e: acc.modules[e] if e else acc,
        path.split(".")[1:],
        project.root_ast,
    )

    no_alias = {
        k: v for k, v in module_doc.modules.items() if not isinstance(v, AstAlias)
    }
    children = [
        k
        for k, v in no_alias.items()
        if isinstance(v.filepath, PosixPath)
        and v.filepath.name == INIT_FILENAME
        and v.docstring
    ]
    return len(children) == 0


def parse_module(ast: AstModule, project: Project) -> Module:
    """
    Transforms module documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's module documentation.
        project: Project description.

    Returns:
        The parsed model.
    """
    elements = extract_module(ast=ast)
    children_modules = [
        parse_child_module(ast=m, project=project) for m in elements.modules
    ]
    classes = [
        parse_class(ast=c, project=project) for c in elements.classes if c.has_docstring
    ]
    functions = [
        parse_function(ast=f, semantic=FUNCTION_GLOBAL_SEMANTIC, project=project)
        for f in elements.functions
        if f.has_docstring
    ]
    attributes = [
        parse_attribute(ast=a, semantic=GLOBAL_SEMANTIC, project=project)
        for a in elements.attributes
    ]
    files = [format_file_doc(ast=f, project=project) for f in elements.files]
    sections = get_docstring_sections(ast)

    return Module(
        name=ast.name,
        documentation=format_detailed_docstring(
            sections=sections, parent=ast, project=project
        ),
        semantic=MODULE_SEMANTIC,
        path=canonical_path(ast=ast, project=project),
        children=children_modules,
        attributes=sorted(attributes, key=lambda m: m.name),
        types=classes,
        callables=functions,
        files=files,
    )


def get_symbol_path(ast: AstClass | AstFunction | AstAttribute | AstModule) -> str:
    path = ast.name
    it = ast
    while it.parent:
        path = f"{it.parent.name}.{path}"
        it = it.parent

    return path


def parse_child_module(ast: AstModule, project: Project) -> ChildModule:
    """
    Transforms submodule documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's module documentation.
        project: Project description.

    Returns:
        The parsed model.
    """
    return ChildModule(
        name=ast.name,
        path=ast.canonical_path,
        isLeaf=is_leaf_module(path=ast.canonical_path, project=project),
    )


def format_file_doc(ast: AstModule, project: Project) -> File:
    """
    Transforms a file documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's module documentation.
        project: Project description.

    Returns:
        The parsed model.
    """
    return File(
        name=ast.name,
        path=str(ast.filepath.relative_to(project.root_ast.filepath.parent)),
        documentation=format_detailed_docstring(
            get_docstring_sections(ast), parent=ast, project=project
        ),
    )


def parse_function(ast: AstFunction, semantic: Semantic, project: Project) -> Callable:
    """
    Transforms a function's documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's function documentation.
        semantic: Target semantic
        project: Project description.

    Returns:
        The parsed model.
    """
    parsed = get_docstring_sections(ast)
    sections = [
        p
        for p in parsed
        if isinstance(p, DocstringSectionText)
        or (isinstance(p, DocstringSectionAdmonition) and p.title != "Return")
    ]
    formatted = format_detailed_docstring(sections, parent=ast, project=project)
    params_doc = parse_parameters(ast, project=project)
    returns_doc = parse_returns(ast, project=project)

    return Callable(
        name=ast.name,
        documentation=Documentation(
            sections=[s for s in [*formatted.sections, returns_doc, params_doc] if s]
        ),
        path=canonical_path(ast=ast, project=project),
        code=parse_code(ast=ast, project=project),
        semantic=semantic,
    )


def parse_class(ast: AstClass, project: Project) -> Type:
    """
    Transforms a class's documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's class documentation.
        project: Project description.

    Returns:
        The parsed model.
    """
    bases = find_attributes_of_type(ast.bases, ExprName)
    semantic = Semantic(
        role="class",
        labels=[],
        attributes={},
        relations={"inherits": [b.canonical_path for b in bases]},
    )
    return Type(
        name=ast.name,
        documentation=format_detailed_docstring(
            sections=get_docstring_sections(ast),
            parent=ast,
            project=project,
        ),
        path=canonical_path(ast=ast, project=project),
        semantic=semantic,
        attributes=[
            parse_attribute(ast=attr, semantic=ATTR_SEMANTIC, project=project)
            for attr in ast.attributes.values()
            if attr.docstring and not attr.inherited
        ],
        callables=[
            parse_function(ast=f, semantic=METHOD_SEMANTIC, project=project)
            for f in ast.functions.values()
            if f and f.docstring
        ],
        code=parse_code(ast, project=project),
    )


def parse_parameters(ast: AstFunction, project: Project) -> DocumentationSection | None:
    """
    Transforms a function's parameter documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's function documentation.
        project: Project description.

    Returns:
        The parsed model.
    """
    parsed = get_docstring_sections(ast)

    params = next(
        (p for p in parsed if isinstance(p, DocstringSectionParameters)), None
    )

    def format_param(e):
        with_links = replace_links(
            e.description, parent=ast.canonical_path, project=project
        )
        return f"*  **{e.name}**: {with_links}"

    if not params:
        return None

    content = functools.reduce(
        lambda acc, e: f"{acc}\n{format_param(e)}", params.value, ""
    )
    return DocumentationSection(
        title="Arguments",
        content=content,
        contentType="Markdown",
        semantic=Semantic(role="arguments", labels=[], attributes={}, relations={}),
    )


def parse_returns(ast: AstFunction, project: Project) -> DocumentationSection | None:
    """
    Transforms a function's returns documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's function documentation.
        project: Project description.

    Returns:
        The parsed model.
    """

    parsed = get_docstring_sections(ast)

    returns = next(
        (p for p in parsed if isinstance(p, DocstringSectionReturns)),
        None,
    )
    if returns:
        try:
            returns_doc = replace_links(
                returns.value[0].description,
                parent=ast.canonical_path,
                project=project,
            )
            return DocumentationSection(
                title="Returns",
                content=returns_doc,
                contentType="Markdown",
                semantic=Semantic(
                    role="returns", labels=[], attributes={}, relations={}
                ),
            )
        except Exception as e:
            DocReporter.add_error(
                ast.canonical_path,
                f"Failed to parse return of function {ast.name}: {e}",
            )

    return None


def get_docstring_sections(
    ast: AstClass | AstFunction | AstAttribute | AstModule,
):
    if not ast.docstring and not (
        isinstance(ast, AstModule) and ast.filepath.parts[-1] != "__init__.py"
    ):
        # This should not normally happen because only symbols with docstring are reported.
        # Except for files for which it is tolerated.
        DocReporter.add_no_docstring(get_symbol_path(ast))

    docstring_text = ast.docstring.value if ast.docstring else ""

    docstring = AstDocstring(
        docstring_text,
        parent=ast,
    )
    return docstring.parse("google")


def get_nav_path(tag: SUPPORTED_CROSS_LINK_TAGS, py_path: str):
    nav = ""
    if tag == "mod":
        nav = py_path.replace(".", "/")
    parts = py_path.split(".")
    if tag in ["class", "func", "glob"]:
        nav = "/".join(parts[0:-2]) + f".{parts[-2]}.{parts[-1]}"
    if tag in ["meth", "attr"]:
        nav = "/".join(parts[0:-3]) + f".{parts[-3]}.{parts[-2]}.{parts[-1]}"
    return nav


def replace_links(text: str, parent: str, project: Project) -> str:

    cross_ref_pattern = r":(\w+):`([^`]+)`"
    project_prefix = f"{project.root_ast.name}."

    def sanitize_py_path(py_path: str):
        if py_path.startswith(project_prefix):
            return py_path.replace(project_prefix, "")
        return py_path

    def get_cross_link_candidates(
        link_type: SphinxCrossLinkTag, short_link: str, all_symbols: list[str]
    ):
        short_link_sanitized = sanitize_py_path(short_link)
        parent_symbol = ".".join(short_link_sanitized.split(".")[0:-1])

        return (
            [s for s in all_symbols if s.endswith(short_link_sanitized)]
            if link_type in {"mod", "class", "func", "glob"}
            else [s for s in all_symbols if s.endswith(parent_symbol)]
        )

    def replace_function(match: re.Match):
        tag = match.group(1)  # Capture the tag (e.g., func, class, etc.)
        # Capture the value between the backticks
        # (e.g., 'module.foo' or 'custom text <module.foo>')
        content = match.group(2)
        py_path = content
        label = py_path.split(".")[-1]

        if tag not in SUPPORTED_CROSS_LINK_TAGS:
            DocReporter.add_sphinx_tag_unknown(parent, tag)
            return label

        pattern = r"<([^>]+)>"
        matches = re.findall(pattern, py_path)
        if matches:
            index_start = py_path.find("<")
            label = py_path[0:index_start]
            py_path = matches[0]

        py_path = sanitize_py_path(py_path)
        if project.all_symbols.get(py_path, None):
            nav_path = get_nav_path(tag=tag, py_path=py_path)
            return f"[{label}](@nav{project.config.base_nav}/{nav_path})"

        candidates = get_cross_link_candidates(
            link_type=tag,
            short_link=py_path,
            all_symbols=list(project.all_symbols.keys()),
        )

        DocReporter.add_sphinx_link_unresolved(parent, match.group(0), candidates)
        return label

    return re.sub(cross_ref_pattern, replace_function, text)


def format_detailed_docstring(
    sections: Sequence[DocstringSection],
    parent: AstFunction | AstClass | AstAttribute | AstModule,
    project: Project,
) -> Documentation:
    def admonition(v: DocstringSectionAdmonition) -> DocumentationSection:
        return DocumentationSection(
            content=replace_links(
                v.value.description, parent=parent.canonical_path, project=project
            ),
            contentType="Markdown",
            semantic=Semantic(
                role="admonition",
                labels=[],
                attributes={
                    "tag": (
                        v.value.annotation
                        if isinstance(v.value.annotation, str)
                        else None
                    )
                },
                relations={},
            ),
            title=v.title,
        )

    def text(v: DocstringSectionText) -> DocumentationSection:
        return DocumentationSection(
            content=replace_links(
                v.value, parent=parent.canonical_path, project=project
            ),
            contentType="Markdown",
            semantic=Semantic(role="text", labels=[], attributes={}, relations={}),
            title=v.title,
        )

    def factory(v: DocstringSection):
        if isinstance(v, DocstringSectionAdmonition):
            return admonition(v)
        if isinstance(v, DocstringSectionText):
            return text(v)
        return None

    formatted = [factory(s) for s in sections]
    return Documentation(sections=[s for s in formatted if s])


def parse_attribute(
    ast: AstAttribute, semantic: Semantic, project: Project
) -> Attribute:
    """
    Transforms an attribute's documentation as provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's module documentation.
        semantic: Target semantic.
        project: Project description.

    Returns:
        The parsed model.
    """
    sections = get_docstring_sections(ast)
    documentation = format_detailed_docstring(
        sections=sections, parent=ast, project=project
    )
    return Attribute(
        name=ast.name,
        semantic=semantic,
        documentation=documentation,
        path=canonical_path(ast=ast, project=project),
        code=parse_code(ast=ast, project=project),
    )


def extract_function_declaration(
    function_str,
):
    def_index = function_str.find("def")
    no_decorator = function_str[def_index:]
    close_parenthesis_index = no_decorator.find(")")
    remaining = no_decorator[close_parenthesis_index:]
    end_index = remaining.find(":")
    return function_str[0 : def_index + close_parenthesis_index + end_index]


def extract_class_declaration(class_str):
    index_doc_start = class_str.find('"""')
    return class_str[0:index_doc_start].rstrip()[0:-1]


def parse_code(ast: AstClass | AstFunction | AstAttribute, project: Project) -> Code:
    """
    Transforms a code's documentation from class, function or attribute provided by griffe to the mkdocs-ts models.

    Parameters:
        ast: Griffe's module documentation.
        project: Project description.

    Returns:
        The parsed model.
    """

    def nav_path(e: ExprName | AstClass | AstFunction):
        return navigation_path(ast=e, project=project)

    file_path = str(ast.filepath.relative_to(project.root_ast.filepath.parent))
    start_line = ast.lineno
    end_line = ast.endlineno
    references = {}
    implementation = ""
    declaration = ""
    if isinstance(ast, AstAttribute):
        types_annotation = find_attributes_of_type(ast.annotation, ExprName)
        types_value = find_attributes_of_type(ast.value, ExprName)
        declaration = functools.reduce(lambda acc, e: f"{acc}\n{e}", ast.lines)
        implementation = None
        references = {e.name: nav_path(e=e) for e in [*types_annotation, *types_value]}

    if isinstance(ast, AstFunction):
        types_annotation = find_attributes_of_type(ast.annotation, ExprName)
        returns_annotation = find_attributes_of_type(ast.returns, ExprName)
        parameters_annotation = find_attributes_of_type(ast.parameters, ExprName)
        all_annotations = [
            *types_annotation,
            *returns_annotation,
            *parameters_annotation,
        ]
        implementation = functools.reduce(lambda acc, e: f"{acc}\n{e}", ast.lines)
        declaration = extract_function_declaration(implementation)
        references = {
            **{e.name: nav_path(e=e) for e in all_annotations},
            ast.name: nav_path(e=ast),
        }

    if isinstance(ast, AstClass):
        decorators_annotation = find_attributes_of_type(ast.decorators, ExprName)
        bases_annotation = find_attributes_of_type(ast.bases, ExprName)
        all_annotations = [
            *decorators_annotation,
            *bases_annotation,
        ]
        implementation = functools.reduce(lambda acc, e: f"{acc}\n{e}", ast.lines)
        declaration = extract_class_declaration(implementation)
        references = {
            **{e.name: nav_path(e=e) for e in all_annotations},
            ast.name: nav_path(e=ast),
        }

    return Code(
        filePath=file_path,
        startLine=start_line,
        endLine=end_line,
        declaration=declaration,
        implementation=implementation,
        references=references,
    )


def find_attributes_of_type(ast: Any, target_type):
    results = []
    primitive_types = (int, float, str, bool, bytes, complex)

    def get_attr_val(obj, attr_name) -> Any | None:
        attr_value = getattr(obj, attr_name, None)
        invalid = any(
            [
                attr_name.startswith("__"),
                attr_name in ["parent"],
                not attr_value,
                isinstance(attr_value, primitive_types),
                isinstance(attr_value, AstModule),
            ]
        )
        return not invalid and attr_value

    def parse_obj(obj):
        attributes = [
            get_attr_val(obj, attr_name)
            for attr_name in dir(obj)
            if get_attr_val(obj, attr_name)
        ]
        for attr_value in attributes:
            if isinstance(attr_value, target_type):
                results.append(attr_value)
                continue
            recursive_search(attr_value)

    def recursive_search(current):

        if isinstance(current, target_type):
            results.append(current)

        if isinstance(current, list):
            for item in current:
                recursive_search(item)
        elif hasattr(current, "__dict__"):
            parse_obj(current)

    recursive_search(ast)
    return results


docs = {}


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "__dict__"):
            return dataclasses.asdict(o)
        if isinstance(o, (list, tuple)):
            return [self.default(item) for item in o]
        return json.JSONEncoder.default(self, o)


def init_symbols(root_ast: AstModule) -> dict[str, SymbolRef]:
    """
    Recursive look up for all the symbols within the provided AST.

    Parameters:
        root_ast: Root module's AST.

    Returns:
        A dictionary `canonical path` => :class:`mkdocs_py_griffe.py_griffe.SymbolRef`.
    """

    def get_canonical_path(p: str):
        return p.replace(f"{root_ast.name}.", "")

    def get_symbol(
        ast: AstClass | AstFunction | AstAttribute | AstModule, from_class: bool
    ):
        base = get_canonical_path(ast.canonical_path)
        indexes = {
            Kind.MODULE: 1,
            Kind.ATTRIBUTE: 3 if from_class else 2,
            Kind.FUNCTION: 3 if from_class else 2,
            Kind.CLASS: 2,
        }
        kinds = {
            Kind.MODULE: "module",
            Kind.ATTRIBUTE: "property" if from_class else "attribute",
            Kind.FUNCTION: "method" if from_class else "function",
            Kind.CLASS: "class",
        }
        index = indexes[ast.kind]
        module_path = "/".join(base.split(".")[0:-index])
        remaining = ".".join(base.split(".")[-index:])
        return SymbolRef(
            navigation_path=f"{module_path}.{remaining}",
            kind=cast(SymbolKind, kinds[ast.kind]),
        )

    def init_symbols_rec(ast: AstModule, depth=0, max_depth=10) -> dict[str, SymbolRef]:
        if depth > max_depth:
            raise RecursionError("Maximum recursion depth reached")

        elements = extract_module(ast=ast)
        functions = {
            get_canonical_path(f.canonical_path): get_symbol(f, from_class=False)
            for f in elements.functions
        }
        attributes = {
            get_canonical_path(a.canonical_path): get_symbol(a, from_class=False)
            for a in elements.attributes
        }
        classes = {
            get_canonical_path(c.canonical_path): get_symbol(c, from_class=False)
            for c in elements.classes
        }
        methods = {
            get_canonical_path(m.canonical_path): get_symbol(m, from_class=True)
            for c in elements.classes
            for m in c.functions.values()
        }
        properties = {
            get_canonical_path(p.canonical_path): get_symbol(p, from_class=True)
            for c in elements.classes
            for p in c.attributes.values()
        }
        sub_modules = {
            k: v
            for module in elements.modules
            for k, v in init_symbols_rec(
                ast=module, depth=depth + 1, max_depth=max_depth
            ).items()
        }
        return {
            get_canonical_path(ast.canonical_path): get_symbol(ast, from_class=False),
            **functions,
            **attributes,
            **classes,
            **methods,
            **properties,
            **attributes,
            **sub_modules,
        }

    return init_symbols_rec(ast=root_ast)


def get_module_aliases(root_ast: AstModule, ast: AstModule):
    """
    Retrieves the list of aliases defined within a module.

    Parameters:
        root_ast: Root module's AST.
        ast: Module AST to generate the aliases for.
    """

    def is_lib_alias(m):
        try:
            return isinstance(m, AstAlias) and m.canonical_path.startswith(root_ast.name)
        except AliasResolutionError:
            return False
        except AttributeError:
            return False

    imports: list[AstAlias] = [m for m in ast.all_members.values() if is_lib_alias(m)]

    wild_char_imports = [m for m in imports if m.name.endswith("/*")]

    def is_target_alias(m):
        try:
            return isinstance(m, AstAlias) and m.target.canonical_path.startswith(
                root_ast.name
            )
        except AliasResolutionError:
            return False
        except AttributeError:
            return False

    wild_char_aliases = [
        alias
        for short_access in wild_char_imports
        for alias in short_access.all_members.values()
        if is_target_alias(alias)
    ]
    explicit_imports = [m for m in imports if not m.name.endswith("/*")]
    explicit_aliases = {
        f"{ast.canonical_path}.{m.name}": m.canonical_path for m in explicit_imports
    }

    implicit_aliases = {
        f"{ast.canonical_path}.{alias.name}": alias.target.canonical_path
        for alias in wild_char_aliases
    }
    return {**explicit_aliases, **implicit_aliases}


def init_aliases(root_ast: AstModule) -> dict[str, str]:
    """
    Retrieves the list of all aliases defined within the provided root AST.

    Recursively call :func:`mkdocs_py_griffe.py_griffe.get_module_aliases` for each module found in the provided AST.

    Parameters:
        root_ast: Root module's AST.
    """

    def init_aliases_rec(ast: AstModule, depth=0, max_depth=10) -> dict[str, str]:
        if depth > max_depth:
            raise RecursionError("Maximum recursion depth reached")

        submodules = [
            v
            for _, v in ast.modules.items()
            if not isinstance(v, griffe.dataclasses.Alias)
        ]
        aliases = get_module_aliases(root_ast=root_ast, ast=ast)
        aliases_submodules = {
            k: v
            for module in submodules
            for k, v in init_aliases_rec(
                ast=module, depth=depth + 1, max_depth=max_depth
            ).items()
        }
        return {
            **aliases,
            **aliases_submodules,
        }

    return init_aliases_rec(ast=root_ast)


def generate_api(root_ast: AstModule, config: Configuration):
    """
    Create documentation API files from an AST parsed by the griffe library:
    * It generates the list of exported symbols (those documented).
      See :func:`mkdocs_py_griffe.py_griffe.init_symbols`.
    * It generates the list of all aliases from the `__init__.py` files, and from the `import` statements in the files.
      See :func:`mkdocs_py_griffe.py_griffe.init_aliases`.
    * It generates the documentation recursively for all exported modules (those documented).

    Parameters:
        root_ast: Root module's AST.
        config: Configuration.
    """
    all_symbols = init_symbols(root_ast=root_ast)
    all_aliases = init_aliases(root_ast=root_ast)
    project = Project(
        config=config,
        root_ast=root_ast,
        all_symbols=all_symbols,
        all_aliases=all_aliases,
    )

    def get_doc_rec(module: AstModule, path: str):

        doc = parse_module(module, project=project)
        target_path = Path(config.out, *path.split(".")).with_suffix(".json")
        if target_path.exists():
            target_path.unlink()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding='UTF8') as json_file:
            json.dump(doc, json_file, cls=DataclassJSONEncoder, indent=4)
        for child in doc.children:
            gr_child = module[child.name]
            get_doc_rec(module=gr_child, path=f"{path}.{child.name}")

    get_doc_rec(module=root_ast, path=root_ast.name)

    print(
        f"Internal cross links errors ({len(DocReporter.internal_cross_ref_errors)}):"
    )
    pprint.pprint(DocReporter.internal_cross_ref_errors)
    print(
        f"External cross links errors  ({len(DocReporter.external_cross_ref_errors)}):"
    )
    pprint.pprint(DocReporter.external_cross_ref_errors)
    print(f"No docstring errors ({len(DocReporter.no_docstrings_errors)}):")
    pprint.pprint(DocReporter.no_docstrings_errors)
    print(f"Sphinx cross-link tag unknown ({len(DocReporter.sphinx_tag_unknown)}):")
    pprint.pprint(DocReporter.sphinx_tag_unknown)
    print(
        f"Sphinx cross-link unresolved ({len(DocReporter.sphinx_links_unresolved.keys())}):"
    )
    pprint.pprint(DocReporter.sphinx_links_unresolved)
