"""The harmonised label report: a dataset-level source is reported per dataset."""

from __future__ import annotations

from faultline.config import RunMeta
from faultline.data.common.stage import StageResult
from faultline.data.telemetry.labels import (
    HarmonisedSite,
    dataset_interval_table,
    render_harmonised_report,
)

CARE_COUNTS = {
    "farm_a anomaly": 12,
    "farm_a normal": 10,
    "farm_b anomaly": 6,
    "farm_b normal": 9,
    "farm_c anomaly": 27,
    "farm_c normal": 31,
}


def test_care_datasets_are_counted_with_and_without_farm_a() -> None:
    text = dataset_interval_table(CARE_COUNTS)
    # 22 of 45: the Wilson 95% interval runs from 35% to 63%
    assert "| anomaly | all farms | 45 | 35-63% |" in text
    assert "| anomaly | without farm A | 33 |" in text
    assert "| normal | all farms | 50 |" in text
    assert "| normal | without farm A | 40 |" in text


def test_the_label_table_leaves_a_dataset_level_source_out() -> None:
    meta = RunMeta(run_id="r", config_path="c.yaml", config_hash="h", git_sha="g")
    kelmarsh = HarmonisedSite(
        source="kelmarsh",
        turbines=1,
        steps=52596,
        events={"narrow": 10, "broad": 50},
        positives={"narrow_within_1h": 5},
        known={"narrow_within_1h": 1000},
    )
    care = HarmonisedSite(
        source="care",
        turbines=95,
        steps=52596,
        events={"narrow": 45, "broad": 45},
        dataset_level=True,
        extra={
            "care": {
                "rows": 95,
                "by farm and label": CARE_COUNTS,
                "anomaly starts inside their dataset's grid": 45,
            }
        },
    )
    details = {
        "harmonised": True,
        "sites": {"kelmarsh": kelmarsh, "care": care},
        "horizons_steps": [6],
        "rule": {"min_duration_s": 60, "narrow_causes": ["technical"]},
    }
    text = render_harmonised_report(meta, StageResult("label", 0, 0, details=details))
    label_table = text.split("## Label table")[1].split("\n## ")[0]
    assert "| kelmarsh |" in label_table
    assert "| care |" not in label_table
    assert "## care: labelled events, per dataset" in text
    assert "| anomaly | all farms | 45 | 35-63% |" in text
