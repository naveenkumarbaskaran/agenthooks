import pytest

from agenthooks.core.contract import ContractVersion, check_compatibility


def test_parse_valid_version():
    v = ContractVersion("1.0")
    assert v.major == 1
    assert v.minor == 0

def test_parse_invalid_version_raises():
    with pytest.raises(ValueError, match="invalid contract version"):
        ContractVersion("1.0.0")

def test_parse_invalid_non_numeric_raises():
    with pytest.raises(ValueError):
        ContractVersion("abc")

def test_version_str():
    assert str(ContractVersion("2.3")) == "2.3"

def test_exact_version_match():
    assert check_compatibility("==1.0", "1.0") is True

def test_exact_version_mismatch():
    assert check_compatibility("==1.0", "1.1") is False

def test_gte_range_passes():
    assert check_compatibility(">=1.0", "1.0") is True
    assert check_compatibility(">=1.0", "2.0") is True

def test_gte_range_fails():
    assert check_compatibility(">=1.0", "0.9") is False

def test_combined_range_passes():
    assert check_compatibility(">=1.0,<2.0", "1.5") is True

def test_combined_range_fails_lower():
    assert check_compatibility(">=1.0,<2.0", "0.9") is False

def test_combined_range_fails_upper():
    assert check_compatibility(">=1.0,<2.0", "2.0") is False

def test_none_required_always_passes():
    assert check_compatibility(None, "1.0") is True
    assert check_compatibility(None, None) is True

def test_none_got_with_requirement_fails():
    assert check_compatibility(">=1.0", None) is False

def test_none_got_without_requirement_passes():
    assert check_compatibility(None, None) is True
