import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

temporary_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{temporary_directory.name}/api-test.db"

from app.database import Base, engine as api_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_fall_data  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def cleanup_api_database():
    yield
    api_engine.dispose()
    temporary_directory.cleanup()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_fall_data(session)
        yield session
    engine.dispose()


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=api_engine)
    Base.metadata.create_all(bind=api_engine)
    with TestClient(app) as test_client:
        yield test_client
