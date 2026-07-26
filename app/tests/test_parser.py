"""Тести парсера вставленого тексту з коефіцієнтами."""
from app.providers.odds_paste_parser import parse_odds_text


SAMPLE = """
Arsenal — Chelsea
Тотал більше 2.5
Коефіцієнт 1.85

Real Madrid — Valencia
Перемога Real Madrid
Коефіцієнт 1.42
"""


def test_parse_two_blocks():
    lines = parse_odds_text(SAMPLE)
    assert len(lines) == 2

    first = lines[0]
    assert first.home == "Arsenal"
    assert first.away == "Chelsea"
    assert first.market_key == "over_2.5"
    assert first.total_line == 2.5
    assert abs(first.decimal_odds - 1.85) < 1e-9

    second = lines[1]
    assert second.home == "Real Madrid"
    assert second.away == "Valencia"
    assert second.market_key == "1x2_home"
    assert abs(second.decimal_odds - 1.42) < 1e-9


def test_parse_btts_and_double_chance():
    text = """
    Inter - Torino
    Обидві заб'ють Так
    2.10

    Bayern Munich vs Wolfsburg
    Подвійний шанс 1X
    1.15
    """
    lines = parse_odds_text(text)
    assert lines[0].market_key == "btts_yes"
    assert lines[1].market_key == "dc_1x"
