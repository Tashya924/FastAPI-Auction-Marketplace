from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
import main
import models


TEST_DATABASE_URL = "sqlite:///./test_auction.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

models.Base.metadata.create_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_database():
    for table in reversed(models.Base.metadata.sorted_tables):
        with test_engine.begin() as connection:
            connection.execute(table.delete())
    yield


@pytest.fixture(autouse=True)
def override_dependencies(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)
    main.app.dependency_overrides[main.get_db] = override_get_db
    yield
    main.app.dependency_overrides.clear()


@pytest.fixture
def client():
    transport = httpx.ASGITransport(app=main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def auth_user_payload():
    return {
        "username": "auctioneer",
        "email": "auctioneer@example.com",
        "password": "StrongPass123!",
    }


@pytest.fixture
def bidder_payload():
    return {
        "username": "bidder",
        "email": "bidder@example.com",
        "password": "StrongPass123!",
    }
