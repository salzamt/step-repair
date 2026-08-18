#!/usr/bin/env python3

import sys
import os

import FreeCAD as App
import Part
import Import


SEW_TOLERANCE = 0.01  # mm
PRECISION = 1e-7
MIN_TOLERANCE = 1e-7


def stats(label, shape):
    print(f"\n{label}")
    print("-" * len(label))
    print("valid:   ", shape.isValid())
    print("solids:  ", len(shape.Solids))
    print("shells:  ", len(shape.Shells))
    print("faces:   ", len(shape.Faces))

    for i, shell in enumerate(shape.Shells, 1):
        print(
            f"  shell {i}: "
            f"closed={shell.isClosed()} "
            f"faces={len(shell.Faces)}"
        )


def main():
    if len(sys.argv) not in (3, 4):
        print(
            f"Usage: {sys.argv[0]} input.step output.step [tolerance_mm]",
            file=sys.stderr,
        )
        return 2

    input_file = os.path.abspath(sys.argv[1])
    output_file = os.path.abspath(sys.argv[2])

    tolerance = (
        float(sys.argv[3])
        if len(sys.argv) == 4
        else SEW_TOLERANCE
    )

    if not os.path.isfile(input_file):
        print(f"ERROR: input file does not exist: {input_file}", file=sys.stderr)
        return 2

    print(f"Input:      {input_file}")
    print(f"Output:     {output_file}")
    print(f"Tolerance:  {tolerance} mm")

    # ------------------------------------------------------------------
# Read STEP directly as one TopoShape
# ------------------------------------------------------------------

    print("\nReading STEP geometry ...")

    try:
        shape = Part.Shape()
        shape.read(input_file)
    except Exception as exc:
        print(f"ERROR reading STEP: {exc}", file=sys.stderr)
        return 1

    if shape.isNull():
        print("ERROR: STEP contains no geometry", file=sys.stderr)
        return 1

    stats("BEFORE REPAIR", shape)

    # ------------------------------------------------------------------
    # Sew faces / edges
    # ------------------------------------------------------------------

    print(f"\nSewing with tolerance {tolerance} mm ...")

    try:
        shape.sewShape(tolerance)
    except Exception as exc:
        print(f"ERROR during sewShape(): {exc}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------
    # OCCT shape repair
    # ------------------------------------------------------------------

    print("Running shape.fix() ...")

    try:
        result = shape.fix(
            PRECISION,
            MIN_TOLERANCE,
            tolerance,
        )
        print(f"fix() returned: {result}")
    except Exception as exc:
        print(f"ERROR during fix(): {exc}", file=sys.stderr)
        return 1

    stats("AFTER SEW + FIX", shape)

    # ------------------------------------------------------------------
    # If we already have solids, keep the repaired shape.
    #
    # Otherwise convert every closed shell to a solid.
    # ------------------------------------------------------------------

    if len(shape.Solids) > 0:
        print("\nShape already contains solid(s).")
        final_shape = shape

    else:
        shells = list(shape.Shells)

        if not shells:
            print(
                "ERROR: repaired shape contains neither solids nor shells",
                file=sys.stderr,
            )
            return 1

        open_shells = [
            shell
            for shell in shells
            if not shell.isClosed()
        ]

        if open_shells:
            print(
                f"\nERROR: {len(open_shells)} of {len(shells)} shell(s) "
                f"are still open after repair.",
                file=sys.stderr,
            )

            for i, shell in enumerate(shells, 1):
                print(
                    f"  shell {i}: "
                    f"closed={shell.isClosed()} "
                    f"faces={len(shell.Faces)}"
                )

            print(
                "\nNo STEP was written because the result would still "
                "contain open shells.",
                file=sys.stderr,
            )
            print(
                "Try a slightly larger tolerance, e.g.:\n"
                f"  FreeCADCmd {sys.argv[0]} "
                f"{sys.argv[1]} {sys.argv[2]} 0.05",
                file=sys.stderr,
            )

            return 3

        print(f"\nConverting {len(shells)} closed shell(s) to solid(s) ...")

        solids = []

        for i, shell in enumerate(shells, 1):
            try:
                solid = Part.makeSolid(shell)

                # Run the same conservative fix on the resulting solid.
                solid.fix(
                    PRECISION,
                    MIN_TOLERANCE,
                    tolerance,
                )

            except Exception as exc:
                print(
                    f"ERROR creating solid from shell {i}: {exc}",
                    file=sys.stderr,
                )
                return 1

            print(
                f"  solid {i}: "
                f"valid={solid.isValid()} "
                f"volume={solid.Volume:.3f} mm³"
            )

            if not solid.isValid():
                print(
                    f"ERROR: resulting solid {i} is invalid",
                    file=sys.stderr,
                )
                return 1

            if solid.Volume <= 0:
                print(
                    f"ERROR: resulting solid {i} has no positive volume",
                    file=sys.stderr,
                )
                return 1

            solids.append(solid)

        if len(solids) == 1:
            final_shape = solids[0]
        else:
            final_shape = Part.makeCompound(solids)

    # ------------------------------------------------------------------
    # Final validation
    # ------------------------------------------------------------------

    stats("FINAL", final_shape)

    if not final_shape.isValid():
        print(
            "\nERROR: final shape is invalid; refusing to export",
            file=sys.stderr,
        )
        return 1

    if len(final_shape.Solids) == 0:
        print(
            "\nERROR: final shape contains no solids; refusing to export",
            file=sys.stderr,
        )
        return 1

    # ------------------------------------------------------------------
    # Export STEP
    # ------------------------------------------------------------------

    output_dir = os.path.dirname(output_file)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    try:
        final_shape.exportStep(output_file)
    except Exception as exc:
        print(f"ERROR exporting STEP: {exc}", file=sys.stderr)
        return 1

    print("\nSUCCESS")
    print(f"Wrote: {output_file}")
    print(f"Solids: {len(final_shape.Solids)}")
    print(f"Faces:  {len(final_shape.Faces)}")
   # ------------------------------------------------------------------
# Export STEP while preserving individual solids as separate objects
# ------------------------------------------------------------------

#     export_doc = App.newDocument("RepairedExport")
#     export_objects = []
#
#     solids = list(final_shape.Solids)
#
#     if not solids:
#         print("ERROR: no solids to export", file=sys.stderr)
#         return 1
#
#     print(f"\nExporting {len(solids)} separate STEP object(s) ...")
#
#     for i, solid in enumerate(solids, 1):
#         obj = export_doc.addObject(
#             "Part::Feature",
#             f"Part_{i:03d}"
#         )
#
#         obj.Label = f"Part {i}"
#         obj.Shape = solid
#         export_objects.append(obj)
#
#     export_doc.recompute()
#
#     try:
#         Import.export(export_objects, output_file)
#     except Exception as exc:
#         print(f"ERROR exporting STEP: {exc}", file=sys.stderr)
#         return 1
#
#     print("\nSUCCESS")
#     print(f"Wrote: {output_file}")
#     print(f"Separate objects: {len(export_objects)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
