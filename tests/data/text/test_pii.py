"""PII scrubbing, ported from notebook cells 32-34, with the ADR-0005 change."""

from __future__ import annotations

from faultline.data.text.pii import PIIConfig, scrub_pii


def test_emails_and_phones_are_masked_by_default() -> None:
    text = "write to duty.engineer@example.org or call +44 1234 567890 today"
    scrubbed, stats = scrub_pii(text)
    assert "<EMAIL>" in scrubbed
    assert "<PHONE>" in scrubbed
    assert "example.org" not in scrubbed
    assert stats["email"] == 1
    assert stats["phone"] == 1


def test_digit_masking_is_off_by_default() -> None:
    # ADR-0005: the course pipeline masked any run of six or more digits. That is
    # right for TinyStories and destructive for operator narratives, where the
    # magnitude is the technical content.
    text = "accumulated output was 9876543 kWh at the time of the trip"
    scrubbed, stats = scrub_pii(text)
    assert "9876543" in scrubbed
    assert "<NUMBER>" not in scrubbed
    assert stats["digits"] == 0


def test_digit_masking_when_explicitly_enabled() -> None:
    scrubbed, stats = scrub_pii("reference 9876543 raised", PIIConfig(mask_digits=True))
    assert "<NUMBER>" in scrubbed
    assert stats["digits"] == 1


def test_each_class_can_be_disabled() -> None:
    config = PIIConfig(mask_emails=False, mask_phones=False)
    text = "a@b.com and +44 1234 567890"
    scrubbed, stats = scrub_pii(text, config)
    assert scrubbed == text
    assert stats == {"email": 0, "phone": 0, "digits": 0}


def test_short_numbers_survive_even_when_digit_masking_is_on() -> None:
    scrubbed, _ = scrub_pii("rated at 2050 kW", PIIConfig(mask_digits=True))
    assert "2050" in scrubbed


def test_counts_multiple_replacements() -> None:
    _, stats = scrub_pii("a@b.com c@d.org e@f.net")
    assert stats["email"] == 3
