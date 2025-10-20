import numpy as np
import rasterio
from rasterio.transform import from_bounds
from pdgraster.Raster import Raster 

def _make_tif(path, arr, *, bounds=(0, 0, 3, 3), crs=None, descs=("a", "b")):
    h, w = arr.shape[1], arr.shape[2]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=arr.shape[0],
        dtype=arr.dtype,
        crs=crs,
        transform=from_bounds(*bounds, width=w, height=h),
    ) as ds:
        ds.write(arr)
        ds.descriptions = descs


def test_from_file_and_summary(tmp_path):
   # Smoke test: Raster.from_file reads data and computes summary stats.
    arr = np.stack(
        [
            np.arange(9, dtype=np.uint8).reshape(3, 3),  # band 0: 0..8
            np.full((3, 3), 5, dtype=np.uint8),          # band 1: all 5s
        ]
    )
    p = tmp_path / "known.tif"
    _make_tif(p, arr, crs=None, bounds=(0, 0, 3, 3), descs=("count", "coverage"))

    r = Raster.from_file(str(p))
    assert r.count == 2
    assert r.descriptions == ("count", "coverage")

    s = r.summary
    assert s["min"][0] == 0
    assert s["max"][0] == 8
    assert s["sum"][0] == int(arr[0].sum())
    assert s["min"][1] == 5
    assert s["max"][1] == 5
    assert s["sum"][1] == int(arr[1].sum())


def test_from_rasters_merge_and_resample(tmp_path):
   #  Merge and resample two small rasters.
    a1 = np.zeros((2, 16, 16), dtype=np.uint8)
    a2 = np.ones((2, 16, 16), dtype=np.uint8)  
    p1 = tmp_path / "a.tif"
    p2 = tmp_path / "b.tif"

    _make_tif(p1, a1, crs="EPSG:3857", bounds=(0, 0, 2, 2), descs=("b1", "b2"))
    _make_tif(p2, a2, crs="EPSG:3857", bounds=(1, 1, 3, 3), descs=("b1", "b2"))

    r = Raster.from_rasters(
        rasters=[str(p1), str(p2)],
        resampling_methods=("nearest", "nearest"),
        shape=(8, 8),
        bounds={"left": 0, "right": 3, "bottom": 0, "top": 3},
    )

    assert r.count == 2
    assert r.shape == (8, 8)
    assert r.data.min() == 0
    assert r.data.max() == 1