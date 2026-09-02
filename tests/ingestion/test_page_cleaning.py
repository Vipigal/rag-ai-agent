from ingestion.page_cleaning import clean_pages


TITLES = ("Partida", "Frenagem", "Isolamento", "Rolamentos", "Vibração", "Ruído")


def running_title(i: int) -> str:
    return f"Especificação do Motor Elétrico {i}" if i % 2 else f"{i} Especificação do Motor Elétrico"


def guide_pages(count: int) -> list[str]:
    return [
        f"www.weg.net \n\n# 3.{i} {TITLES[i - 1]} \n\nBody about {TITLES[i - 1].lower()} of motors. \n\n"
        f"{running_title(i)} \n"
        for i in range(1, count + 1)
    ]


def test_lines_repeated_on_most_pages_are_stripped_from_every_page():
    cleaned = clean_pages(guide_pages(6))

    assert all("www.weg.net" not in page for page in cleaned)
    assert all("Especificação do Motor Elétrico" not in page for page in cleaned)
    assert all(f"Body about {TITLES[i - 1].lower()} of motors." in cleaned[i - 1] for i in range(1, 7))
    assert all(f"# 3.{i} {TITLES[i - 1]}" in cleaned[i - 1] for i in range(1, 7))


def test_repetition_needs_at_least_three_pages():
    pages = ["Header line \n\nfirst body \n", "Header line \n\nsecond body \n"]

    cleaned = clean_pages(pages)

    assert all("Header line" in page for page in cleaned)


def test_table_lines_are_never_treated_as_repeated_furniture():
    pages = [f"|Carcaça|Potência|\n|---|---|\n|{i}|{i * 10}|\n\nprose {i} \n" for i in range(5)]

    cleaned = clean_pages(pages)

    assert all("|---|---|" in page and "|Carcaça|Potência|" in page for page in cleaned)


def test_bare_page_number_lines_are_dropped():
    pages = ["**5** \n\nBody one. \n\n12 \n", "Body two. \n\n1-2 \n", "Body three at 5 mm. \n\n– 3 – \n"]

    cleaned = clean_pages(pages)

    assert cleaned[0] == "Body one."
    assert cleaned[1] == "Body two."
    assert cleaned[2] == "Body three at 5 mm."


def test_html_comments_and_dot_leaders_are_removed():
    pages = [
        "<!-- Start of picture text -->\nFigura 5.1 - Ligações \n<!-- End of picture text -->\n\n"
        "|**General Information** . . . . . . . . . . . . . . 1−1<br>. . . . . . . . . . . 1−2|\n"
    ]

    cleaned = clean_pages(pages)

    assert cleaned[0] == (
        "Figura 5.1 - Ligações\n\n|**General Information** 1−1<br> 1−2|"
    )


def test_blank_runs_collapse_and_trailing_spaces_are_trimmed():
    pages = ["First paragraph. \n\n\n\n\nSecond paragraph.   \n\n\n"]

    cleaned = clean_pages(pages)

    assert cleaned[0] == "First paragraph.\n\nSecond paragraph."


def test_pages_left_empty_stay_in_place():
    pages = ["Body. \n\n7 \n", "8 \n", "Body. \n\n9 \n"]

    cleaned = clean_pages(pages)

    assert cleaned == ["Body.", "", "Body."]


def test_contiguous_dot_leaders_collapse_too():
    pages = ["#### **1. Noções Fundamentais .......................................6** \n"]

    cleaned = clean_pages(pages)

    assert cleaned[0] == "#### **1. Noções Fundamentais 6**"
