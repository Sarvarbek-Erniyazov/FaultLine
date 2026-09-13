"""Declared fixed-boilerplate rules and the general paragraph-frequency check."""

from __future__ import annotations

from faultline.data.text.boilerplate import (
    BoilerplateConfig,
    boilerplate_counts,
    find_frequent_paragraphs,
    normalize_paragraph,
    split_paragraphs,
    strip_declared_boilerplate,
)

MODERN_DOC = (
    "EN Revision Imported Date: 7/15/2021\n"
    "EN Revision Text: NON-AGREEMENT STATE - LOST MOISTURE DENSITY GAUGE\n"
    'The following was received from the licensee via email:\n"On Monday..."\n'
    "The licensee notified the NRC Region III Office.\n"
    "THIS MATERIAL EVENT CONTAINS A 'Less than Cat 3' LEVEL OF RADIOACTIVE MATERIAL\n"
    'Sources that are "Less than IAEA Category 3 sources," are either sources that are '
    "very unlikely to cause permanent injury to individuals or contain a very small amount "
    "of radioactive material that would not cause any permanent injury. Some of these "
    "sources, such as moisture density gauges or thickness gauges that are Category 4, the "
    "amount of unshielded radioactive material, if not safely managed or securely protected, "
    "could possibly - although it is unlikely - temporarily injure someone who handled it or "
    "were otherwise in contact with it, or who were close to it for a period of many weeks. "
    "For additional information go to "
    "http://www-pub.iaea.org/MTCD/publications/PDF/Pub1227_web.pdf"
)

OLDER_DOC_WITHOUT_URL = (
    'THIS MATERIAL EVENT CONTAINS A "LESS THAN CAT 3" LEVEL OF RADIOACTIVE MATERIAL \n'
    'Sources that are "Less than IAEA Category 3 sources," are either sources that are '
    "very unlikely to cause permanent injury to individuals or contain a very small amount "
    "of radioactive material that would not cause any permanent injury. Some of these "
    "sources, such as moisture density gauges or thickness gauges that are Category 4, the "
    "amount of unshielded radioactive material, if not safely managed or securely protected, "
    "could possibly - although it is unlikely - temporarily injure someone who handled it or "
    "were otherwise in contact with it, or who were close to it for a period of many weeks."
)

BR_TAG_HEADER = (
    "EN Revision Imported Date: 12/11/2025<br><br>EN Revision Text: AGREEMENT STATE REPORT\n"
    "The following was received..."
)


def _enabled() -> BoilerplateConfig:
    return BoilerplateConfig(strip_en_revision_header=True, strip_iaea_less_than_cat3=True)


def test_disabled_by_default() -> None:
    stripped, counts = strip_declared_boilerplate(MODERN_DOC, BoilerplateConfig())
    assert stripped == MODERN_DOC
    assert counts == {}


def test_strips_en_revision_header() -> None:
    stripped, counts = strip_declared_boilerplate(MODERN_DOC, _enabled())
    assert "EN Revision Imported Date" not in stripped
    assert "EN Revision Text" not in stripped
    assert stripped.startswith("NON-AGREEMENT STATE")
    assert counts["en_revision_header"] == 1


def test_strips_en_revision_header_with_br_tag_separator() -> None:
    stripped, counts = strip_declared_boilerplate(BR_TAG_HEADER, _enabled())
    assert stripped.startswith("AGREEMENT STATE REPORT")
    assert counts["en_revision_header"] == 1


def test_strips_iaea_less_than_cat3_with_url() -> None:
    stripped, counts = strip_declared_boilerplate(MODERN_DOC, _enabled())
    assert "Pub1227_web.pdf" not in stripped
    assert "THIS MATERIAL EVENT CONTAINS" not in stripped
    assert stripped.rstrip().endswith("Region III Office.")
    assert counts["iaea_less_than_cat3"] == 1


def test_strips_iaea_less_than_cat3_without_url() -> None:
    stripped, counts = strip_declared_boilerplate(OLDER_DOC_WITHOUT_URL, _enabled())
    assert stripped.strip() == ""
    assert counts["iaea_less_than_cat3"] == 1


def test_does_not_touch_category_3_paragraph() -> None:
    # A different IAEA category (not "Less than Cat 3") must survive untouched.
    text = (
        'THIS MATERIAL EVENT CONTAINS A "CATEGORY 3" LEVEL OF RADIOACTIVE MATERIAL \n'
        "Category 3 sources, if not safely managed..."
    )
    stripped, counts = strip_declared_boilerplate(text, _enabled())
    assert stripped == text
    assert counts["iaea_less_than_cat3"] == 0


def test_boilerplate_counts_does_not_modify_text() -> None:
    counts = boilerplate_counts(MODERN_DOC, _enabled())
    assert counts == {"en_revision_header": 1, "iaea_less_than_cat3": 1}


def test_rules_are_independently_switchable() -> None:
    header_only = BoilerplateConfig(strip_en_revision_header=True)
    stripped, counts = strip_declared_boilerplate(MODERN_DOC, header_only)
    assert "EN Revision" not in stripped
    assert "Pub1227_web.pdf" in stripped
    assert counts == {"en_revision_header": 1}


# -- the general paragraph-frequency check ------------------------------------------


def test_normalize_paragraph_collapses_line_wrapping() -> None:
    wrapped = " The unit received an automatic trip\n due to a spurious signal.  "
    expected = "The unit received an automatic trip due to a spurious signal."
    assert normalize_paragraph(wrapped) == expected


def test_split_paragraphs_uses_blank_lines() -> None:
    text = "First paragraph.\nStill first.\n\nSecond paragraph.\n\n\nThird, after two blank lines."
    assert split_paragraphs(text) == [
        "First paragraph. Still first.",
        "Second paragraph.",
        "Third, after two blank lines.",
    ]


def test_find_frequent_paragraphs_counts_documents_not_occurrences() -> None:
    # "Shared line." repeats twice WITHIN each document (must count once per document);
    # each document's second paragraph is distinct ACROSS documents (must never qualify).
    documents = [f"Shared line.\n\nShared line.\n\nUnique to doc {i}." for i in range(5)] + [
        "Something else entirely."
    ]
    frequent = find_frequent_paragraphs(documents, min_docs=4)
    assert len(frequent) == 1
    assert frequent[0].text == "Shared line."
    assert frequent[0].document_count == 5


def test_find_frequent_paragraphs_respects_threshold() -> None:
    documents = ["Common paragraph." for _ in range(50)]
    assert find_frequent_paragraphs(documents, min_docs=100) == []
    assert len(find_frequent_paragraphs(documents, min_docs=10)) == 1


def test_find_frequent_paragraphs_sorted_most_common_first() -> None:
    documents = (
        ["Very common." for _ in range(20)] + ["Somewhat common." for _ in range(15)] + ["Rare."]
    )
    frequent = find_frequent_paragraphs(documents, min_docs=10)
    assert [item.text for item in frequent] == ["Very common.", "Somewhat common."]
    assert [item.document_count for item in frequent] == [20, 15]
