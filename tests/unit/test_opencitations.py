# SPDX-License-Identifier: MIT
"""Unit tests for OpenCitations client factory."""

from __future__ import annotations

import importlib
import types

import pytest

from aletheia_probe.opencitations import (
    OpenCitationsClient,
    create_opencitations_client,
)


def test_create_opencitations_client_defaults_to_remote(monkeypatch) -> None:
    """Factory should return remote client when no local mode is requested."""
    monkeypatch.delenv("OPENCITATIONS_MODE", raising=False)
    client = create_opencitations_client()
    assert isinstance(client, OpenCitationsClient)


def test_create_opencitations_client_local_requires_adapter(monkeypatch) -> None:
    """Local mode raises clear ImportError when adapter package is missing."""
    monkeypatch.setenv("OPENCITATIONS_MODE", "local")

    real_import_module = importlib.import_module

    def fail_adapter_import(name: str, package: str | None = None):
        if name == "aletheia_opencitations_adapter":
            raise ImportError("missing adapter")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fail_adapter_import)

    with pytest.raises(ImportError, match="OPENCITATIONS_MODE=local requires"):
        create_opencitations_client()


def test_create_opencitations_client_local_uses_adapter(monkeypatch) -> None:
    """Local mode should delegate client creation to adapter factory."""
    monkeypatch.setenv("OPENCITATIONS_MODE", "local")

    adapter_module = types.SimpleNamespace()
    adapter_module.create_opencitations_client = lambda mode="local": {
        "mode": mode,
        "kind": "adapter-client",
    }

    real_import_module = importlib.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "aletheia_opencitations_adapter":
            return adapter_module
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    client = create_opencitations_client()
    assert client == {"mode": "local", "kind": "adapter-client"}
