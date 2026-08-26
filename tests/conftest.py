import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import mount_portals, router
from tests.fakes import FakeKnowledgeBase, FakePDFProcessor, FakeQueryEngine


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)
    mount_portals(application)

    kb = FakeKnowledgeBase()
    application.state.knowledge_base = kb
    application.state.pdf_processor = FakePDFProcessor(kb)
    application.state.query_engine = FakeQueryEngine()
    return application


@pytest.fixture
def client(app):
    return TestClient(app)
