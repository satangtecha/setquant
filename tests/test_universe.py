import pandas as pd
import pytest

from setquant.universe import all_symbols, load_periods, members_on, to_yahoo


@pytest.fixture
def universe_csv(tmp_path):
    p = tmp_path / "u.csv"
    p.write_text(
        "index,period_start,period_end,symbol,source\n"
        "SET100,2024-01-01,2024-06-30,AAA,test\n"
        "SET100,2024-01-01,2024-06-30,BBB,test\n"
        "SET100,2024-07-01,2024-12-31,AAA,test\n"
        "SET100,2024-07-01,2024-12-31,CCC,test\n"
    )
    return p


def test_members_are_point_in_time(universe_csv):
    periods = load_periods(universe_csv)
    assert members_on(periods, "2024-03-15") == ["AAA", "BBB"]
    assert members_on(periods, "2024-09-15") == ["AAA", "CCC"]  # BBB dropped out


def test_all_symbols_includes_dropped_members(universe_csv):
    periods = load_periods(universe_csv)
    assert all_symbols(periods) == ["AAA", "BBB", "CCC"]


def test_invalid_period_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text(
        "index,period_start,period_end,symbol,source\n"
        "SET100,2024-06-30,2024-01-01,AAA,test\n"
    )
    with pytest.raises(ValueError, match="period_end before period_start"):
        load_periods(p)


def test_to_yahoo():
    assert to_yahoo("ptt") == "PTT.BK"


def test_aliases_resolve_and_reject_chains(tmp_path):
    from setquant.universe import load_aliases, to_data_symbol

    p = tmp_path / "aliases.csv"
    p.write_text("old_symbol,new_symbol,note\nTMB,TTB,rename\n")
    aliases = load_aliases(p)
    assert to_data_symbol("tmb", aliases) == "TTB"
    assert to_data_symbol("PTT", aliases) == "PTT"

    bad = tmp_path / "chained.csv"
    bad.write_text("old_symbol,new_symbol,note\nA,B,x\nB,C,y\n")
    import pytest
    with pytest.raises(ValueError, match="chained"):
        load_aliases(bad)
