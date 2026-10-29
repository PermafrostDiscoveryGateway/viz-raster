"""Thin direct subcommands over the pdgraster operations."""

import argparse
import json

from .operations import (
    calculate_ranges,
    compose_parent,
    rasterize_tile,
    render_web_tile,
)


def _json(text):
    """Parse a CLI JSON argument into Python data.

    Parameters
    ----------
    text : str
        JSON-encoded argument value.

    Returns
    -------
    object
        The decoded Python value.
    """
    return json.loads(text)


def _parser():
    """Build the CLI parser with one subcommand per operation.

    Returns
    -------
    argparse.ArgumentParser
        Parser with the calculate-ranges, rasterize-tile, compose-parent,
        and render-web-tile subcommands.
    """
    parser = argparse.ArgumentParser(description="Run a pdgraster operation")
    subs = parser.add_subparsers(dest="operation", required=True)

    ranges = subs.add_parser("calculate-ranges")
    ranges.add_argument("raster_paths", nargs="+")

    tile = subs.add_parser("rasterize-tile")
    tile.add_argument("input_path")
    tile.add_argument("output_path")
    tile.add_argument("--bounds", required=True, type=_json)
    tile.add_argument("--shape", required=True, type=_json)
    tile.add_argument("--centroid-properties", default=None, type=_json)
    tile.add_argument("--statistics", required=True, type=_json)
    tile.add_argument("--overwrite", action="store_true")

    parent = subs.add_parser("compose-parent")
    parent.add_argument("child_paths", nargs="+")
    parent.add_argument("output_path")
    parent.add_argument("--bounds", required=True, type=_json)
    parent.add_argument("--shape", required=True, type=_json)
    parent.add_argument("--resampling", required=True)
    parent.add_argument("--overwrite", action="store_true")

    web = subs.add_parser("render-web-tile")
    web.add_argument("input_path")
    web.add_argument("output_path")
    web.add_argument("--band", required=True, type=int)
    web.add_argument("--value-range", required=True, type=_json)
    web.add_argument("--palette", required=True, type=_json)
    web.add_argument("--nodata", default=None, type=_json)
    web.add_argument("--overwrite", action="store_true")
    return parser


def _dispatch(args):
    """Run the operation selected by parsed CLI args.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed arguments whose ``operation`` selects the subcommand and
        whose remaining fields map to that operation.

    Returns
    -------
    object
        The selected operation's result (output path or band ranges).
    """
    if args.operation == "rasterize-tile":
        return rasterize_tile(
            args.input_path,
            args.output_path,
            bounds=args.bounds,
            shape=tuple(args.shape),
            centroid_properties=args.centroid_properties,
            statistics=args.statistics,
            overwrite=args.overwrite,
        )
    if args.operation == "compose-parent":
        return compose_parent(
            args.child_paths,
            args.output_path,
            bounds=args.bounds,
            shape=tuple(args.shape),
            resampling=args.resampling,
            overwrite=args.overwrite,
        )
    if args.operation == "calculate-ranges":
        return calculate_ranges(args.raster_paths)
    return render_web_tile(
        args.input_path,
        args.output_path,
        band=args.band,
        value_range=args.value_range,
        palette=args.palette,
        nodata=args.nodata,
        overwrite=args.overwrite,
    )


def main(argv=None):
    """Parse args, run one operation, and print its result as JSON.

    Parameters
    ----------
    argv : list of str, optional
        Argument list (defaults to ``sys.argv``).

    Returns
    -------
    int
        0 on success.
    """
    result = _dispatch(_parser().parse_args(argv))
    print(json.dumps(result, default=str))
    return 0
