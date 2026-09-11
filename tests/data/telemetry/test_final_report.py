"""The final stage report: a dataset-level source is counted apart, with no base rate."""

from __future__ import annotations

from faultline.config import RunMeta
from faultline.data.common.stage import StageResult
from faultline.data.telemetry.report import final_report


def test_a_dataset_level_source_is_counted_apart_without_a_base_rate() -> None:
    meta = RunMeta(run_id="r", config_path="c.yaml", config_hash="h", git_sha="g")
    details = {
        "imputed": {},
        "splits": {"test": 20},
        "outputs": {},
        "split_spec": {
            "holdout_sites": ["hill_of_towie"],
            "eval_only_sources": ["care"],
            "time": {"train_until": "2020-12-31T23:59:59Z", "val_until": "2021-12-31T23:59:59Z"},
            "late_period_split": "test",
            "windows": {"context_steps": 144, "stride_steps": 1},
        },
        "horizons_steps": [6],
        "split_windows": {
            ("test", "care"): {
                "rows": 10,
                "segments": 1,
                "windows narrow_within_1h": 8,
                "positive narrow_within_1h": 2,
            },
            ("test", "hill_of_towie"): {
                "rows": 10,
                "segments": 1,
                "windows narrow_within_1h": 9,
                "positive narrow_within_1h": 3,
            },
        },
        "split_events": {("test", "care"): {"narrow": 1}, ("test", "hill_of_towie"): {"narrow": 2}},
        "checked": {"segments": 2, "windows": 17},
        "dataset_level_sources": ["care"],
    }
    text = final_report(meta, StageResult(name="final", rows_in=20, rows_out=20, details=details))
    narrow = text.split("**Narrow label**")[1].split("**Broad label**")[0]
    assert "hill_of_towie" in narrow
    assert "care" not in narrow
    assert "| test | care | 10 | 1 | 1 | 8 |" in text.split("**Dataset-level sources**")[1]
    # CARE's 2 positives in 8 windows are never printed as a rate
    assert "(25.00%)" not in text
