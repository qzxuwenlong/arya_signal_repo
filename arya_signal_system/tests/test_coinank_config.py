import os

from src.config import use_coinank_enrichment
from src.scanner import run_scan


def test_use_coinank_enrichment_defaults_to_false(monkeypatch):
    monkeypatch.delenv('ARYA_USE_COINANK', raising=False)
    monkeypatch.delenv('ARYA_DERIVATIVES_MODE', raising=False)

    assert use_coinank_enrichment() is False


def test_use_coinank_enrichment_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv('ARYA_USE_COINANK', '1')
    monkeypatch.delenv('ARYA_DERIVATIVES_MODE', raising=False)
    assert use_coinank_enrichment() is True

    monkeypatch.setenv('ARYA_USE_COINANK', '0')
    monkeypatch.setenv('ARYA_DERIVATIVES_MODE', 'okx_coinank')
    assert use_coinank_enrichment() is True

    monkeypatch.setenv('ARYA_DERIVATIVES_MODE', 'okx_only')
    monkeypatch.setenv('ARYA_USE_COINANK', '1')
    assert use_coinank_enrichment() is False


def test_run_scan_disables_coinank_by_default_even_when_key_exists(monkeypatch):
    monkeypatch.setenv('COINANK_API_KEY', 'test-key-not-used')
    monkeypatch.delenv('ARYA_USE_COINANK', raising=False)
    monkeypatch.delenv('ARYA_DERIVATIVES_MODE', raising=False)

    result = run_scan(limit=1, use_live=False)

    assert result['source_status']['coinank'] == 'disabled_by_config'
    assert result['source_status']['coinank_enrichment'] == 'disabled_by_config'


def test_run_scan_marks_coinank_opt_in_missing_key(monkeypatch):
    monkeypatch.setenv('ARYA_USE_COINANK', '1')
    monkeypatch.delenv('ARYA_DERIVATIVES_MODE', raising=False)
    monkeypatch.delenv('COINANK_API_KEY', raising=False)
    monkeypatch.delenv('COINANK_APIKEY', raising=False)

    result = run_scan(limit=1, use_live=False)

    assert result['source_status']['coinank'] == 'missing_key'
    assert result['source_status']['coinank_enrichment'] == 'missing_key'

