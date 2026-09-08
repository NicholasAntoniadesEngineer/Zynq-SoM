from __future__ import annotations

from schgen.core import native as _nat


class Sym(str):
    __slots__ = ()


def _from_tagged(node):
    kind, payload = node
    if kind == "sym":
        return Sym(payload)
    if kind == "str":
        return payload
    if kind == "bool":
        return bool(payload)
    if kind == "num":
        as_int = int(payload)
        return as_int if as_int == payload else payload
    if kind == "list":
        return [_from_tagged(child) for child in payload]
    raise ValueError(f"sexpr: unknown tagged node {kind!r}")


def loads(text: str) -> list:
    if not _nat.loaded():
        raise RuntimeError("native sexpr_loads_tagged required")
    got = _from_tagged(_nat.module().sexpr_loads_tagged(text))
    if _nat.trace():
        ref = _loads_py(text)
        if got != ref:
            raise AssertionError(
                f"native sexpr loads DIVERGENCE: cpp={got!r} python={ref!r}")
    return got


def _loads_py(text: str) -> list:
    i, n = 0, len(text)

    def parse() -> object:
        nonlocal i
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            raise ValueError("unexpected EOF")
        c = text[i]
        if c == "(":
            i += 1
            out: list = []
            while True:
                while i < n and text[i] in " \t\r\n":
                    i += 1
                if i < n and text[i] == ")":
                    i += 1
                    return out
                out.append(parse())
        if c == '"':
            i += 1
            buf: list[str] = []
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if ch == '"':
                    i += 1
                    return "".join(buf)
                buf.append(ch)
                i += 1
            raise ValueError("unterminated string")
        j = i
        while j < n and text[j] not in ' \t\r\n()"':
            j += 1
        tok = text[i:j]
        i = j
        try:
            return int(tok)
        except ValueError:
            try:
                return float(tok)
            except ValueError:
                return Sym(tok)

    node = parse()
    while i < n and text[i] in " \t\r\n":
        i += 1
    if i != n:
        raise ValueError(f"trailing data at {i}")
    return node  # type: ignore[return-value]


def _fmt_num(v: float) -> str:
    if not _nat.loaded():
        raise RuntimeError("native sexpr_fmt_num required")
    return _nat.module().sexpr_fmt_num(float(v))


def _fmt_num_py(v: float) -> str:
    if v == int(v):
        return str(int(v))
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s else "0"


def dumps(node: object, indent: int = 0) -> str:
    if not _nat.loaded():
        raise RuntimeError("native sexpr_dumps_py required")
    got = _nat.module().sexpr_dumps_py(node, indent)
    if _nat.trace():
        ref = _dumps_py(node, indent)
        if got != ref:
            raise AssertionError(
                "native sexpr dumps DIVERGENCE")
    return got


def _dumps_py(node: object, indent: int = 0) -> str:
    pad = "\t" * indent
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        esc = node.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    if isinstance(node, bool):
        return "yes" if node else "no"
    if isinstance(node, (int, float)):
        return _fmt_num_py(float(node))
    if isinstance(node, list):
        if not node:
            return "()"
        has_list = any(isinstance(x, list) for x in node)
        inner = [_dumps_py(x, indent + 1) for x in node]
        if not has_list and sum(len(s) for s in inner) < 90:
            return "(" + " ".join(inner) + ")"
        head = inner[0]
        lines = [f"({head}"]
        for s in inner[1:]:
            lines.append("\t" * (indent + 1) + s)
        lines.append(pad + ")")
        return "\n".join(lines)
    raise TypeError(f"cannot serialise {type(node)}")


def find(node: list, tag: str) -> list | None:
    for x in node:
        if isinstance(x, list) and x and isinstance(x[0], Sym) and x[0] == tag:
            return x
    return None


def find_all(node: list, tag: str) -> list[list]:
    return [x for x in node
            if isinstance(x, list) and x and isinstance(x[0], Sym) and x[0] == tag]
