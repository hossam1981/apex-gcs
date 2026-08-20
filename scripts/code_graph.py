"""
Placeholder + call-graph checks for APEX GCS.

Finds:
  - stub / TODO / NotImplemented functions
  - HTML handlers that call a missing function (broken sequence)
  - named functions that are never referenced (orphans)
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER_NAME = re.compile(
    r"(placeholder|stub|todo|fixme|not_?implemented|unimplemented|dummy|coming_soon)",
    re.I,
)
STUB_TEXT = re.compile(
    r"\b(TODO|FIXME|XXX|PLACEHOLDER|NotImplemented|not implemented|coming soon|stub)\b",
    re.I,
)
JS_FN_DEF = re.compile(
    r"(?:async\s+)?function\s+([A-Za-z_][\w]*)\s*\(",
)
HTML_ON_ATTR = re.compile(
    r"""\bon(?:click|change|input|keyup|keydown|load)\s*=\s*['"]([^'"]*)['"]""",
    re.I,
)
JS_SIMPLE_CALL = re.compile(r"(?<![\w.])([A-Za-z_][\w]*)\s*\(")
JS_METHOD_CALL = re.compile(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\s*\(")
JS_COMMENT = re.compile(r"//.*?$|/\*.*?\*/", re.S | re.M)
JS_HOST = {
    "alert", "parseInt", "parseFloat", "isNaN", "isFinite", "Number", "String",
    "Boolean", "Object", "Array", "Date", "Math", "JSON", "Error", "TypeError",
    "Map", "Set", "Promise", "Image", "Blob", "URL", "Worker", "WebSocket",
    "fetch", "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "requestAnimationFrame", "cancelAnimationFrame", "eval",
    "encodeURIComponent", "decodeURIComponent", "AudioContext",
    "webkitAudioContext", "confirm", "prompt", "document", "window",
    "console", "navigator", "location", "localStorage", "sessionStorage",
    "history", "event", "this", "self", "parent", "performance",
}

# Names that are entry points even if the local file never calls them.
PY_ENTRY = {"main", "main_async"}


@dataclass
class Finding:
    path: str
    line: int
    kind: str
    message: str

    def format(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"{loc}: [{self.kind}] {self.message}"


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _strip_js_body(body: str) -> str:
    return JS_COMMENT.sub("", body).strip()


def _js_match_brace(text: str, open_idx: int) -> int:
    """Return index of matching `}` for `{` at open_idx, skipping strings/comments."""
    i = open_idx
    n = len(text)
    depth = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            i = text.find("\n", i)
            if i < 0:
                return -1
            continue
        if ch == "/" and nxt == "*":
            i = text.find("*/", i + 2)
            if i < 0:
                return -1
            i += 2
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _js_functions(source: str) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    for match in JS_FN_DEF.finditer(source):
        name = match.group(1)
        brace = source.find("{", match.end())
        if brace < 0:
            continue
        close = _js_match_brace(source, brace)
        if close < 0:
            continue
        body = source[brace + 1 : close]
        found.append((name, _line_of(source, match.start()), body))
    return found


def _is_js_stub(name: str, body: str) -> str | None:
    if PLACEHOLDER_NAME.search(name):
        return f"function {name}() looks like a placeholder name"
    stripped = _strip_js_body(body)
    if not stripped:
        return f"function {name}() has an empty body"
    compact = re.sub(r"\s+", " ", stripped)
    if compact in {"return;", "return null;", "return undefined;", "return {};", "return [];"}:
        return f"function {name}() is a stub ({compact})"
    if re.fullmatch(r"throw new Error\([^)]*\);?", compact) and STUB_TEXT.search(compact):
        return f"function {name}() throws a not-implemented error"
    if STUB_TEXT.search(stripped) and len(compact) < 80:
        return f"function {name}() still contains placeholder text"
    return None


def _ident_uses(source: str, name: str) -> int:
    return len(re.findall(rf"\b{re.escape(name)}\b", source))


def check_javascript(path: Path, rel: str) -> list[Finding]:
    html = path.read_text(encoding="utf-8", errors="replace")
    findings: list[Finding] = []
    functions = _js_functions(html)
    defined = {name: line for name, line, _ in functions}

    for name, line, body in functions:
        reason = _is_js_stub(name, body)
        if reason:
            findings.append(Finding(rel, line, "placeholder", reason))

    for match in HTML_ON_ATTR.finditer(html):
        code = match.group(1)
        line = _line_of(html, match.start())
        for obj, method in JS_METHOD_CALL.findall(code):
            if obj in JS_HOST:
                continue
            if not re.search(rf"\b{re.escape(method)}\s*\([^)]*\)\s*\{{", html):
                findings.append(
                    Finding(
                        rel,
                        line,
                        "sequence",
                        f"handler calls {obj}.{method}() but {method}() is not defined",
                    )
                )
        for fn in JS_SIMPLE_CALL.findall(code):
            if fn in JS_HOST or fn in defined:
                continue
            findings.append(
                Finding(
                    rel,
                    line,
                    "sequence",
                    f"handler calls {fn}() but that function is not defined",
                )
            )

    for name, line, _body in functions:
        # definition adds 1; a real use needs at least 2 occurrences
        if _ident_uses(html, name) < 2:
            findings.append(
                Finding(
                    rel,
                    line,
                    "orphan",
                    f"function {name}() is defined but never called (orphan). ASK the user: wire it, or delete? Do not delete to silence this check.",
                )
            )
    return findings


def _py_is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    name = fn.name
    if PLACEHOLDER_NAME.search(name):
        return f"function {name}() looks like a placeholder name"
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]  # skip docstring
    if not body:
        return f"function {name}() has an empty body"
    if len(body) == 1:
        stmt = body[0]
        if isinstance(stmt, ast.Pass):
            return f"function {name}() is only `pass`"
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is ...:
            return f"function {name}() is only `...`"
        if isinstance(stmt, ast.Raise):
            exc = stmt.exc
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError":
                return f"function {name}() raises NotImplementedError"
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                return f"function {name}() raises NotImplementedError"
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            if STUB_TEXT.search(stmt.value.value):
                return f"function {name}() is still a placeholder string"
    return None


class _PyUseVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.used: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.used.add(node.attr)
        self.generic_visit(node)


def check_python(path: Path, rel: str) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []  # syntax is reported elsewhere
    findings: list[Finding] = []
    defined: list[tuple[str, int, ast.AST]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.append((node.name, node.lineno, node))
            reason = _py_is_stub(node)
            if reason:
                findings.append(Finding(rel, node.lineno, "placeholder", reason))

    uses = _PyUseVisitor()
    uses.visit(tree)
    for name, line, _node in defined:
        if name.startswith("__") and name.endswith("__"):
            continue
        if name in PY_ENTRY:
            continue
        if name not in uses.used:
            findings.append(
                Finding(
                    rel,
                    line,
                    "orphan",
                    f"function {name}() is defined but never called (orphan). ASK the user: wire it, or delete? Do not delete to silence this check.",
                )
            )
    return findings


def check_paths(paths: list[Path], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        rel = str(path.relative_to(root))
        if path.suffix == ".py":
            findings.extend(check_python(path, rel))
        elif path.suffix == ".html":
            findings.extend(check_javascript(path, rel))
    return findings
