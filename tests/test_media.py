"""Базовые unit-тесты."""
import pytest
from bot.services.media import FitMode


@pytest.mark.parametrize("fit,expected", [
    (FitMode.FIT, "fit"),
    (FitMode.CROP, "crop"),
    (FitMode.SQUARE, "square"),
])
def test_fit_mode_values(fit, expected):
    assert fit.value == expected
