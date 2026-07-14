import numpy as np
from pdgraster import WebImage


def test_webimage_save_png_with_safe_palette(tmp_path):
    data = np.arange(16, dtype=float).reshape(4, 4)
    wi = WebImage(
        image_data=data,
        palette=(["#663399", "#ffcc00", "#ffff00"], "#ffffff00"),
        min_val=0.0,
        max_val=15.0,
        nodata_val=None,
    )
    out = tmp_path / "tile.png"
    wi.save(str(out))
    assert out.exists() and out.stat().st_size > 0
