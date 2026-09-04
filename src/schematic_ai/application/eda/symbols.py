"""KiCad symbol-library loading for trusted endpoint derivation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from schematic_ai.application.eda.checker import SExpr, atom, collect_symbol_pin_points, parse_sexpr
from schematic_ai.application.knowledge.kicad import resolve_symbol_dir
from schematic_ai.domain.knowledge import SymbolReference


@dataclass(frozen=True)
class KiCadSymbolDefinition:
    lib_id: str
    source_path: Path
    source_text: str
    embedded_text: str
    pin_points: dict[str, tuple[float, float]]


class KiCadSymbolDefinitionResolver:
    """Load exact KiCad symbol definitions from a trusted configured library."""

    def __init__(self) -> None:
        self.last_failure_reason: str | None = None

    def resolve(self, reference: SymbolReference, symbol_dir: str | Path | None = None) -> KiCadSymbolDefinition | None:
        self.last_failure_reason = None
        root = resolve_symbol_dir(symbol_dir)
        if root is None:
            self.last_failure_reason = "KiCad symbol directory is not configured"
            return None
        library_path = root / f"{reference.library}.kicad_sym"
        if not library_path.exists():
            self.last_failure_reason = f"KiCad symbol library {library_path.name} does not exist"
            return None
        text = library_path.read_text(encoding="utf-8")
        root_expr = parse_sexpr(text)
        if not isinstance(root_expr, list):
            self.last_failure_reason = f"KiCad symbol library {library_path.name} is not a symbol library S-expression"
            return None
        symbol_expr = next(
            (
                symbol
                for symbol in _children(root_expr, "symbol")
                if atom(symbol, 1) == reference.symbol_name
            ),
            None,
        )
        if symbol_expr is None:
            self.last_failure_reason = f"symbol {reference.library}:{reference.symbol_name} not found in configured KiCad library"
            return None
        if not _is_supported_single_unit_symbol(symbol_expr, reference.symbol_name):
            self.last_failure_reason = (
                f"unsupported symbol variant for {reference.library}:{reference.symbol_name}; "
                "Milestone 8 supports simple single-unit, single-style symbols only"
            )
            return None
        pin_points = collect_symbol_pin_points(symbol_expr)
        if not pin_points:
            self.last_failure_reason = f"symbol {reference.library}:{reference.symbol_name} has no usable pin endpoints"
            return None
        source_text = extract_symbol_text(text, reference.symbol_name)
        if source_text is None:
            self.last_failure_reason = f"symbol {reference.library}:{reference.symbol_name} source subtree could not be preserved"
            return None
        embedded_text = _indent_block(
            rename_symbol_text(source_text, reference.symbol_name, f"{reference.library}:{reference.symbol_name}"),
            4,
        )
        return KiCadSymbolDefinition(
            lib_id=f"{reference.library}:{reference.symbol_name}",
            source_path=library_path,
            source_text=source_text,
            embedded_text=embedded_text,
            pin_points=pin_points,
        )


def _children(expr: list[SExpr], name: str) -> list[list[SExpr]]:
    return [child for child in expr if isinstance(child, list) and atom(child, 0) == name]


def _is_supported_single_unit_symbol(expr: list[SExpr], symbol_name: str) -> bool:
    child_symbols = _children(expr, "symbol")
    return len(child_symbols) == 1 and atom(child_symbols[0], 1) == f"{symbol_name}_0_1"


def extract_symbol_text(text: str, symbol_name: str) -> str | None:
    depth = 0
    index = 0
    in_string = False
    escape = False
    while index < len(text):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            index += 1
            continue
        if char == "(":
            if depth == 1 and text.startswith("(symbol", index):
                end = _matching_paren(text, index)
                candidate = text[index : end + 1]
                parsed = parse_sexpr(candidate)
                if isinstance(parsed, list) and atom(parsed, 1) == symbol_name:
                    return candidate
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    return None


def rename_symbol_text(text: str, old_name: str, new_name: str) -> str:
    old = re.escape(_quoted_atom_body(old_name))
    new = _quoted_atom_body(new_name)
    renamed = re.sub(r'(\(\s*symbol\s+")' + old + r'(")', r"\1" + new + r"\2", text, count=1)
    return re.sub(r'(\(\s*symbol\s+")' + old + r'(_[^"]*")', r"\1" + new + r"\2", renamed)


def _quoted_atom_body(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("unclosed symbol subtree")


def _indent_block(text: str, indent: int) -> str:
    prefix = " " * indent
    return "\n".join(prefix + line for line in text.strip().splitlines())


def _rename_symbol(expr: list[SExpr], new_name: str) -> list[SExpr]:
    renamed: list[SExpr] = []
    for index, item in enumerate(expr):
        if index == 1:
            renamed.append(new_name)
        elif isinstance(item, list):
            renamed.append(_rename_nested_derived_symbol(item, atom(expr, 1) or "", new_name))
        else:
            renamed.append(item)
    return renamed


def _rename_nested_derived_symbol(expr: list[SExpr], old_prefix: str, new_prefix: str) -> list[SExpr]:
    renamed: list[SExpr] = []
    for index, item in enumerate(expr):
        if index == 1 and atom(expr, 0) == "symbol" and isinstance(item, str) and item.startswith(old_prefix):
            renamed.append(item.replace(old_prefix, new_prefix, 1))
        elif isinstance(item, list):
            renamed.append(_rename_nested_derived_symbol(item, old_prefix, new_prefix))
        else:
            renamed.append(item)
    return renamed


def to_sexpr(expr: SExpr, indent: int = 0, parent_head: str | None = None, index: int | None = None) -> str:
    if isinstance(expr, str):
        return _format_atom(expr, parent_head, index)
    if _is_flat(expr):
        head = atom(expr, 0)
        return "(" + " ".join(to_sexpr(item, parent_head=head, index=item_index) for item_index, item in enumerate(expr)) + ")"
    pad = " " * indent
    head = atom(expr, 0)
    lines = [pad + "(" + to_sexpr(expr[0], parent_head=head, index=0)]
    for item_index, item in enumerate(expr[1:], start=1):
        if isinstance(item, list):
            lines.append(to_sexpr(item, indent + 2))
        else:
            lines[-1] += " " + to_sexpr(item, parent_head=head, index=item_index)
    lines[-1] += ")"
    return "\n".join(lines)


def _is_flat(expr: list[SExpr]) -> bool:
    return all(not isinstance(item, list) for item in expr)


def _format_atom(value: str, parent_head: str | None, index: int | None) -> str:
    if index == 0:
        return value
    if _should_quote(parent_head, index):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _should_quote(parent_head: str | None, index: int | None) -> bool:
    if parent_head in {"symbol", "property", "name", "number"} and index in {1, 2}:
        return True
    return False
