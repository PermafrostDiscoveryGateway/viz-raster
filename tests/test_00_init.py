import pdgraster


def test_init():
    """The raster package imports without the staging package installed."""
    assert pdgraster.Raster is not None
