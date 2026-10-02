"""All new tests run with network access denied, even without pytest plugins."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network disabled in offline tests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
