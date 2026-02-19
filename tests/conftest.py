"""Shared test fixtures."""

import pytest

from digirails.crypto.keys import generate_keypair
from digirails.network.params import MAINNET, REGTEST


@pytest.fixture
def mainnet_keypair():
    return generate_keypair(MAINNET)


@pytest.fixture
def regtest_keypair():
    return generate_keypair(REGTEST)
