"""Unit tests: message parsing and small helpers, no network needed."""

import json

import pytest

from eeg_stream import ServerFilters, parse_message, parse_welcome
from live_view import check_channels
from record import MONTAGES, parse_electrodes, safe_name
from spectrum import load

WELCOME = {"status": "connected", "sample_rate": 250, "channels": 8,
           "filter": True, "notch_filter": False, "notch_freq": 60.0, "mock": False}


def test_parse_data_frame():
    s = parse_message(json.dumps({"t": 1.5, "n": 42, "channels": [1, 2.5, -3]}))
    assert (s.t, s.n, s.uv) == (1.5, 42, [1.0, 2.5, -3.0])


@pytest.mark.parametrize("raw", [json.dumps(WELCOME), "not json", "[]", json.dumps({"n": 1}),
                                 json.dumps({"n": 1, "channels": ["x"]}), json.dumps({"channels": [1]})])
def test_everything_else_is_not_a_sample(raw):
    assert parse_message(raw) is None


def test_welcome():
    assert parse_welcome(json.dumps(WELCOME))["channels"] == 8
    assert parse_welcome(json.dumps({"t": 1, "n": 1, "channels": [1]})) is None


def test_server_filters_from_welcome():
    st = ServerFilters.from_welcome(WELCOME)
    assert (st.bandpass, st.notch, st.notch_freq) == (True, False, 60.0)
    assert st.any_on() and not st.unknown()
    assert st.describe() == "bandpass on, notch off"
    on = ServerFilters.from_welcome({**WELCOME, "filter": False, "notch_filter": True, "notch_freq": 50})
    assert on.describe() == "bandpass off, notch on at 50 Hz"


def test_server_filters_unknown_when_not_reported():
    st = ServerFilters.from_welcome({"status": "connected", "channels": 8})
    assert st.unknown() and not st.any_on()
    assert "unknown" in st.describe()


def test_parse_electrodes():
    assert parse_electrodes("ch1=Fp1, ch2 = Fp2,REF=M1,bias=M2") == {
        "ch1": "Fp1", "ch2": "Fp2", "ref": "M1", "bias": "M2"}
    for bad in ["ch9=Oz", "ch1", "ch1=", "ground=M1"]:
        with pytest.raises(ValueError):
            parse_electrodes(bad)


def test_montages_use_known_keys():
    for name, electrodes in MONTAGES.items():
        assert set(electrodes) <= {*(f"ch{i}" for i in range(1, 9)), "ref", "bias"}, name


def test_safe_file_names():
    assert safe_name("eyes closed/1") == "eyes_closed_1"
    assert safe_name("sub-02") == "sub-02"


def test_channel_validation():
    assert check_channels([1, 2]) is None
    assert "between 1 and 8" in check_channels([0])
    assert "between 1 and 8" in check_channels([9])
    assert check_channels([1, 1]) is not None


def test_load_skips_an_incomplete_last_line(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("t,n,ch1,ch2\n0.0,1,1.5,2\n0.004,2,2.5,3\n0.008,3,3.")
    assert load(f, 1).tolist() == [1.5, 2.5]
