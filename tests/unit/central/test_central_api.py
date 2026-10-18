"""API HTTP du central : authentification par jeton, format des réponses et des erreurs."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from nkap.central.api import create_central_app
from nkap.central.auth import revoke_site
from nkap.core.clock import FakeClock
from nkap.core.orm import Actor
from nkap.sync.protocol import PROTOCOL_VERSION, PUSH_PATH, STATE_PATH
from support.central import CentralDb
from support.events import SITE_A, SITE_B, make_envelope


@pytest.fixture
def client(central_db: CentralDb, clock: FakeClock) -> Iterator[TestClient]:
    with TestClient(create_central_app(central_db.factory, clock=clock)) as test_client:
        yield test_client


def _auth(central_db: CentralDb, code: str = "S01") -> dict[str, str]:
    return {"Authorization": f"Bearer {central_db.tokens[code]}"}


def _body(*seqs: int, site_id: object = SITE_A) -> dict[str, object]:
    events = [make_envelope(site_seq=s, site_id=site_id).model_dump(mode="json") for s in seqs]
    return {"protocol_version": PROTOCOL_VERSION, "site_id": str(site_id), "events": events}


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["role"] == "central"


def test_push_and_state_with_a_valid_token(client: TestClient, central_db: CentralDb) -> None:
    response = client.post(PUSH_PATH, json=_body(1, 2), headers=_auth(central_db))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["acked_through"] == 2
    assert data["server_time"].endswith("Z")
    state = client.get(STATE_PATH, headers=_auth(central_db)).json()
    assert state["acked_through"] == 2
    assert state["site_id"] == str(SITE_A)


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nks_faux"}, {"X": "y"}])
def test_missing_or_wrong_tokens_are_refused(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(PUSH_PATH, json=_body(1), headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.invalid_site_token"


def test_a_revoked_site_is_refused(
    client: TestClient, central_db: CentralDb, clock: FakeClock
) -> None:
    with central_db.factory.begin() as session:
        revoke_site(session, site_id=SITE_A, clock=clock, actor=Actor.system())
    response = client.post(PUSH_PATH, json=_body(1), headers=_auth(central_db))
    assert response.status_code == 401


def test_a_site_cannot_push_in_the_name_of_another(
    client: TestClient, central_db: CentralDb
) -> None:
    response = client.post(PUSH_PATH, json=_body(1, site_id=SITE_B), headers=_auth(central_db))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "auth.site_mismatch"


def test_invalid_bodies_get_a_structured_error(client: TestClient, central_db: CentralDb) -> None:
    body = _body(1)
    body["events"][0]["payload"] = {"text": 1.5}  # type: ignore[index]
    response = client.post(PUSH_PATH, json=body, headers=_auth(central_db))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "request.invalid"
    assert error["message"] == "Requête invalide."
    assert error["details"]


def test_messages_follow_the_accept_language_header(
    client: TestClient, central_db: CentralDb
) -> None:
    response = client.post(PUSH_PATH, json=_body(1), headers={"Accept-Language": "en-GB"})
    assert response.json()["error"]["message"].startswith("Site synchronization token")


def test_oversized_requests_are_refused(client: TestClient, central_db: CentralDb) -> None:
    headers = {**_auth(central_db), "Content-Length": str(64 * 1024 * 1024)}
    response = client.post(PUSH_PATH, content=b"{}", headers=headers)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request.too_large"
