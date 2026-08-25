"""Tests for the Stage 0 package foundation."""

import terminal_intelligence


def test_package_is_importable() -> None:
    """The installed package can be imported."""
    assert terminal_intelligence.__doc__
