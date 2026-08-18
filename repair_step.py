#!/usr/bin/env python3

import os
import sys

import FreeCAD as App
import Part
import Mesh


DEFAULT_TOLERANCE = 0.01  # mm
PRECISION = 1e-7
MIN_TOLERANCE = 1e-7
MIN_VOLUME = 1e-9

# STL tessellation
LINEAR_DEFLECTION = 0.05
ANGULAR_DEFLECTION = 0.261799  # ~15 degrees in radians


def stats(label, shape):
    print(f"\n{label}")
    print("-" * len(label))
    print("valid:  ", shape.isValid())
    print("solids: ", len(shape.Solids))
    print("shells: ", len(shape.Shells))
    print("faces:  ", len(shape.Faces))
    print("edges:  ", len(shape.Edges))

    for i, shell in enumerate(shape.Shells, 1):
        print(
            f"  shell {i:03d}: "
            f"closed={shell.isClosed()} "
            f"faces={len(shell.Faces)}"
        )


def solid_stats(label, solid):
    print(
        f"{label}: "
        f"valid={solid.isValid()} "
        f"closed={solid.isClosed()} "
        f"faces={len(solid.Faces)} "
        f"edges={len(solid.Edges)} "
        f"volume={solid.Volume:.3f} mm³"
    )


def validate_solid(solid):
    errors = []

    if solid.isNull():
        errors.append("null shape")
        return errors

    if not solid.isValid():
        errors.append("invalid BRep")

    if not solid.isClosed():
        errors.append("not closed")

    if solid.Volume <= MIN_VOLUME:
        errors.append(f"zero/negative volume ({solid.Volume})")

    if len(solid.Faces) == 0:
        errors.append("no faces")

    return errors


def repair_shape(input_file, tolerance):
    """
    OLD / PROVEN repair path.

    Intentionally kept simple:
      read
      -> sew
      -> fix
      -> convert closed shells to solids

    In particular:
      - NO removeSplitter()
      - NO fuse()
      - NO boolean operations between parts
      - NO FreeCAD document object hierarchy
    """

    print("\nReading STEP ...")

    try:
        shape = Part.Shape()
        shape.read(input_file)
    except Exception as exc:
        raise RuntimeError(f"Could not read STEP: {exc}")

    if shape.isNull():
        raise RuntimeError("STEP contains no geometry")

    stats("ORIGINAL", shape)

    # ----------------------------------------------------------
    # Sew
    # ----------------------------------------------------------

    print(f"\nSewing with tolerance {tolerance} mm ...")

    try:
        shape.sewShape(tolerance)
    except Exception as exc:
        raise RuntimeError(f"sewShape() failed: {exc}")

    stats("AFTER SEW", shape)

    # ----------------------------------------------------------
    # Fix
    # ----------------------------------------------------------

    print("\nRunning shape.fix() ...")

    try:
        changed = shape.fix(
            PRECISION,
            MIN_TOLERANCE,
            tolerance,
        )
        print(f"fix() returned: {changed}")
    except Exception as exc:
        raise RuntimeError(f"shape.fix() failed: {exc}")

    stats("AFTER FIX", shape)

    # ----------------------------------------------------------
    # Get/create solids
    # ----------------------------------------------------------

    if shape.Solids:
        print(
            f"\nShape already contains "
            f"{len(shape.Solids)} solid(s)."
        )

        solids = [
            solid.copy()
            for solid in shape.Solids
        ]

    else:
        shells = list(shape.Shells)

        if not shells:
            raise RuntimeError(
                "Repaired shape contains neither solids nor shells"
            )

        print(
            f"\nChecking {len(shells)} shell(s) ..."
        )

        open_shells = []

        for i, shell in enumerate(shells, 1):
            print(
                f"  shell {i:03d}: "
                f"closed={shell.isClosed()} "
                f"faces={len(shell.Faces)}"
            )

            if not shell.isClosed():
                open_shells.append(i)

        if open_shells:
            raise RuntimeError(
                f"{len(open_shells)} shell(s) remain open: "
                + ", ".join(map(str, open_shells))
                + f"\nCurrent tolerance: {tolerance} mm"
                + "\nTry 0.02 or 0.05 mm."
            )

        print("\nConverting closed shells to solids ...")

        solids = []

        for i, shell in enumerate(shells, 1):
            try:
                solid = Part.makeSolid(shell)
            except Exception as exc:
                raise RuntimeError(
                    f"Could not create solid from shell {i}: {exc}"
                )

            solid_stats(
                f"  solid {i:03d}",
                solid,
            )

            solids.append(solid)

    # ----------------------------------------------------------
    # Validate solids, but DO NOT modify them further.
    # ----------------------------------------------------------

    print(
        f"\nValidating {len(solids)} solid(s) ..."
    )

    for i, solid in enumerate(solids, 1):
        solid_stats(
            f"  part {i:03d}",
            solid,
        )

        errors = validate_solid(solid)

        if errors:
            raise RuntimeError(
                f"Solid {i} failed validation:\n  - "
                + "\n  - ".join(errors)
            )

    return solids


def export_step(solids, output_file):
    """
    OLD / PROVEN Bambu-compatible STEP export.

    One STEP TopoShape containing multiple solids.

    This is deliberately NOT Import.export([...]).
    """

    print("\nCreating STEP compound ...")

    if len(solids) == 1:
        final_shape = solids[0]
    else:
        final_shape = Part.makeCompound(solids)

    print(
        f"Compound contains "
        f"{len(final_shape.Solids)} solid(s)"
    )

    if len(final_shape.Solids) != len(solids):
        raise RuntimeError(
            "Solid count changed while creating STEP compound: "
            f"{len(solids)} -> {len(final_shape.Solids)}"
        )

    temp_file = output_file + ".tmp.step"

    if os.path.exists(temp_file):
        os.unlink(temp_file)

    print(f"\nWriting STEP:\n  {output_file}")

    try:
        final_shape.exportStep(temp_file)
    except Exception as exc:
        raise RuntimeError(
            f"STEP export failed: {exc}"
        )

    # ----------------------------------------------------------
    # Round-trip verification
    # ----------------------------------------------------------

    print("\nRe-reading exported STEP ...")

    verification = Part.Shape()

    try:
        verification.read(temp_file)
    except Exception as exc:
        raise RuntimeError(
            f"Could not re-read exported STEP: {exc}"
        )

    if verification.isNull():
        raise RuntimeError(
            "Exported STEP re-imported as null shape"
        )

    stats(
        "EXPORTED STEP CHECK",
        verification,
    )

    if len(verification.Solids) != len(solids):
        raise RuntimeError(
            "Solid count changed during STEP round-trip: "
            f"{len(solids)} -> "
            f"{len(verification.Solids)}"
        )

    for i, solid in enumerate(
        verification.Solids,
        1,
    ):
        errors = validate_solid(solid)

        if errors:
            raise RuntimeError(
                f"Exported solid {i} failed validation:\n  - "
                + "\n  - ".join(errors)
            )

    os.replace(
        temp_file,
        output_file,
    )

    print()
    print("=" * 70)
    print("SUCCESS — STEP")
    print("=" * 70)
    print(f"Output: {output_file}")
    print(f"Solids: {len(solids)}")
    print()
    print(
        "Bambu Studio: use Split -> To Parts "
        "if required."
    )


