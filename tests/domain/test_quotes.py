import pytest

from domain.services.quotes import contains, normalize

PAGE = """#### 2.3 Lubrication

**Recommended** lubricant is Shell Rotella 10 SAE 10W. Never operate these type 21 seals in a
dry-run condition.

|**Frame Size**|**Oil Spec**|**Min. Quarts**|**Max. Quarts**|
|---|---|---|---|
|250TY|4824-18-AF|3.0|3.5|
|**Temperatura**<br>**de Operação**|Óleo Mineral CLP|
|**Volume ofgr**<br>**inches**<sup>**3**</sup>|**ease to add**<br>**teaspoon**|
Dow Corning Molykote G-Rapid Plus
The motor must be stored shaft down in its' original packaging.
"""


@pytest.mark.parametrize(
    "quote",
    [
        "Never operate these type 21 seals in a dry-run condition.",
        "never operate these type 21 seals in a\n    dry-run condition",
        "Recommended lubricant is Shell Rotella 10 SAE 10W.",
        "2.3 Lubrication",
        "Frame Size | Oil Spec | Min. Quarts | Max. Quarts\n250TY | 4824-18-AF | 3.0 | 3.5",
        "|250TY|4824-18-AF|3.0|3.5|",
        "Temperatura de Operação | Óleo Mineral CLP",
        "Dow Corning Molykote G‑Rapid Plus",
        '"Never operate these type 21 seals in a dry-run condition."',
        "“Recommended lubricant is Shell Rotella 10 SAE 10W.”",
        "«Dow Corning Molykote G-Rapid Plus»",
        "The motor must be stored shaft down in its’ original packaging.",
        "|**Volume ofgr**\n**inches**\n**3**|**ease to add**\n**teaspoon**|",
        "Volume ofgr inches 3 | ease to add teaspoon",
    ],
)
def test_a_verbatim_passage_is_found_despite_case_whitespace_markup_and_dashes(quote: str):
    assert contains(PAGE, quote) is True


@pytest.mark.parametrize(
    "quote",
    [
        "Never operate these seals without oil.",
        "Shell Rotella 10 SAE 10W\n250TY | 9999",
        "",
        "   \n  ",
        "3.0 | 3.5 quarts of Shell",
    ],
)
def test_a_paraphrase_a_partly_wrong_multiline_quote_or_a_blank_quote_is_not_found(quote: str):
    assert contains(PAGE, quote) is False


def test_normalize_folds_case_markup_dashes_quotation_marks_and_whitespace():
    assert normalize("**Temperatura**<br>**de Operação**  — 40 °C") == "temperatura de operação - 40 °c"
    assert normalize("“its’ original” <sup>3</sup> «ok»") == "its original 3 ok"
