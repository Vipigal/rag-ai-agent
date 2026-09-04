from api.main import app

ERROR_CODES = ("422", "500", "502", "503")


def test_every_operation_carries_a_summary_a_description_and_a_tag():
    spec = app.openapi()

    assert spec["info"]["title"] == "RAG Agent API"
    assert "POST /documents" in spec["info"]["description"]
    assert "POST /question" in spec["info"]["description"]
    for path, method in (("/documents", "post"), ("/question", "post"), ("/health", "get")):
        operation = spec["paths"][path][method]
        assert operation["summary"], f"{method} {path} has no summary"
        assert operation["description"], f"{method} {path} has no description"
        assert operation["tags"], f"{method} {path} has no tag"


def test_the_two_challenge_endpoints_declare_every_error_status_with_an_example():
    spec = app.openapi()

    for path in ("/documents", "/question"):
        responses = spec["paths"][path]["post"]["responses"]
        assert set(ERROR_CODES) <= set(responses), f"{path} declares {sorted(responses)}"
        for code in ERROR_CODES:
            body = responses[code]["content"]["application/json"]
            assert body["schema"]["$ref"] == "#/components/schemas/ErrorResponse"
            assert body["example"]["detail"], f"{path} {code} has no example"
            assert responses[code]["description"]


def test_health_declares_the_unavailable_status():
    responses = app.openapi()["paths"]["/health"]["get"]["responses"]

    assert responses["503"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/ErrorResponse"
    )


def test_request_and_response_schemas_carry_the_challenge_examples():
    schemas = app.openapi()["components"]["schemas"]

    assert schemas["QuestionRequest"]["properties"]["question"]["examples"] == [
        "What grease should I use to relubricate the motor bearings?"
    ]
    assert schemas["QuestionRequest"]["properties"]["question"]["description"]
    question_examples = schemas["QuestionResponse"]["examples"]
    assert any(example["references"] == [] for example in question_examples)
    assert any(example["references"] for example in question_examples)
    assert schemas["QuestionResponse"]["properties"]["references"]["description"]
    assert schemas["DocumentsResponse"]["examples"] == [
        {"message": "Documents processed successfully", "documents_indexed": 2, "total_chunks": 128}
    ]
    assert schemas["ErrorResponse"]["properties"]["detail"]["description"]
