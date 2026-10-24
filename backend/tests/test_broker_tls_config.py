"""Regression tests: a ``rediss://`` broker/result URL always gets verified TLS.

Celery does not read TLS settings from URL query parameters, so a plain
``rediss://`` URL without ``broker_use_ssl``/``redis_backend_use_ssl`` config
either published unverified or was refused outright by redis-py. Both were
observed in the local demo (the API process could not dispatch to a secure
broker). The app config now attaches a certificate-verification-required
SSL context whenever the URL is ``rediss://``, with ``REDIS_SSL_CA_CERTS``
as the platform-appropriate CA-bundle override, and attaches nothing for a
plain ``redis://`` URL. There is deliberately no bypass switch.
"""

from __future__ import annotations

import ssl

import pytest


def _build_app(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]):
    """Import a fresh celery app module with the given environment."""
    import importlib
    import sys

    for name, value in (
        ("CELERY_BROKER_URL", None),
        ("REDIS_URL", None),
        ("REDIS_SSL_CA_CERTS", None),
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    saved = {k: v for k, v in sys.modules.items() if k.startswith("backend.app.worker")}
    try:
        for k in saved:
            del sys.modules[k]
        return importlib.import_module(
            "backend.app.worker.celery_app"
        )
    finally:
        # Re-importing the module elsewhere must see the original environment.
        for k, v in saved.items():
            sys.modules[k] = v


def test_rediss_url_configures_verified_tls_for_broker_and_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _build_app(monkeypatch, {"CELERY_BROKER_URL": "rediss://:redacted@broker.example:6379/0"})

    broker_tls = module.celery_app.conf.broker_use_ssl
    backend_tls = module.celery_app.conf.redis_backend_use_ssl

    # Kombu unpacks these into SSLConnection, so the value must be a kwargs
    # dict; an ssl.SSLContext fails live with "not iterable".
    assert isinstance(broker_tls, dict)
    assert isinstance(backend_tls, dict)
    assert backend_tls == broker_tls
    # No bypass: verification is always required for a rediss:// scheme.
    assert broker_tls["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert backend_tls["ssl_cert_reqs"] == ssl.CERT_REQUIRED


def test_rediss_url_honours_the_ca_bundle_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # openssl parses the CA bundle when the context is created, so point the
    # override at a real bundle (certifi ships one with the ecosystem used by
    # the local worker bootstrap).
    import certifi

    module = _build_app(
        monkeypatch,
        {
            "CELERY_BROKER_URL": "rediss://:redacted@broker.example:6379/0",
            "REDIS_SSL_CA_CERTS": certifi.where(),
        },
    )

    # The named CA bundle replaced the default system store, and verification
    # stays required.
    assert module.celery_app.conf.broker_use_ssl["ssl_ca_certs"] == certifi.where()
    assert module.celery_app.conf.broker_use_ssl["ssl_cert_reqs"] == ssl.CERT_REQUIRED


def test_plain_redis_url_sets_no_tls_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _build_app(monkeypatch, {"CELERY_BROKER_URL": "redis://localhost:6379/0"})

    # A plain redis:// URL must not silently gain TLS options.
    assert not module.celery_app.conf.broker_use_ssl
    assert not module.celery_app.conf.redis_backend_use_ssl
