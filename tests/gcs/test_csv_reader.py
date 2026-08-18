from __future__ import annotations

import pandas as pd

from iplanrio_agent_toolkit.gcs.csv_reader import GCSCSVReader


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data_envio": ["2024-01-01", "2024-02-15", "2024-03-20"],
            "status": ["ok", "pending", "ok"],
            "value": [10, 20, 30],
        }
    )


def test_exact_match_filter() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"status": "ok"})
    assert len(result) == 2


def test_gte_filter() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"value_gte": 20})
    assert len(result) == 2
    assert result["value"].tolist() == [20, 30]


def test_in_filter() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"status_in": ["ok"]})
    assert len(result) == 2


def test_not_filter() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"status_not": "ok"})
    assert len(result) == 1


def test_lt_and_gt_filters() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"value_gt": 10, "value_lt": 30})
    assert len(result) == 1


def test_unknown_column_is_ignored() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"does_not_exist": 1})
    assert len(result) == 3


def test_combined_filters() -> None:
    result = GCSCSVReader._apply_filters(_df(), {"status": "ok", "value_gte": 20})
    assert len(result) == 1
    assert result.iloc[0]["value"] == 30
