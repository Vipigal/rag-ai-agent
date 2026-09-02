import logging

from api import main


def test_importing_the_api_edge_puts_domain_loggers_at_info():
    assert main.app.title == "RAG Agent API"
    assert logging.getLogger("domain.services.ingestion_pipeline").getEffectiveLevel() == logging.INFO
