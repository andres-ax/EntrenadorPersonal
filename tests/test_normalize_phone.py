"""Tests de normalización E.164 para teléfonos colombianos."""
import pytest

from src.services.identity import normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("3044093197", "+573044093197"),
        ("573044093197", "+573044093197"),
        ("+573044093197", "+573044093197"),
        ("+57573044093197", "+573044093197"),
        ("57573044093197", "+573044093197"),
        ("+57 304 409 3197", "+573044093197"),
    ],
)
def test_normalize_phone_colombia(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected
