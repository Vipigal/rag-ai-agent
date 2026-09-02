from domain.models import Chunk, chunk_id
from ingestion.embedding_units import embedding_units

SHA_ONE = "f315915be2378786af1785ccc6a226aad15ad69d96465ec0105b186066cb2681"
CONTEXT = "WEG motores eletricos guia de especificacao 50032749 > 7. Características > 7.5 Grau de proteção"


def make_chunk(**overrides: object) -> Chunk:
    fields: dict[str, object] = dict(
        id=chunk_id(SHA_ONE, 0),
        document_id=SHA_ONE,
        filename="WEG-motores-eletricos-guia-de-especificacao-50032749.pdf",
        text="O grau de proteção IP55 protege contra poeira.\n\nJatos d'água também.",
        page=34,
        section="7. Características > 7.5 Grau de proteção",
        index_in_doc=0,
    )
    fields.update(overrides)
    return Chunk(**fields)  # type: ignore[arg-type]


def test_units_are_the_blank_line_blocks_each_prefixed_with_the_context():
    assert embedding_units(make_chunk()) == [
        f"{CONTEXT}\n\nO grau de proteção IP55 protege contra poeira.",
        f"{CONTEXT}\n\nJatos d'água também.",
    ]


def test_tables_split_into_rows_that_keep_the_header():
    table = "|Carcaça|Graxa (g)|\n|---|---|\n|132|20|\n|160|30|"
    chunk = make_chunk(text=f"Intervalos:\n\n{table}")

    assert embedding_units(chunk) == [
        f"{CONTEXT}\n\nIntervalos:",
        f"{CONTEXT}\n\n|Carcaça|Graxa (g)|\n|---|---|\n|132|20|",
        f"{CONTEXT}\n\n|Carcaça|Graxa (g)|\n|---|---|\n|160|30|",
    ]


def test_without_section_the_context_is_the_document_name_alone():
    chunk = make_chunk(section=None, text="single block")

    assert embedding_units(chunk) == [
        "WEG motores eletricos guia de especificacao 50032749\n\nsingle block"
    ]


def test_a_chunk_with_no_blocks_still_yields_one_unit():
    chunk = make_chunk(section=None, text="   ")

    assert embedding_units(chunk) == [
        "WEG motores eletricos guia de especificacao 50032749\n\n   "
    ]
