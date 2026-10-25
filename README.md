# GT3 Mod Creator

A Tkinter + Matplotlib tool that creates the `.ini` files of a GT3-revisited car mod
from a form, in the same format as the reference mods (daihatsu_dumbo, weesan3, bx_break).

Run `requirements.bat` once, then `run.bat` (or `cd src && python main.py`).

## What it writes

```
<mod id>/
  mod.ini                  [mod]
  makers/<maker>.ini       [maker]            (optional: only for a maker the disc lacks)
  cars/<label>.ini         [car] [body] [powertrain] [drivetrain] [tires]
                           [model] [paints] [dealer] [arcade] [reference]
  images/  models/         created empty, for your picture and .glb files
```

Output matches the reference files: same section and key order, `key = value`,
`; comments` aligned to column 31 (21 in mod.ini), `yes`/`no` booleans, LF line endings,
and numbers written exactly as typed (`2.00` stays `2.00`). Sections with nothing in
them (e.g. `[model]` without a file, `[reference]` when blank) are left out, so the
donor's values are used. Options > "Write explanatory comments" switches the comments
off for the plain style of `bx_break`.

## Layout

```
src/main.py                 entry point
src/core/curve.py           rpm:Nm curve parse / format / validate
src/core/schema.py          loads the parameter schema (JSON)
src/core/ini_model.py       one .ini: parse, validate, write in the game's style
src/core/project.py         the three-file mod: paths, save, open folder
src/data/car_mod_schema.json   ** the parameters: edit this to add/change fields **
src/gui/app.py              main window, menus, file actions
src/gui/parameter_form.py   auto-built form for each file
src/gui/curve_panel.py      torque curve editor + live plot
src/gui/paints_panel.py     [paints] list editor
src/gui/preview_panel.py    live preview of each generated file
src/core/modeltools.py      model / picture helpers (measure, finish, pictures, Blender runner)
src/gui/model_panel.py      the Model tools tab
src/tools/prepare.py        Blender script run by the Model tools tab (bundled by build.bat)
```

## Model tools tab

The **model tools** tab (icon: `src/gui/icons/model_tools.png`) gets a 3D body into the mod,
fills in its sizes and makes the dealer pictures. Files go where the car tab's `Model file`,
`Picture` and `Thumbnail` paths point; if the mod isn't saved yet you are asked to save it.

1. **Add your 3D body**: *I have a finished .glb* copies it into the mod and measures it.
   *I have a CarConcept-style .glb* first cleans it up in Blender (found automatically, or
   use "Find…"; remembered in `~/.gt3_mod_creator.json`), sets the game's materials, then measures.
2. **Fill in the sizes**: after measuring you are asked whether to put length, width and height
   (and wheelbase / tracks after a Blender conversion) in the car tab. The buttons repeat this later.
3. **Dealer pictures**: copy the viewer command, take a screenshot of the car in the game,
   then choose it; the 640x448 picture and 51x27 thumbnail are made for you.

The Blender option is written for the CarConcept model (CC-BY 4.0: keep its credit). For
another model edit `DELETE_PREFIX` / `RENAME` in `src/tools/prepare.py` and `MATS` in
`src/core/modeltools.py`. The finished-.glb option and the pictures work with anything.

## Changing the parameters

Everything the form offers comes from `src/data/car_mod_schema.json` (or any schema
you load via Options > Load parameter schema). A parameter looks like:

```json
{"key": "weight_kg", "label": "Curb weight", "type": "float", "unit": "kg",
 "min": 100, "default": "1300", "comment": "curb weight (the game adds 120 kg of driver)"}
```

Types: `string`, `int`, `float`, `bool`, `choice`, `list`, `curve`. Useful fields:
`required`, `min`/`max`, `pattern`, `suggestions` (editable drop-down), `choices`
(fixed list), `comment` (inline `;` note), `note_above`, `help` (shown in the form).
Write defaults as strings if their exact text matters (`"2.00"`).

## Notes

- Opening an existing mod keeps unrecognised keys and writes them back; your own
  hand-written comments are replaced by the standard ones.
- The car file is named after its `label` (as the example README asks).
- Validation warns but never blocks saving.
