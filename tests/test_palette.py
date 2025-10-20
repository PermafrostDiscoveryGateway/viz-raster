from pdgraster.Palette import Palette

def test_palette_rgba_table_len_257_with_explicit_colors():
    pal = Palette(["#000000", "#808080", "#ffffff"], "#00000000")
    assert len(pal.rgba_list) == 257

def test_palette_get_color_shapes():
    pal = Palette(["#000000", "#808080", "#ffffff"], "#00000000")
    c0, c1 = pal.get_color(0.0), pal.get_color(1.0)
    assert len(c0) == 4 and len(c1) == 4 and c0 != c1
