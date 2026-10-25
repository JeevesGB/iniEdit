"""Schema: which files, sections and keys the creator offers, and how they are written.

The schema is plain JSON (``data/car_mod_schema.json``) so parameters can be added,
removed or re-ranged without touching Python code.  It mirrors the layout of a
GT3-revisited mod folder:  mod.ini, makers/<maker>.ini, cars/<label>.ini.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import curve as curve_mod

TYPES = ("string", "int", "float", "bool", "choice", "list", "curve")
SECTION_KINDS = ("fields", "paints")
TRUE_WORDS = {"1", "true", "yes", "on"}
FALSE_WORDS = {"0", "false", "no", "off"}
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


class SchemaError(Exception):
    pass


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@dataclass
class Parameter:
    key: str
    label: str = ""
    type: str = "string"
    default: object = ""
    unit: str = ""
    help: str = ""
    required: bool = False
    min: float | None = None
    max: float | None = None
    choices: list[str] = field(default_factory=list)      # restricted list
    suggestions: list[str] = field(default_factory=list)  # editable drop-down
    suggest_from: str = ""                                 # dataset suggestions, e.g. "cars.label"
    pattern: str = ""                                      # regex the whole value must match
    pattern_hint: str = ""
    min_items: int = 0
    max_items: int | None = None
    # curve type
    max_points: int = curve_mod.DEFAULT_MAX_POINTS
    x_label: str = "X"
    y_label: str = "Y"
    title: str = ""
    power_readout: bool = False
    default_display_limit: int = 9000
    # output formatting
    comment: str = ""       # inline "; comment" (use \n for continuation lines)
    note_above: str = ""    # comment lines written above the key (\n separated)
    auto: str = ""          # "file.section.key": value is copied from there, no form field

    def default_text(self) -> str:
        if self.type == "bool":
            return "yes" if self.default in (True, "yes", "true", "1", 1) else "no"
        if self.type == "curve" and isinstance(self.default, list):
            return curve_mod.format_curve([(int(x), float(y)) for x, y in self.default])
        if self.type == "list" and isinstance(self.default, list):
            return " ".join(str(v) for v in self.default)
        if self.default is None:
            return ""
        return str(self.default)

    def validate(self, raw: str) -> str | None:
        """Return an error message for a raw text value, or None if it is fine."""
        text = raw.strip()
        if not text:
            return "Required." if self.required else None
        if self.type == "curve":
            return curve_mod.validate_text(text, self.max_points)
        if self.type == "bool":
            return None if text.lower() in TRUE_WORDS | FALSE_WORDS else "Use yes or no."
        if self.type == "choice":
            return None if text in self.choices else f"Choose one of: {', '.join(self.choices)}"
        if self.type in ("int", "float"):
            try:
                value = int(text) if self.type == "int" else float(text)
            except ValueError:
                return "Must be a whole number." if self.type == "int" else "Must be a number."
            return self._range_error(value)
        if self.type == "list":
            tokens = text.split()
            for token in tokens:
                try:
                    value = float(token)
                except ValueError:
                    return f"'{token}' is not a number."
                error = self._range_error(value)
                if error:
                    return error
            if len(tokens) < self.min_items:
                return f"Needs at least {self.min_items} values."
            if self.max_items is not None and len(tokens) > self.max_items:
                return f"At most {self.max_items} values allowed."
            return None
        if self.pattern and not re.fullmatch(self.pattern, text):
            return self.pattern_hint or f"Must match {self.pattern}"
        if not text.isascii():
            return "Non-ASCII character (the reference files are plain ASCII)."
        return None

    def _range_error(self, value: float) -> str | None:
        if self.min is not None and value < self.min:
            return f"Must be at least {self.min:g}."
        if self.max is not None and value > self.max:
            return f"Must be at most {self.max:g}."
        return None


@dataclass
class Section:
    name: str
    title: str
    parameters: list[Parameter] = field(default_factory=list)
    description: str = ""
    kind: str = "fields"
    lead_notes: str = ""           # comment lines right under the [header]
    footer_notes: str = ""         # comment lines after the last key
    emit_if: str = ""              # only write the section if this key is non-blank
    paint_defaults: dict[str, str] = field(default_factory=dict)


@dataclass
class FileSpec:
    id: str
    title: str
    path: str                      # may contain {file.section.key} placeholders
    sections: list[Section]
    comment_col: int = 31          # column (0-based) where inline ';' comments start
    preamble: str = ""             # comment lines at the very top; {mod_id} is substituted
    optional: bool = False
    description: str = ""


@dataclass
class Schema:
    files: list[FileSpec]
    name: str = "Mod"
    format_version: int = 1

    def file(self, file_id: str) -> FileSpec | None:
        return next((f for f in self.files if f.id == file_id), None)

    def find(self, file_id: str, section: str, key: str) -> Parameter | None:
        spec = self.file(file_id)
        if spec:
            for sec in spec.sections:
                if sec.name == section:
                    return next((p for p in sec.parameters if p.key == key), None)
        return None

    def all_parameters(self):
        for spec in self.files:
            for sec in spec.sections:
                for param in sec.parameters:
                    yield spec, sec, param

    def defaults(self, file_id: str) -> dict[str, dict[str, str]]:
        spec = self.file(file_id)
        values: dict[str, dict[str, str]] = {}
        for sec in spec.sections:
            if sec.kind == "paints":
                values[sec.name] = dict(sec.paint_defaults)
            else:
                values[sec.name] = {p.key: p.default_text() for p in sec.parameters if not p.auto}
        return values


_PARAM_FIELDS = set(Parameter.__dataclass_fields__)
_SECTION_FIELDS = set(Section.__dataclass_fields__) - {"parameters"}
_FILE_FIELDS = set(FileSpec.__dataclass_fields__) - {"sections"}


def _check_fields(raw: dict, allowed: set, where: str):
    unknown = set(raw) - allowed
    if unknown:
        raise SchemaError(f"{where}: unknown field(s): {', '.join(sorted(unknown))}.")


def _param(raw: dict, where: str) -> Parameter:
    if "key" not in raw:
        raise SchemaError(f"{where}: parameter is missing 'key'.")
    where = f"{where}.{raw['key']}"
    _check_fields(raw, _PARAM_FIELDS, where)
    ptype = raw.get("type", "string")
    if ptype not in TYPES:
        raise SchemaError(f"{where}: unknown type '{ptype}' (use one of {', '.join(TYPES)}).")
    if ptype == "choice" and not raw.get("choices"):
        raise SchemaError(f"{where}: choice parameters need 'choices'.")
    if raw.get("pattern"):
        try:
            re.compile(raw["pattern"])
        except re.error as exc:
            raise SchemaError(f"{where}: bad pattern: {exc}") from exc
    data = dict(raw)
    data.setdefault("label", raw["key"].replace("_", " ").capitalize())
    return Parameter(**data)


def parse_schema(raw: dict) -> Schema:
    if not isinstance(raw, dict) or not isinstance(raw.get("files"), list) or not raw["files"]:
        raise SchemaError("Schema must be an object with a non-empty 'files' list.")
    files, file_ids = [], set()
    for fraw in raw["files"]:
        for need in ("id", "path"):
            if need not in fraw:
                raise SchemaError(f"Every file needs '{need}'.")
        _check_fields(fraw, _FILE_FIELDS | {"sections"}, f"file {fraw['id']}")
        if fraw["id"] in file_ids:
            raise SchemaError(f"Duplicate file id '{fraw['id']}'.")
        file_ids.add(fraw["id"])
        sections, seen = [], set()
        for sraw in fraw.get("sections", []):
            if "name" not in sraw:
                raise SchemaError(f"File {fraw['id']}: every section needs a 'name'.")
            where = f"{fraw['id']}.{sraw['name']}"
            _check_fields(sraw, _SECTION_FIELDS | {"parameters"}, where)
            if sraw.get("kind", "fields") not in SECTION_KINDS:
                raise SchemaError(f"{where}: kind must be one of {', '.join(SECTION_KINDS)}.")
            params = []
            for praw in sraw.get("parameters", []):
                p = _param(praw, where)
                if p.key in seen:
                    raise SchemaError(f"Duplicate parameter {where}.{p.key}.")
                seen.add(p.key)
                params.append(p)
            sdata = {k: v for k, v in sraw.items() if k != "parameters"}
            sdata.setdefault("title", sraw["name"].capitalize())
            sections.append(Section(parameters=params, **sdata))
        fdata = {k: v for k, v in fraw.items() if k != "sections"}
        fdata.setdefault("title", fraw["id"].capitalize())
        files.append(FileSpec(sections=sections, **fdata))
    return Schema(files, raw.get("name", "Mod"), int(raw.get("format_version", 1)))


def load_schema(path: str | Path) -> Schema:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaError(f"Could not read schema {path}: {exc}") from exc
    return parse_schema(raw)
