from __future__ import annotations
import re
from pathlib import Path, PurePosixPath
from typing import Callable

from . import curve as curve_mod
from . import gearing
from .discdata import DiscCars
from .ini_model import IniDocument
from .schema import FileSpec, Schema, slugify

PLACEHOLDER = re.compile(r"\{(\w+)\.(\w+)\.(\w+)\}")
MOD_ID_RE = re.compile(r"[a-z0-9_]+")
EXTRA_WORK_DIRS = ("images", "models")  


class ModProject:
    def __init__(self, schema: Schema, disc: DiscCars | None = None):
        self.schema = schema
        self.disc = disc or DiscCars()
        self.mod_id = ""
        self.docs: dict[str, IniDocument] = {s.id: IniDocument(schema.defaults(s.id)) for s in schema.files}
        self.include: dict[str, bool] = {s.id: True for s in schema.files}

    def apply_auto_values(self) -> None:
        for spec, sec, param in self.schema.all_parameters():
            if param.auto:
                f, s, k = param.auto.split(".")
                self.docs[spec.id].values.setdefault(sec.name, {})[param.key] = self.docs[f].get(s, k).strip()

    def resolved_docs(self) -> dict[str, IniDocument]:
        self.apply_auto_values()
        raw = self.docs

        def sub(m):
            doc = raw.get(m.group(1))
            return doc.get(m.group(2), m.group(3)).strip() if doc else m.group(0)

        return {fid: IniDocument({s: {k: PLACEHOLDER.sub(sub, v) for k, v in items.items()}
                                  for s, items in doc.values.items()}) for fid, doc in raw.items()}

    def relative_path(self, spec: FileSpec) -> str | None:
        missing = False

        def sub(m):
            nonlocal missing
            value = slugify(self.docs[m.group(1)].get(m.group(2), m.group(3)))
            if not value:
                missing = True
            return value

        path = PLACEHOLDER.sub(sub, spec.path)
        return None if missing else path

    def render(self, comments: bool = True) -> dict[str, tuple[str | None, str]]:
        docs = self.resolved_docs()
        out = {}
        for spec in self.schema.files:
            if self.include[spec.id]:
                out[spec.id] = (self.relative_path(spec), docs[spec.id].dumps(spec, comments, self.mod_id))
        return out

    def validate(self) -> list[str]:
        docs = self.resolved_docs()
        issues = []
        if not self.mod_id:
            issues.append("Mod folder name: required.")
        elif not MOD_ID_RE.fullmatch(self.mod_id):
            issues.append("Mod folder name: use a-z, 0-9 and _ only.")
        for spec in self.schema.files:
            if not self.include[spec.id]:
                continue
            issues += [f"{spec.title}: {i}" for i in docs[spec.id].validate(spec)]
            if self.relative_path(spec) is None:
                issues.append(f"{spec.title}: can't work out the file name (a field it depends on is empty).")
        car = docs.get("car")
        if car is not None and self.disc:
            label = car.get("car", "label").strip()
            donor = car.get("car", "donor").strip()
            if label in self.disc.by_label:
                issues.append(f"Car: [car] label '{label}' is a disc car; a mod car can never replace a disc car.")
            if donor and donor not in self.disc.by_label:
                issues.append(f"Car: [car] donor '{donor}' is not a disc car label (see data/cars.json).")
        if car is not None:
            max_rpm = car.get("powertrain", "max_rpm").strip()
            points = curve_mod.parse_curve(car.get("powertrain", "curve"))
            if max_rpm.isdigit() and points and max(p[0] for p in points) > int(max_rpm):
                issues.append(f"Car: [powertrain] curve goes past max_rpm ({max_rpm}).")
            ratios = gearing.parse_gears(car.get("drivetrain", "gears"))
            if gearing.issues(ratios):
                issues.append("Car: [drivetrain] gears should get smaller from 1st gear upwards.")
        return issues

    def save(self, parent_dir: str | Path, comments: bool = True) -> list[Path]:
        rendered = self.render(comments)
        root = Path(parent_dir) / self.mod_id
        written = []
        for _fid, (rel, text) in rendered.items():
            if rel is None:
                raise ValueError("Cannot save: a file name could not be worked out.")
            target = root / PurePosixPath(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            written.append(target)
        for sub in EXTRA_WORK_DIRS:
            (root / sub).mkdir(exist_ok=True)
        return written

    def work_folders(self) -> list[str]:
        dirs = {PurePosixPath(s.path).parent.as_posix() for s in self.schema.files}
        dirs.discard(".")
        return sorted(dirs | set(EXTRA_WORK_DIRS))

    def create_work_folders(self, parent_dir: str | Path) -> Path:
        if not self.mod_id or not MOD_ID_RE.fullmatch(self.mod_id):
            raise ValueError("Mod folder name: use a-z, 0-9 and _ only.")
        root = Path(parent_dir) / self.mod_id
        if (root / "mod.ini").exists():
            raise ValueError(f"{root} already contains a mod. Use \"Edit existing mod\" to open it.")
        for sub in self.work_folders():
            (root / sub).mkdir(parents=True, exist_ok=True)
        return root

    def stale_files(self, parent_dir: str | Path, written: list[Path]) -> list[Path]:
        root = Path(parent_dir) / self.mod_id
        done = {p.resolve() for p in written}
        dirs = {p.parent for p in written}
        return sorted(p for d in dirs if d != root for p in d.glob("*.ini") if p.resolve() not in done)

    def load_folder(self, folder: str | Path, choose: Callable[[FileSpec, list[Path]], Path | None] | None = None
                    ) -> list[str]:
        folder = Path(folder)
        notes = []
        self.mod_id = folder.name
        if not (folder / "mod.ini").is_file():
            raise ValueError("That folder has no mod.ini - pick the mod's own folder.")
        for spec in self.schema.files:
            rel = PurePosixPath(spec.path)
            if PLACEHOLDER.search(spec.path):
                candidates = sorted((folder / rel.parent).glob("*.ini"))
            else:
                candidates = [folder / rel] if (folder / rel).is_file() else []
            if not candidates:
                self.include[spec.id] = False if spec.optional else self.include[spec.id]
                if not spec.optional:
                    notes.append(f"No {spec.title.lower()} file found; using defaults.")
                self.docs[spec.id] = IniDocument({} if spec.optional else self.schema.defaults(spec.id))
                continue
            picked = candidates[0]
            if len(candidates) > 1:
                picked = (choose(spec, candidates) if choose else None) or candidates[0]
                notes.append(f"{len(candidates)} {spec.title.lower()} files found; loaded {picked.name}.")
            self.docs[spec.id] = IniDocument.parse(picked.read_text(encoding="utf-8-sig"))
            self.include[spec.id] = True
        return notes

    def load_single(self, path: str | Path) -> str:
        doc = IniDocument.parse(Path(path).read_text(encoding="utf-8-sig"))
        for spec in self.schema.files:
            first = spec.sections[0].name
            if first in doc.values:
                self.docs[spec.id] = doc
                self.include[spec.id] = True
                return spec.id
        raise ValueError("Couldn't tell what kind of file this is (no [mod], [maker] or [car] section).")
