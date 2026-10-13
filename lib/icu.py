"""ICU MessageFormat parser, validator, and template expander for Antigravity_App_TC.

Supports:
  - Simple placeholders: {name}, {count}, {x1}, {s}
  - Typed placeholders:  {date, date, medium}, {n, number}
  - Plural / select:     {count, plural, =0 {none} one {# item} other {# items}}
  - Offset in plural:    {count, plural, offset:1 =0 {nobody} ...}
  - Escaped quotes:      '{not a placeholder}', '' (literal single quote)
  - Nested blocks:       plural inside select, select inside plural, etc.
"""

import itertools
import re


class ParseError(Exception):
    def __init__(self, msg, pos=None):
        super().__init__(f"{msg} (at pos {pos})" if pos is not None else msg)
        self.pos = pos


class Literal:
    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return f"Literal({self.text!r})"


class SimpleArg:
    __slots__ = ("name", "arg_type", "style")

    def __init__(self, name, arg_type=None, style=None):
        self.name = name
        self.arg_type = arg_type
        self.style = style

    def __repr__(self):
        return f"SimpleArg({self.name!r}, {self.arg_type!r}, {self.style!r})"


class HashPlaceholder:
    """The `#` symbol inside a plural/selectordinal branch."""

    def __repr__(self):
        return "Hash()"


class ComplexArg:
    __slots__ = ("name", "kind", "offset", "branches")

    def __init__(self, name, kind, offset, branches):
        self.name = name
        self.kind = kind
        self.offset = offset
        self.branches = branches

    def __repr__(self):
        return (
            f"ComplexArg({self.name!r}, {self.kind!r}, "
            f"offset={self.offset}, branches={list(self.branches.keys())})"
        )


_IDENT_RE = re.compile(r"\s*([^\s,{}]+)\s*")
_SELECTOR_RE = re.compile(r"\s*(=?\w+)\s*")
_OFFSET_RE = re.compile(r"\s*offset\s*:\s*(-?\d+)\s*")


def parse(msg: str) -> list:
    nodes, pos = _parse_message(msg, 0, in_plural=False, top_level=True)
    if pos != len(msg):
        raise ParseError("unexpected closing '}'", pos)
    return nodes


def _parse_message(msg: str, pos: int, in_plural: bool, top_level: bool):
    nodes = []
    buf = []
    n = len(msg)

    def flush():
        if buf:
            nodes.append(Literal("".join(buf)))
            buf.clear()

    while pos < n:
        ch = msg[pos]

        if ch == "'":
            if pos + 1 < n and msg[pos + 1] == "'":
                buf.append("''")
                pos += 2
                continue
            if pos + 1 < n and msg[pos + 1] in ("{", "}", "#"):
                end = msg.find("'", pos + 1)
                if end == -1:
                    buf.append(msg[pos:])
                    pos = n
                else:
                    buf.append(msg[pos : end + 1])
                    pos = end + 1
                continue
            buf.append("'")
            pos += 1
            continue

        if ch == "#" and in_plural:
            flush()
            nodes.append(HashPlaceholder())
            pos += 1
            continue

        if ch == "{":
            flush()
            arg_node, pos = _parse_argument(msg, pos + 1)
            nodes.append(arg_node)
            continue

        if ch == "}":
            if top_level:
                raise ParseError("unmatched '}'", pos)
            flush()
            return nodes, pos

        buf.append(ch)
        pos += 1

    if not top_level:
        raise ParseError("unclosed '{'", pos)
    flush()
    return nodes, pos


def _parse_argument(msg: str, pos: int):
    n = len(msg)
    m = _IDENT_RE.match(msg, pos)
    if not m:
        raise ParseError("expected argument name", pos)
    name = m.group(1)
    pos = m.end()

    if pos >= n:
        raise ParseError(f"unclosed argument {{{name}", pos)

    if msg[pos] == "}":
        return SimpleArg(name), pos + 1

    if msg[pos] != ",":
        raise ParseError(f"expected ',' or '}}' after {{{name}", pos)
    pos += 1

    m = _IDENT_RE.match(msg, pos)
    if not m:
        raise ParseError(f"expected type in {{{name}, ...", pos)
    arg_type = m.group(1)
    pos = m.end()

    if pos >= n:
        raise ParseError(f"unclosed {{{name}, {arg_type}", pos)

    if msg[pos] == "}":
        return SimpleArg(name, arg_type), pos + 1

    if msg[pos] != ",":
        raise ParseError(f"expected ',' or '}}' after {{{name}, {arg_type}", pos)
    pos += 1

    if arg_type in ("plural", "select", "selectordinal"):
        return _parse_complex(msg, pos, name, arg_type)

    depth = 1
    style_start = pos
    while pos < n and depth > 0:
        if msg[pos] == "{":
            depth += 1
        elif msg[pos] == "}":
            depth -= 1
            if depth == 0:
                break
        pos += 1
    if depth != 0:
        raise ParseError(f"unclosed style in {{{name}, {arg_type}, ...", style_start)
    style = msg[style_start:pos].strip()
    return SimpleArg(name, arg_type, style), pos + 1


