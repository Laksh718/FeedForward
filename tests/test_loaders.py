"""Every dataset loads and matches its schema."""

import pytest

from feedforward.data.loaders import SchemaError, load_all, load_table


def test_all_tables_load():
    tables = load_all()
    assert len(tables["calendar"]) == 365
    assert len(tables["weather"]) == 365
    assert len(tables["kitchen_history"]) == 15745
    assert len(tables["kitchen_history_raw"]) == 15760


def test_unknown_table_rejected():
    with pytest.raises(KeyError):
        load_table("nope")


def test_missing_column_detected(monkeypatch, tmp_path):
    from feedforward.data import loaders
    from feedforward.data.schemas import TableSpec

    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setitem(loaders.TABLES, "bad", TableSpec(bad, ("a", "b", "c")))
    with pytest.raises(SchemaError):
        load_table("bad")
