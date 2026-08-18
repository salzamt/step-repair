# STEP Repair

Repair and validate STEP CAD geometry with FreeCAD. The tool sews and fixes an
input shape, checks every resulting solid, and writes either a verified STEP
file or one STL file per solid for multi-part printing workflows.

## Requirements

- [FreeCAD](https://www.freecad.org/) installed as the `org.freecad.FreeCAD`
  Flatpak application
- Bash, `realpath`, and `flatpak`

The repository does not include CAD models. STEP and STL files are ignored by
default because they are typically large generated or proprietary assets.

## Usage

Make the launcher executable once after cloning:

```bash
chmod +x run-repair
```

Repair a STEP file. The repaired file is placed next to the input as
`<name>_repaired.<extension>`:

```bash
./run-repair path/to/model.stp
```

Export each repaired solid as a separate STL file instead:

```bash
./run-repair --stl path/to/model.step
```

The STL files are written to `<name>_repaired_parts/`. Import all of them
together in Bambu Studio and choose the multi-part-object option when prompted.

## What the repair does

1. Reads the source STEP geometry.
2. Sews and fixes the shape with FreeCAD's Part workbench.
3. Converts closed shells to solids when necessary.
4. Validates that every solid is non-null, valid, closed, non-empty, and has
   positive volume.
5. For STEP output, round-trips the exported file and validates it again.

The tool deliberately avoids boolean operations, fusing parts, and
`removeSplitter()` so it preserves individual parts where possible.

## Development

There is no separate build step. Run basic local checks with:

```bash
bash -n run-repair
python3 -m py_compile repair_step.py
```

`repair_step.py` imports FreeCAD modules, so exercising the repair logic
requires running it through `run-repair` with FreeCAD installed.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md), keep
changes focused, and do not commit CAD files unless they are explicitly needed
as reviewed test fixtures.

## License

This project is licensed under the [MIT License](LICENSE).
