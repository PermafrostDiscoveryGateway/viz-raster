import json
import subprocess
import sys

import numpy as np
import rasterio
from rasterio.transform import from_bounds


def _tif(path, data):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:3857",
        transform=from_bounds(0, 0, 1, 1, 2, 2),
    ) as dataset:
        dataset.write(data)


def test_calculate_ranges_subcommand(tmp_path):
    first, second = tmp_path / "first.tif", tmp_path / "second.tif"
    _tif(first, np.array([[[2, 2], [5, 5]]], dtype=np.uint8))
    _tif(second, np.array([[[1, 9], [1, 9]]], dtype=np.uint8))

    result = subprocess.run(
        [sys.executable, "-m", "pdgraster", "calculate-ranges", str(first), str(second)],
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [[1, 9]]


def test_render_web_tile_subcommand(tmp_path):
    source, output = tmp_path / "source.tif", tmp_path / "tile.png"
    _tif(source, np.arange(4, dtype=np.uint8).reshape(1, 2, 2))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pdgraster",
            "render-web-tile",
            str(source),
            str(output),
            "--band",
            "1",
            "--value-range",
            "[0, 3]",
            "--palette",
            '[["#000000", "#ffffff"], "#00000000"]',
            "--nodata",
            "null",
        ],
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()


def test_unknown_subcommand_fails(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "pdgraster", "not-allowed"],
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert result.returncode != 0
