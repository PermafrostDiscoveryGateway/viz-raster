import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

from .Raster import Raster


def _temp_sibling(output):
    """Return the hidden temp path used for atomic writes next to output.

    Parameters
    ----------
    output : str or pathlib.Path
        Final destination path the temp file sits beside.

    Returns
    -------
    pathlib.Path
        Sibling path with a leading-dot ``.tmp`` name and the same suffix.
    """
    output = Path(output)
    return output.with_name(f".{output.stem}.tmp{output.suffix}")


def _valid_raster(path):
    """Check whether a path is a non-empty, readable raster file.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to check.

    Returns
    -------
    bool
        True only if the file exists, is non-empty, and opens via Raster.
    """
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        return False
    try:
        Raster.from_file(str(path))
    except Exception:
        return False
    return True


def _valid_image(path):
    """Check whether a path is a non-empty, loadable image file.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to check.

    Returns
    -------
    bool
        True only if the file exists, is non-empty, and loads via PIL.
    """
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        return False
    try:
        with Image.open(path) as image:
            image.load()
    except Exception:
        return False
    return True


def _produce(output, overwrite, is_valid, produce):
    """Write output atomically via a temp sibling, skipping valid outputs.

    Parameters
    ----------
    output : str or pathlib.Path
        Final destination path.
    overwrite : bool
        When False, return an already-valid output without rewriting it.
    is_valid : callable
        Predicate taking a path and returning True when it needs no rewrite.
    produce : callable
        Callback taking a temp path and writing the new artifact there.

    Returns
    -------
    pathlib.Path
        Path to the final output file.

    Raises
    ------
    Exception
        Re-raises any error from ``produce`` after removing temp output
        (and removing a previously invalid destination).
    """
    output = Path(output)
    if not overwrite and is_valid(output):
        return Path(output)
    had_valid = is_valid(output)
    temp = _temp_sibling(output)
    try:
        produce(temp)
        output.parent.mkdir(parents=True, exist_ok=True)
        temp.replace(output)
    except Exception:
        temp.unlink(missing_ok=True)
        if not had_valid:
            output.unlink(missing_ok=True)
        raise
    return Path(output)


def rasterize_tile(
    input_path,
    output_path,
    *,
    bounds,
    shape,
    centroid_properties,
    statistics,
    overwrite=False,
):
    """Rasterize a vector file into a tile raster, skipping valid outputs.

    Parameters
    ----------
    input_path : str or pathlib.Path
        Source vector file to rasterize.
    output_path : str or pathlib.Path
        Destination raster file.
    bounds : dict
        Raster bounds with keys ``left``, ``right``, ``bottom``, ``top``.
    shape : tuple of int
        Output ``(height, width)`` in pixels.
    centroid_properties : list or None
        Point properties passed through to ``Raster.from_vector``.
    statistics : dict or list
        Per-band statistics config passed as ``stats`` to ``Raster.from_vector``.
    overwrite : bool, optional
        Rewrite even when the destination is already a valid raster.

    Returns
    -------
    pathlib.Path
        Path to the written (or skipped, still valid) raster file.
    """
    def produce(temp):
        raster = Raster.from_vector(
            str(input_path),
            centroid_properties=centroid_properties,
            bounds=bounds,
            shape=tuple(shape),
            stats=statistics,
        )
        raster.write(str(temp))
        Raster.from_file(str(temp))

    return _produce(output_path, overwrite, _valid_raster, produce)


