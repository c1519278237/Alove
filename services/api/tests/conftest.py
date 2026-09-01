import os

import pytest
from fastapi.testclient import TestClient

os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET_KEY"] = "test-only-secret-with-more-than-32-bytes"
os.environ["DATABASE_URL"] = "sqlite:///./test_guiyin.db"
os.environ["SMS_PROVIDER"] = "console"
# Never let the local .env file make automated tests consume paid API quota.
os.environ["AI_API_KEY"] = ""

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, phone: str, display_name: str) -> tuple[str, str]:
    requested = client.post("/api/v1/auth/sms/request", json={"phone": phone})
    assert requested.status_code == 200, requested.text
    code = requested.json()["debug_code"]
    verified = client.post(
        "/api/v1/auth/sms/verify",
        json={"phone": phone, "code": code, "display_name": display_name},
    )
    assert verified.status_code == 200, verified.text
    payload = verified.json()
    return payload["access_token"], payload["user_id"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
