import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
from shapely.geometry import box

from pdgraster.operations import (
    calculate_ranges,
    compose_parent,
    rasterize_tile,
    render_web_tile,
)


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


def test_rasterize_tile_produces_readable_geotiff(tmp_path):
    source, output = tmp_path / "source.gpkg", tmp_path / "tile.tif"
    gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)], crs="EPSG:3857").to_file(source)
    result = rasterize_tile(
        source,
        output,
        bounds={"left": 0, "right": 1, "bottom": 0, "top": 1},
        shape=(2, 2),
        centroid_properties=None,
        statistics=[
            {
                "name": "count",
                "weight_by": "count",
                "property": "centroids_per_pixel",
                "aggregation_method": "sum",
            }
        ],
    )

    assert result == output
    with rasterio.open(output) as dataset:
        assert dataset.count == 1
        data = dataset.read(1)
    assert data.min() == 0 and data.max() == 1 and data.sum() == 1


def test_compose_parent_reads_only_supplied_children(tmp_path):
    child, ignored, output = (
        tmp_path / "child.tif",
        tmp_path / "ignored.tif",
        tmp_path / "parent.tif",
    )
    _tif(child, np.ones((1, 2, 2), dtype=np.uint8))
    ignored.write_text("not a raster")

    result = compose_parent(
        [child],
        output,
        bounds={"left": 0, "right": 1, "bottom": 0, "top": 1},
        shape=(2, 2),
        resampling="nearest",
    )

    assert result == output
    assert rasterio.open(output).read(1).tolist() == [[1, 1], [1, 1]]


def _tif_nodata(path, data, nodata=None):
    data = np.asarray(data)
    count, height, width = data.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=count,
        dtype=data.dtype.name,
        crs="EPSG:3857",
        transform=from_bounds(0, 0, 1, 1, width, height),
        nodata=nodata,
    ) as dataset:
        dataset.write(data)


def test_calculate_ranges_stable_under_input_reorder(tmp_path):
    first = tmp_path / "first.tif"
    second = tmp_path / "second.tif"
    _tif_nodata(first, np.array([[[2, 5], [3, 4]], [[10, 12], [11, 13]]]))
    _tif_nodata(second, np.array([[[1, 9], [3, 4]], [[10, 20], [11, 13]]]))

    assert calculate_ranges([second, first]) == calculate_ranges([first, second])
    assert calculate_ranges([first, second]) == [(1.0, 9.0), (10.0, 20.0)]


def test_calculate_ranges_honors_nodata_and_valid_zero(tmp_path):
    path = tmp_path / "tile.tif"
    _tif_nodata(
        path,
        np.array([[[0, 5], [np.nan, 3]], [[0, 255], [7, 255]]], dtype="float64"),
        nodata=255,
    )

    assert calculate_ranges([path]) == [(0.0, 5.0), (0.0, 7.0)]


def test_calculate_ranges_rejects_band_count_mismatch(tmp_path):
    one = tmp_path / "one.tif"
    two = tmp_path / "two.tif"
    _tif_nodata(one, np.ones((1, 2, 2), dtype=np.uint8))
    _tif_nodata(two, np.ones((2, 2, 2), dtype=np.uint8))

    with pytest.raises(ValueError, match="band count"):
        calculate_ranges([one, two])


def test_calculate_ranges_fails_with_no_valid_range(tmp_path):
    path = tmp_path / "empty.tif"
    _tif_nodata(path, np.full((1, 2, 2), 255, dtype=np.uint8), nodata=255)

    with pytest.raises(ValueError, match="no valid"):
        calculate_ranges([path])


def test_overwrite_false_reuses_valid_output(tmp_path, monkeypatch):
    from pdgraster import operations

    child, output = tmp_path / "child.tif", tmp_path / "parent.tif"
    _tif(child, np.ones((1, 2, 2), dtype=np.uint8))
    kwargs = {
        "bounds": {"left": 0, "right": 1, "bottom": 0, "top": 1},
        "shape": (2, 2),
        "resampling": "nearest",
    }
    calls = []
    real = operations.Raster.from_rasters

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(operations.Raster, "from_rasters", counting)
    assert compose_parent([child], output, **kwargs) == output
    assert len(calls) == 1
    assert compose_parent([child], output, **kwargs) == output
    assert len(calls) == 1
    assert compose_parent([child], output, overwrite=True, **kwargs) == output
    assert len(calls) == 2


def test_overwrite_false_regenerates_invalid_output(tmp_path):
    child, output = tmp_path / "child.tif", tmp_path / "parent.tif"
    _tif(child, np.ones((1, 2, 2), dtype=np.uint8))
    output.write_bytes(b"not a raster")

    result = compose_parent(
        [child],
        output,
        bounds={"left": 0, "right": 1, "bottom": 0, "top": 1},
        shape=(2, 2),
        resampling="nearest",
    )

    assert result == output
    assert rasterio.open(output).read(1).tolist() == [[1, 1], [1, 1]]


def test_failed_write_leaves_no_final_output(tmp_path, monkeypatch):
    from pdgraster import operations

    child, output = tmp_path / "child.tif", tmp_path / "parent.tif"
    _tif(child, np.ones((1, 2, 2), dtype=np.uint8))
    real_write = operations.Raster.write

    def fail_write(self, path):
        real_write(self, path)
        raise RuntimeError("boom")

    monkeypatch.setattr(operations.Raster, "write", fail_write)
    with pytest.raises(RuntimeError, match="boom"):
        compose_parent(
            [child],
            output,
            bounds={"left": 0, "right": 1, "bottom": 0, "top": 1},
            shape=(2, 2),
            resampling="nearest",
        )

    assert not output.exists()
    assert list(tmp_path.glob(".parent.tmp*")) == []


def test_render_web_tile_uses_explicit_range_and_style(tmp_path):
    source, output = tmp_path / "source.tif", tmp_path / "tile.png"
    _tif(source, np.arange(4, dtype=np.uint8).reshape(1, 2, 2))

    result = render_web_tile(
        source,
        output,
        band=1,
        value_range=(0, 3),
        palette=(["#000000", "#ffffff"], "#00000000"),
        nodata=None,
    )

    assert result == output
    with Image.open(output) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (0, 0, 0, 255)
        assert image.getpixel((1, 1)) == (254, 254, 254, 255)


def test_render_web_tile_preserves_constant_band(tmp_path):
    source, output = tmp_path / "source.tif", tmp_path / "tile.png"
    _tif(source, np.full((1, 2, 2), 5, dtype=np.uint8))

    result = render_web_tile(
        source,
        output,
        band=1,
        value_range=(5, 5),
        palette=(["#000000", "#ffffff"], "#00000000"),
        nodata=None,
    )

    assert result == output
    with Image.open(output) as image:
        pixels = [image.getpixel((x, y)) for x in range(2) for y in range(2)]
    assert len(set(pixels)) == 1
