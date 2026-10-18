"""Test minimal : le paquet s'importe et expose sa version."""

import nkap


def test_package_exposes_version() -> None:
    assert nkap.__version__ == "0.1.0"