def _parse_complex(msg: str, pos: int, name: str, kind: str):
    n = len(msg)
    is_plural = kind in ("plural", "selectordinal")
    offset = 0

    if is_plural:
        m = _OFFSET_RE.match(msg, pos)
        if m:
            offset = int(m.group(1))
            pos = m.end()

    branches = {}
    while pos < n:
        while pos < n and msg[pos] in " \t\r\n":
            pos += 1
        if pos >= n:
            raise ParseError(f"unclosed {{{name}, {kind}, ...", pos)
        if msg[pos] == "}":
            if not branches:
                raise ParseError(f"{{{name}, {kind}}} has no branches", pos)
            return ComplexArg(name, kind, offset, branches), pos + 1

        m = _SELECTOR_RE.match(msg, pos)
        if not m:
            raise ParseError(f"expected branch selector in {{{name}, {kind}}}", pos)
        selector = m.group(1)
        pos = m.end()

        while pos < n and msg[pos] in " \t\r\n":
            pos += 1
        if pos >= n or msg[pos] != "{":
            raise ParseError(f"expected '{{' after selector '{selector}'", pos)
        pos += 1

        sub_nodes, pos = _parse_message(msg, pos, in_plural=is_plural, top_level=False)
        if pos >= n or msg[pos] != "}":
            raise ParseError(f"unclosed branch '{selector}'", pos)
        pos += 1
        branches[selector] = sub_nodes

    raise ParseError(f"unclosed {{{name}, {kind}}}", pos)


def serialize(nodes: list) -> str:
    out = []
    for node in nodes:
        if isinstance(node, Literal):
            out.append(node.text)
        elif isinstance(node, HashPlaceholder):
            out.append("#")
        elif isinstance(node, SimpleArg):
            if node.arg_type is None:
                out.append(f"{{{node.name}}}")
            elif node.style is None:
                out.append(f"{{{node.name},{node.arg_type}}}")
            else:
                out.append(f"{{{node.name},{node.arg_type},{node.style}}}")
        elif isinstance(node, ComplexArg):
            parts = [f"{{{node.name},{node.kind},"]
            if node.offset:
                parts.append(f"offset:{node.offset} ")
            for sel, sub in node.branches.items():
                parts.append(f"{sel}{{{serialize(sub)}}}")
            parts.append("}")
            out.append("".join(parts))
    return "".join(out)


def extract_placeholders(nodes: list) -> set[tuple[str, str | None]]:
    found = set()
    for node in nodes:
        if isinstance(node, SimpleArg):
            found.add((node.name, node.arg_type))
        elif isinstance(node, ComplexArg):
            found.add((node.name, node.kind))
            for sub in node.branches.values():
                found |= extract_placeholders(sub)
    return found


def validate_pair(en_msg: str, zh_msg: str) -> list[str]:
    if ", plural," not in en_msg and ", select," not in en_msg and ", selectordinal," not in en_msg:
        en_ph = set(re.findall(r"\{([a-zA-Z0-9_]+)\}", en_msg))
        zh_ph = set(re.findall(r"\{([a-zA-Z0-9_]+)\}", zh_msg))
        errors = []
        if en_ph - zh_ph:
            errors.append(f"missing placeholders: {en_ph - zh_ph}")
        if zh_ph - en_ph:
            errors.append(f"unknown placeholders: {zh_ph - en_ph}")
        return errors

    errors = []
    try:
        en_ast = parse(en_msg)
    except ParseError as e:
        return [f"EN parse error: {e}"]

    try:
        zh_ast = parse(zh_msg)
    except ParseError as e:
        return [f"ZH parse error: {e}"]

    en_ph = extract_placeholders(en_ast)
    zh_ph = extract_placeholders(zh_ast)

    missing = en_ph - zh_ph
    extra = zh_ph - en_ph
    if missing:
        errors.append(f"missing placeholders: { {n for n, _ in missing} }")
    if extra:
        errors.append(f"unknown placeholders: { {n for n, _ in extra} }")

    _check_complex(zh_ast, errors)
    return errors


def _check_complex(nodes: list, errors: list):
    for node in nodes:
        if isinstance(node, ComplexArg):
            if "other" not in node.branches:
                errors.append(f"{{{node.name}, {node.kind}}} missing required 'other' branch")
            for sub in node.branches.values():
                _check_complex(sub, errors)


def expand_plural_to_templates(en_msg: str, zh_msg: str) -> list[tuple[str, str]]:
    """Expand an ICU message pair into concrete (en_pattern, zh_pattern) templates."""
    try:
        en_ast = parse(en_msg)
        zh_ast = parse(zh_msg)
    except ParseError:
        return []

    def expand_nodes(nodes, branch_choice):
        parts = []
        for node in nodes:
            if isinstance(node, Literal):
                parts.append(node.text)
            elif isinstance(node, HashPlaceholder):
                parts.append("{#}")
            elif isinstance(node, SimpleArg):
                parts.append(f"{{{node.name}}}")
            elif isinstance(node, ComplexArg):
                sel = branch_choice.get(node.name, "other")
                sub = node.branches.get(sel) or node.branches.get("other", [])
                expanded = expand_nodes(sub, branch_choice)
                expanded = expanded.replace("{#}", f"{{{node.name}}}")
                parts.append(expanded)
        return "".join(parts)

    complex_args = []

    def find_complex(nodes):
        for n in nodes:
            if isinstance(n, ComplexArg):
                complex_args.append((n.name, list(n.branches.keys())))
                for sub in n.branches.values():
                    find_complex(sub)

    find_complex(en_ast)

    if not complex_args:
        return [(expand_nodes(en_ast, {}), expand_nodes(zh_ast, {}))]

    results = []
    seen = set()
    names = [name for name, _ in complex_args]
    branch_lists = [branches for _, branches in complex_args]

    for combo in itertools.product(*branch_lists):
        choice = dict(zip(names, combo))
        en_pat = expand_nodes(en_ast, choice)
        zh_pat = expand_nodes(zh_ast, choice)
        if en_pat not in seen and en_pat != zh_pat:
            seen.add(en_pat)
            results.append((en_pat, zh_pat))

    return results