def export_stls(solids, input_file):
    """
    Export every repaired solid as its own STL.

    All solids keep their original global CAD coordinates.

    Import ALL generated STL files simultaneously in Bambu Studio
    and choose to load them as one multi-part object.
    """

    directory = os.path.dirname(input_file)

    filename = os.path.basename(input_file)
    stem = os.path.splitext(filename)[0]

    output_dir = os.path.join(
        directory,
        f"{stem}_repaired_parts",
    )

    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    print()
    print("=" * 70)
    print("STL MULTI-PART EXPORT")
    print("=" * 70)
    print(f"Directory: {output_dir}")
    print(f"Parts:     {len(solids)}")
    print()

    output_files = []

    for i, solid in enumerate(solids, 1):
        output_file = os.path.join(
            output_dir,
            f"{stem}_repaired_part_{i:03d}.stl",
        )

        print(
            f"Meshing part {i:03d} -> "
            f"{os.path.basename(output_file)}"
        )

        try:
            vertices, triangles = solid.tessellate(
                LINEAR_DEFLECTION,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Tessellation of part {i} failed: {exc}"
            )

        if not vertices or not triangles:
            raise RuntimeError(
                f"Tessellation of part {i} produced no triangles"
            )

        mesh = Mesh.Mesh()

        facets = []

        for triangle in triangles:
            a, b, c = triangle

            va = vertices[a]
            vb = vertices[b]
            vc = vertices[c]

            facets.append(
                (
                    App.Vector(va.x, va.y, va.z),
                    App.Vector(vb.x, vb.y, vb.z),
                    App.Vector(vc.x, vc.y, vc.z),
                )
            )

        mesh.addFacets(facets)

        print(
            f"  triangles: {mesh.CountFacets}"
        )

        # These tests are diagnostic. We abort on non-manifold
        # meshes because the purpose of --stl is specifically to
        # avoid handing broken tessellation to Bambu.
        try:
            non_manifold = mesh.hasNonManifolds()
        except Exception:
            non_manifold = None

        try:
            mesh_solid = mesh.isSolid()
        except Exception:
            mesh_solid = None

        print(
            f"  mesh solid:   {mesh_solid}"
        )
        print(
            f"  non-manifold: {non_manifold}"
        )

        if non_manifold is True:
            raise RuntimeError(
                f"Part {i} tessellated to a non-manifold mesh"
            )

        try:
            mesh.write(output_file)
        except Exception as exc:
            raise RuntimeError(
                f"Could not write STL part {i}: {exc}"
            )

        output_files.append(output_file)

    print()
    print("=" * 70)
    print("SUCCESS — STL PARTS")
    print("=" * 70)

    print(
        f"Created {len(output_files)} files in:"
    )
    print(
        f"  {output_dir}"
    )

    print()
    print("Bambu Studio:")
    print("  1. Select ALL generated STL files")
    print("  2. Drag/import them together")
    print("  3. Choose YES when asked to load")
    print("     them as one multi-part object")
    print("  4. Assign filament per part")
    print()
    print(
        "Do NOT use Split -> To Objects."
    )


def parse_arguments():
    args = sys.argv[1:]

    stl_mode = False
    tolerance = DEFAULT_TOLERANCE

    # Wrapper supplies:
    #
    # default:
    #   repair_step.py input.stp output.stp
    #
    # STL:
    #   repair_step.py --stl input.stp output.stp
    #
    # Optional tolerance:
    #   repair_step.py input.stp output.stp 0.05
    #   repair_step.py --stl input.stp output.stp 0.05

    if "--stl" in args:
        stl_mode = True
        args.remove("--stl")

    if len(args) not in (2, 3):
        print(
            "Usage:",
            file=sys.stderr,
        )
        print(
            f"  {sys.argv[0]} "
            "[--stl] input.step output.step [tolerance_mm]",
            file=sys.stderr,
        )
        sys.exit(2)

    input_file = os.path.abspath(args[0])
    output_file = os.path.abspath(args[1])

    if len(args) == 3:
        try:
            tolerance = float(args[2])
        except ValueError:
            print(
                f"ERROR: invalid tolerance: {args[2]}",
                file=sys.stderr,
            )
            sys.exit(2)

    if tolerance <= 0:
        print(
            "ERROR: tolerance must be > 0",
            file=sys.stderr,
        )
        sys.exit(2)

    return (
        input_file,
        output_file,
        tolerance,
        stl_mode,
    )


def main():
    (
        input_file,
        output_file,
        tolerance,
        stl_mode,
    ) = parse_arguments()

    if not os.path.isfile(input_file):
        print(
            f"ERROR: input file does not exist:\n"
            f"  {input_file}",
            file=sys.stderr,
        )
        return 2

    print("=" * 70)
    print("STEP REPAIR V3")
    print("=" * 70)

    print(f"Input:      {input_file}")
    print(f"Tolerance:  {tolerance} mm")
    print(
        f"Mode:       "
        f"{'STL MULTI-PART' if stl_mode else 'STEP'}"
    )

    try:
        solids = repair_shape(
            input_file,
            tolerance,
        )

        if stl_mode:
            export_stls(
                solids,
                input_file,
            )
        else:
            export_step(
                solids,
                output_file,
            )

    except Exception as exc:
        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
