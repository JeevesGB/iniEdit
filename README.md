<img width="512" height="512" alt="ico" src="ico.png" />

**iniEdit** is a Tkinter + Matplotlib tool that creates the `.ini` files of a [GT3-revisited](https://github.com/matt-pulsipher/GT3-revisited) car mod
from a form, in the same format as the reference mods (daihatsu_dumbo, weesan3, bx_break).

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
  ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
  [![Gran Turismo 3](https://img.shields.io/badge/Gran%20Turismo-3-red?logo=playstation&logoColor=red)]()
  [![Last commit](https://img.shields.io/github/last-commit/JeevesGB/iniEdit)](https://github.com/JeevesGB/GTExplorer/commits/main)


***Download the latest release here:***   [![GitHub release](https://img.shields.io/github/v/release/JeevesGB/iniEdit)](https://github.com/JeevesGB/iniEdit/releases) 

Run `requirements.bat` once, then `run.bat` (or `cd src && python main.py`).

## Getting started

On launch you choose **New mod** or **Edit existing mod** (recently used mods are listed for one-click opening).
**New mod** asks for a folder name and a location, then creates the mod folder with `cars/`, `makers/`,
`images/` and `models/` ready to use. Then:

1. Fill in the **mod** and **car** tabs. Fields marked `*` are required, and anything you leave blank is
   borrowed from the donor car. Every field has a short explanation under it.
2. Edit the **torque curve** (and **paints**, optionally), and use **model tools** for the 3D body and pictures.
3. Check the **preview** tab, then **Save** (Ctrl+S).

Helpers: the **Problems** button lists everything that needs attention (double-click to jump to it) and tabs
with problems show a warning sign and count; the line under the toolbar shows the mod folder, with an
**Open folder** button; **Help > Quick guide** (F1) explains the workflow and the jargon (label, donor, priority...).
Problems are warnings only and never block saving.

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
src/core/project.py         the three-file mod: paths, work folders, save, open folder
src/core/settings.py        per-user settings (~/.gt3_mod_creator.json): Blender path, recent mods, tips
src/data/car_mod_schema.json   ** the parameters: edit this to add/change fields **
src/gui/app.py              main window, menus, file actions, problems list
src/gui/start_dialog.py     start-up (new / edit / recent) and new-mod dialogs
src/gui/guide.py            Help > Quick guide text
src/gui/parameter_form.py   auto-built form for each file
src/gui/curve_panel.py      torque curve editor: draggable graph, table, undo/redo, tools, generator
src/gui/gear_panel.py       gearbox editor: ratio table, speed / drive-force charts, presets, top-speed fit
src/core/gearing.py         tyre radius, speed per gear, ratio generators and presets
src/gui/paints_panel.py     [paints] list editor
src/gui/preview_panel.py    live preview of each generated file
src/core/modeltools.py      model / picture helpers (measure, finish, pictures, Blender runner)
src/gui/model_panel.py      the Model tools tab
src/tools/prepare.py        Blender script run by the Model tools tab (bundled by build.bat)
```

## Torque curve tab

- **On the graph:** drag a point to move it (Shift = vertical only), click empty space to add one, right-click a point to
  remove it, arrow keys nudge the selected point. Moves snap to the *Snap to* values (default 100 rpm / 1 Nm).
  Hover a point to see rpm, Nm and power.
- **In the table:** double-click a number to edit it; Delete removes the selection; *Split segment* adds a point halfway.
- **Undo / redo** (Ctrl+Z / Ctrl+Y, up to 100 steps) cover every change, including the tools below.
- **Rev limiter and idle** from the car tab are drawn on the graph; *End at rev limiter* trims or extends the curve to it.
- **Power** is shown on a second axis in kW, PS or hp.
- **Tools:** scale torque by a %, move the whole curve in rpm, smooth, paste `rpm:Nm` text or two spreadsheet columns,
  load/export (.txt, .ini, .csv), and **Generate from specs**: enter peak torque, peak power, idle and limiter and a
  realistic curve through both peaks is built.

## Gearbox tab

Edits the same *Gear ratios*, *Final drive* and *Reverse* fields as the car tab (they stay in sync).

- Table with ratio, step to the next gear, overall ratio, speed at the rev limiter and rpm after an upshift. Double-click a ratio to edit it.
- **Build a gearbox:** generate N gears between a 1st and top ratio (even or closer at the top), or start from a preset.
- **Top speed:** type a target speed and the final drive is calculated from the tyre size and top gear.
- Charts: engine rpm vs road speed (with shift drops and peak power marked) and estimated drive force vs road speed.
  Speeds use the driven tyres' rolling radius, so check the tyre sizes on the car tab. Force assumes 90 % drivetrain efficiency.

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
(fixed list), `comment` (inline `;` note), `note_above`, `help` (shown under the field in the form only,
never written to the .ini). Sections can also have a `description`, shown at the top of their box.
Write defaults as strings if their exact text matters (`"2.00"`).

## Notes

- Opening an existing mod keeps unrecognised keys and writes them back; your own
  hand-written comments are replaced by the standard ones.
- The car file is named after its `label` (as the example README asks).
- Validation warns but never blocks saving.
