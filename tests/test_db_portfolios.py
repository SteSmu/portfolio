"""Integration tests for pt.db.portfolios — uses live shared TimescaleDB."""

from __future__ import annotations

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


def test_create_then_get_returns_same_record():
    from pt.db import portfolios

    pid = portfolios.create("_test_create_get", base_currency="USD")
    try:
        row = portfolios.get(pid)
        assert row is not None
        assert row["name"] == "_test_create_get"
        assert row["base_currency"] == "USD"
        assert row["archived_at"] is None
    finally:
        portfolios.delete_hard(pid)


def test_create_uppercases_currency():
    from pt.db import portfolios

    pid = portfolios.create("_test_currency_upper", base_currency="eur")
    try:
        assert portfolios.get(pid)["base_currency"] == "EUR"
    finally:
        portfolios.delete_hard(pid)


def test_create_rejects_empty_name():
    from pt.db import portfolios

    with pytest.raises(ValueError, match="must not be empty"):
        portfolios.create("   ")


def test_archive_marks_archived_at_and_excludes_from_default_list():
    from pt.db import portfolios

    pid = portfolios.create("_test_archive_hidden")
    try:
        assert portfolios.archive(pid) is True

        # Not in default list
        all_default = portfolios.list_all()
        assert pid not in [p["id"] for p in all_default]

        # In include_archived list
        all_with_arch = portfolios.list_all(include_archived=True)
        assert pid in [p["id"] for p in all_with_arch]

        row = portfolios.get(pid)
        assert row["archived_at"] is not None
    finally:
        portfolios.delete_hard(pid)


def test_archive_returns_false_for_unknown_or_already_archived():
    from pt.db import portfolios

    assert portfolios.archive(99_999_999) is False


def test_get_by_name_returns_only_active():
    from pt.db import portfolios

    name = "_test_by_name_active"
    pid = portfolios.create(name)
    try:
        assert portfolios.get_by_name(name)["id"] == pid
        portfolios.archive(pid)
        assert portfolios.get_by_name(name) is None
    finally:
        portfolios.delete_hard(pid)
