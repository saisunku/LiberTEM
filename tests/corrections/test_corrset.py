import numpy as np
import pytest
import sparse

from libertem.corrections import CorrectionSet
from libertem.udf.sum import SumUDF


@pytest.mark.parametrize("gain,dark", [
    (np.zeros((128, 128)), np.ones((128, 128))),
    (np.zeros((128, 128)), None),
])
def test_correction_set_zero_gain(lt_ctx, default_raw, gain, dark):
    udf = SumUDF()

    corr = CorrectionSet(dark=dark, gain=gain)
    res = lt_ctx.run_udf(
        dataset=default_raw,
        udf=udf,
        corrections=corr
    )
    assert np.allclose(res['intensity'], 0)


@pytest.mark.parametrize("gain,dark", [
    (np.ones((128, 128)), np.ones((128, 128))),
    (None, np.ones((128, 128))),
])
def test_correction_set_dark_one(lt_ctx, default_raw, default_raw_data, gain, dark):
    udf = SumUDF()

    corr = CorrectionSet(dark=dark, gain=gain)
    res = lt_ctx.run_udf(
        dataset=default_raw,
        udf=udf,
        corrections=corr
    )
    assert np.allclose(res['intensity'], np.sum(default_raw_data - 1, axis=(0, 1)))


def test_patch_pixels(lt_ctx, default_raw, default_raw_data):
    udf = SumUDF()

    # test with empty excluded_pixels array
    corr = CorrectionSet(excluded_pixels=np.array([
        (), ()
    ]).astype(np.int64), gain=np.ones((128, 128)))
    res = lt_ctx.run_udf(
        dataset=default_raw,
        udf=udf,
        corrections=corr
    )
    assert np.allclose(res['intensity'], np.sum(default_raw_data, axis=(0, 1)))


def test_patch_pixels_only_excluded_pixels(lt_ctx, default_raw, default_raw_data):
    udf = SumUDF()
    excluded_pixels = sparse.COO(
        np.zeros((128, 128))
    )
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    res = lt_ctx.run_udf(
        dataset=default_raw,
        udf=udf,
        corrections=corr
    )
    assert np.allclose(res['intensity'], np.sum(default_raw_data, axis=(0, 1)))


def test_tileshape_adjustment_1():
    sig_shape = (123, 456)
    tile_shape = (17, 42)
    base_shape = (1, 1)
    excluded_coords = np.array([
        (17, ),
        (42, )
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    assert adjusted == (16, 41)


def test_tileshape_adjustment_2():
    sig_shape = (123, 456)
    tile_shape = (17, 42)
    base_shape = (1, 1)
    excluded_coords = np.array([
        (17*2 - 1, ),
        (42, )
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    assert adjusted == (15, 41)


def test_tileshape_adjustment_3():
    sig_shape = (123, 456)
    tile_shape = (17, 42)
    base_shape = (1, 1)
    excluded_coords = np.array([
        (122, ),
        (23, )
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    assert adjusted == (17, 42)


def test_tileshape_adjustment_4():
    sig_shape = (123, 456)
    tile_shape = (17, 1)
    base_shape = (1, 1)
    excluded_coords = np.array([
        (122, ),
        (0, )
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    assert adjusted == (17, 2)


def test_tileshape_adjustment_5():
    sig_shape = (123, 1)
    tile_shape = (17, 1)
    base_shape = (1, 1)
    excluded_coords = np.array([
        (122, ),
        (0, )
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    assert adjusted == (17, 1)


def test_tileshape_adjustment_6():
    sig_shape = (123, 456)
    tile_shape = (17, 1)
    base_shape = (1, 1)
    excluded_coords = np.array([
        (range(123)),
        np.zeros(123, dtype=int)
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    # Switch to full frames since there's no tiling solution
    assert adjusted == (123, 456)


def test_tileshape_adjustment_7():
    sig_shape = (123, 456)
    tile_shape = (14, 42)
    base_shape = (7, 1)
    excluded_coords = np.array([
        (14, ),
        (42, )
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    assert adjusted == (21, 41)


def test_tileshape_adjustment_8():
    sig_shape = (1014, 1024)
    tile_shape = (1, 1)
    base_shape = (1, 1)
    # These magic numbers are "worst case" to produce collisions
    # 2*3*4*5*6*7
    excluded_coords = np.array([
        (720, 210, 306),
        (120, 210, 210)
    ])
    excluded_pixels = sparse.COO(coords=excluded_coords, shape=sig_shape, data=True)
    corr = CorrectionSet(excluded_pixels=excluded_pixels)
    adjusted = corr.adjust_tileshape(
        tile_shape=tile_shape, sig_shape=sig_shape, base_shape=base_shape
    )
    print(adjusted)
    assert adjusted != (1014, 1024)