def compose_parent(
    child_paths, output_path, *, bounds, shape, resampling, overwrite=False
):
    """Merge explicit child rasters into one parent tile, skipping valid outputs.

    Parameters
    ----------
    child_paths : list of str or pathlib.Path
        Child raster files to merge; must all exist.
    output_path : str or pathlib.Path
        Destination parent raster file.
    bounds : dict
        Raster bounds with keys ``left``, ``right``, ``bottom``, ``top``.
    shape : tuple of int
        Output ``(height, width)`` in pixels.
    resampling : str or sequence of str
        Resampling method(s) passed to ``Raster.from_rasters``.
    overwrite : bool, optional
        Rewrite even when the destination is already a valid raster.

    Returns
    -------
    pathlib.Path
        Path to the written (or skipped, still valid) raster file.
    """
    children = [Path(path) for path in child_paths]
    if not children or any(not path.is_file() for path in children):
        raise ValueError("child_paths must be an explicit list of raster files")

    def produce(temp):
        raster = Raster.from_rasters(
            [str(path) for path in children],
            resampling_methods=(
                (resampling,) if isinstance(resampling, str) else tuple(resampling)
            ),
            shape=tuple(shape),
            bounds=bounds,
        )
        raster.write(str(temp))
        Raster.from_file(str(temp))

    return _produce(output_path, overwrite, _valid_raster, produce)


def calculate_ranges(raster_paths):
    """Compute per-band (min, max) over rasters, ignoring nodata and NaN.

    Parameters
    ----------
    raster_paths : list of str or pathlib.Path
        Raster files to scan; must be non-empty with matching band counts.

    Returns
    -------
    list of tuple
        One ``(low, high)`` pair per band, in band order.
    """
    paths = [Path(path) for path in raster_paths]
    if not paths:
        raise ValueError("raster_paths must not be empty")
    count, lows, highs = None, [], []
    for path in paths:
        with rasterio.open(path) as source:
            if count is None:
                count = source.count
                lows = [math.inf] * count
                highs = [-math.inf] * count
            elif source.count != count:
                raise ValueError(
                    f"band count mismatch: {path} has {source.count} bands, "
                    f"expected {count}"
                )
            for band in range(1, count + 1):
                tile = source.read(band, masked=True)
                valid = tile.compressed().astype("float64")
                valid = valid[np.isfinite(valid)]
                if valid.size:
                    lows[band - 1] = min(lows[band - 1], float(valid.min()))
                    highs[band - 1] = max(highs[band - 1], float(valid.max()))
    ranges = []
    for index, (low, high) in enumerate(zip(lows, highs), start=1):
        if low == math.inf:
            raise ValueError(f"band {index} has no valid samples")
        ranges.append((low, high))
    return ranges


from .Palette import Palette
from .WebImage import WebImage


def render_web_tile(
    input_path, output_path, *, band, value_range, palette, nodata, overwrite=False
):
    """Style one raster band as a web image, skipping valid outputs.

    Parameters
    ----------
    input_path : str or pathlib.Path
        Source raster file.
    output_path : str or pathlib.Path
        Destination image file.
    band : int
        1-based band index to render.
    value_range : pair or dict
        Finite ``(min, max)`` pair, or a dict with ``min``/``max`` keys.
    palette : Palette, dict, or sequence
        Style for values; dicts take ``colors`` plus optional ``nodata_color``.
    nodata : value or None
        Nodata value passed through to the web image.
    overwrite : bool, optional
        Rewrite even when the destination is already a valid image.

    Returns
    -------
    pathlib.Path
        Path to the written (or skipped, still valid) image file.
    """
    def produce(temp):
        raster = Raster.from_file(str(input_path))
        if band < 1 or band > raster.count:
            raise ValueError(f"Invalid band: {band}")
        if isinstance(value_range, dict):
            minimum, maximum = value_range["min"], value_range["max"]
        else:
            minimum, maximum = value_range
        try:
            bounded = math.isfinite(minimum) and math.isfinite(maximum)
        except TypeError:
            bounded = False
        if not bounded:
            raise ValueError("value_range must be a finite (min, max) pair")
        if isinstance(palette, Palette):
            style = palette
        elif isinstance(palette, dict):
            style = Palette(palette["colors"], palette.get("nodata_color"))
        else:
            style = Palette(*palette)
        WebImage(raster.data[band - 1], style, minimum, maximum, nodata).save(
            str(temp)
        )
        with Image.open(temp) as image:
            image.load()

    return _produce(output_path, overwrite, _valid_image, produce)
