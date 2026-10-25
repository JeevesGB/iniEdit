"""One .ini document: parse, validate against a FileSpec, and write in the game's style.

Output style (matches the reference mods):
  * ``key = value``, sections in schema order, blank line between sections
  * optional ``; comments`` - inline ones aligned to a fixed column, wrapped ones
    continuing on following lines at the same column
  * values are written exactly as typed (``2.00`` stays ``2.00``)
  * LF line endings, ASCII text
"""

from __future__ import annotations

import configparser

from .schema import FileSpec, Section


class IniDocument:
    """Raw string values as ``values[section][key]``.

    Entries the schema doesn't know are kept and written after the known ones, so
    opening an existing file never silently drops data.
    """

    def __init__(self, values: dict[str, dict[str, str]] | None = None):
        self.values: dict[str, dict[str, str]] = values or {}

    # ---- reading ----------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "IniDocument":
        parser = configparser.ConfigParser(
            interpolation=None,
            delimiters=("=",),
            comment_prefixes=(";",),            # '#' is NOT a comment: paints use '#RRGGBB'
            inline_comment_prefixes=(";",),     # `key = value   ; note`
            empty_lines_in_values=False,
            default_section="\0no-default",
            strict=False,
        )
        parser.optionxform = str                # paint names keep their case
        try:
            parser.read_string(text)
        except configparser.Error as exc:
            raise ValueError(f"Not a valid .ini file: {exc}") from exc
        return cls({s: {k: v.strip() for k, v in parser.items(s)} for s in parser.sections()})

    def get(self, section: str, key: str, default: str = "") -> str:
        return self.values.get(section, {}).get(key, default)

    def sections(self) -> list[str]:
        return list(self.values)

    def unknown_entries(self, spec: FileSpec) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        known = {s.name: s for s in spec.sections}
        for sname, items in self.values.items():
            sec = known.get(sname)
            for key, value in items.items():
                if sec is None or (sec.kind == "fields" and all(p.key != key for p in sec.parameters)):
                    out.setdefault(sname, {})[key] = value
        return out

    # ---- validation -------------------------------------------------
    def validate(self, spec: FileSpec) -> list[str]:
        issues = []
        for sec in spec.sections:
            if sec.kind == "paints":
                issues += [f"[{sec.name}] {m}" for m in _paint_issues(self.values.get(sec.name, {}))]
                continue
            for param in sec.parameters:
                value = self.get(sec.name, param.key)
                error = param.validate(value)
                if error and (value.strip() or not self._section_skipped(sec)):
                    issues.append(f"[{sec.name}] {param.key}: {error}")
        return issues

    def _section_skipped(self, sec: Section) -> bool:
        return bool(sec.emit_if) and not self.get(sec.name, sec.emit_if).strip()

    # ---- writing ----------------------------------------------------
    def dumps(self, spec: FileSpec, comments: bool = True, mod_id: str = "") -> str:
        lines: list[str] = []
        col = spec.comment_col

        def comment_block(text: str, indent: str = ""):
            for part in text.split("\n"):
                lines.append(f"{indent}; {part}")

        def entry(key: str, value: str, comment: str = ""):
            head = f"{key} = {value}".rstrip()
            if not (comments and comment):
                lines.append(head)
                return
            first, *rest = comment.split("\n")
            lines.append(head + " " * max(2, col - len(head)) + f"; {first}")
            for part in rest:
                lines.append(" " * col + f"; {part}")

        if comments and spec.preamble:
            comment_block(spec.preamble.replace("{mod_id}", mod_id or "<mod id>"))
        preamble_len = len(lines)

        for sec in spec.sections:
            if self._section_skipped(sec):
                continue
            if sec.kind == "paints":
                body = [(n, c.strip()) for n, c in self.values.get(sec.name, {}).items() if n.strip() and c.strip()]
                known: set[str] = set()
            else:
                body = None
                known = {p.key for p in sec.parameters}
            start = len(lines)
            if lines and lines[-1] != "" and len(lines) != preamble_len:
                lines.append("")
            lines.append(f"[{sec.name}]")
            header_at = len(lines)
            if sec.kind == "paints":
                for name, colour in body:
                    entry(name, colour)
            else:
                lead_at = len(lines)
                if comments and sec.lead_notes:
                    comment_block(sec.lead_notes)
                header_at = len(lines)
                for param in sec.parameters:
                    value = self.get(sec.name, param.key).strip()
                    if value == "" and not param.required:
                        continue
                    if comments and param.note_above:
                        comment_block(param.note_above)
                    entry(param.key, value, param.comment)
                for key, value in self.values.get(sec.name, {}).items():
                    if key not in known and value.strip():
                        entry(key, value.strip())
                if len(lines) == header_at:      # only notes, no entries: drop them too
                    del lines[lead_at:]
                elif comments and sec.footer_notes:
                    comment_block(sec.footer_notes)
            if len(lines) == header_at:          # nothing under the header: drop it
                del lines[start:]
        # sections the schema doesn't know about
        known_sections = {s.name for s in spec.sections}
        for name, items in self.values.items():
            if name not in known_sections and any(v.strip() for v in items.values()):
                if lines:
                    lines.append("")
                lines.append(f"[{name}]")
                for key, value in items.items():
                    if value.strip():
                        entry(key, value.strip())
        while lines and lines[0] == "":
            lines.pop(0)
        return "\n".join(lines) + "\n"


def _paint_issues(paints: dict[str, str]) -> list[str]:
    from .schema import HEX_COLOR

    issues = []
    for name, colour in paints.items():
        if not name.strip():
            issues.append("a paint has no name.")
        elif not HEX_COLOR.fullmatch(colour.strip()):
            issues.append(f"'{name}': colour must look like #RRGGBB.")
        elif not name.isascii():
            issues.append(f"'{name}': non-ASCII character in paint name.")
    return issues
