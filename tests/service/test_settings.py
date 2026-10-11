import pytest

from epinoic_logic.service import ServiceSettings, SettingsError

from .conftest import KEY, TOKEN

FULL_ENV = {
    "EPINOIC_SERVICE_TOKEN": TOKEN,
    "EPINOIC_SIGNING_KEY": KEY.hex(),
    "EPINOIC_SIGNING_KEY_ID": "env-key",
    "EPINOIC_MAX_BODY_BYTES": "4096",
    "EPINOIC_MAX_CONCURRENCY": "2",
    "EPINOIC_RATE_PER_MINUTE": "7",
}


def test_from_env_reads_every_variable():
    s = ServiceSettings.from_env(FULL_ENV)
    assert s.service_token == TOKEN
    assert s.signing_key == KEY and s.signing_key_id == "env-key"
    assert (s.max_body_bytes, s.max_concurrency, s.rate_per_minute) == (4096, 2, 7)
    assert s.allow_unsigned_for_tests is False and s.signs_results


def test_from_env_defaults():
    s = ServiceSettings.from_env({"EPINOIC_SERVICE_TOKEN": TOKEN, "EPINOIC_SIGNING_KEY": KEY.hex()})
    assert (s.max_body_bytes, s.max_concurrency, s.rate_per_minute, s.signing_key_id) == (1_000_000, 4, 60, "default")


@pytest.mark.parametrize(
    "env, fragment",
    [
        ({"EPINOIC_SIGNING_KEY": KEY.hex()}, "EPINOIC_SERVICE_TOKEN"),
        ({"EPINOIC_SERVICE_TOKEN": TOKEN}, "EPINOIC_SIGNING_KEY"),
        ({"EPINOIC_SERVICE_TOKEN": TOKEN, "EPINOIC_SIGNING_KEY": "not-hex"}, "hex"),
        ({**FULL_ENV, "EPINOIC_MAX_CONCURRENCY": "many"}, "EPINOIC_MAX_CONCURRENCY"),
        ({**FULL_ENV, "EPINOIC_RATE_PER_MINUTE": "0"}, "rate_per_minute"),
        ({**FULL_ENV, "EPINOIC_SERVICE_TOKEN": "short"}, "service_token"),
    ],
)
def test_from_env_rejects_missing_or_invalid_values_without_echoing_them(env, fragment):
    with pytest.raises(SettingsError) as info:
        ServiceSettings.from_env(env)
    assert fragment in str(info.value)
    assert TOKEN not in str(info.value) and KEY.hex() not in str(info.value)


def test_signing_key_required_unless_explicitly_allowed_for_tests():
    with pytest.raises(ValueError):
        ServiceSettings(service_token=TOKEN)
    s = ServiceSettings(service_token=TOKEN, allow_unsigned_for_tests=True)
    assert s.signing_key is None and not s.signs_results
    with pytest.raises(ValueError):
        ServiceSettings(service_token=TOKEN, signing_key=b"short")


def test_allow_unsigned_is_never_read_from_the_environment():
    with pytest.raises(SettingsError):
        ServiceSettings.from_env({"EPINOIC_SERVICE_TOKEN": TOKEN, "EPINOIC_ALLOW_UNSIGNED_FOR_TESTS": "1"})


def test_secrets_are_excluded_from_repr():
    s = ServiceSettings(service_token=TOKEN, signing_key=KEY, signing_key_id="k")
    text = repr(s) + str(s)
    assert TOKEN not in text and KEY.hex() not in text and "signing_key_id='k'" in repr(s)
