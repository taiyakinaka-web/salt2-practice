"""Security and integration acceptance tests; all inputs are synthetic."""
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app

ORIGIN = "http://testserver"
PASSWORD = "synthetic-password-123"
FIELDS = ("name", "company_name", "department", "title", "email", "phone", "address", "website")


def settings(**overrides):
    return dict(admin_email="admin@example.com", admin_password=PASSWORD,
                allowed_origins=[ORIGIN], secure_cookie=False, **overrides)


def image_bytes(fmt="PNG"):
    output = BytesIO()
    Image.new("RGB", (64, 40), "white").save(output, format=fmt)
    return output.getvalue()


@dataclass
class Actor:
    client: TestClient
    user: dict
    csrf: str

    @property
    def headers(self):
        return {"Origin": ORIGIN, "X-CSRF-Token": self.csrf}

    def post(self, path, **kwargs):
        return self.client.post(path, headers=self.headers, **kwargs)

    def delete(self, path):
        return self.client.delete(path, headers=self.headers)


@pytest.fixture
def world(tmp_path):
    app = create_app(database_path=str(tmp_path / "test.sqlite3"), settings=settings())
    with ExitStack() as stack:
        def login(email):
            client = stack.enter_context(TestClient(app))
            response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN})
            assert response.status_code == 200, response.text
            body = response.json()
            return Actor(client, body["user"], body["csrf_token"])
        admin = login("admin@example.com")
        for email in ("a@example.com", "b@example.com"):
            response = admin.post("/api/admin/users", json={"email": email, "password": PASSWORD})
            assert response.status_code == 201, response.text
        yield dict(app=app, path=tmp_path / "test.sqlite3", admin=admin, a=login("a@example.com"),
                   b=login("b@example.com"), login=login, anonymous=stack.enter_context(TestClient(app)))


def save(actor, *, image=None, **fields):
    data = {"name": "Synthetic Person", "request_id": str(uuid4()), **fields}
    return actor.post("/api/cards", data={"data": json.dumps(data)},
                      files={"image": ("synthetic.png", image if image is not None else image_bytes(), "image/png")})


def card(actor, **fields):
    response = save(actor, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def grant(admin, user, scope, target_id):
    response = admin.post(f"/api/admin/users/{user.user['id']}/grants", json={"scope": scope, "target_id": target_id})
    assert response.status_code == 201, response.text
    return response.json()


def visible_ids(actor, **params):
    response = actor.client.get("/api/cards", params=params)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def assert_access(actor, target, allowed):
    for suffix in ("", "/image"):
        response = actor.client.get(f"/api/cards/{target['id']}{suffix}")
        assert response.status_code == (200 if allowed else 404), response.text


def test_authentication_and_logout_invalidates_replayed_cookie(world):
    anonymous = world["anonymous"]
    unknown = anonymous.post("/api/auth/login", headers={"Origin": ORIGIN}, json={"email": "unknown@example.com", "password": PASSWORD})
    incorrect = anonymous.post("/api/auth/login", headers={"Origin": ORIGIN}, json={"email": "a@example.com", "password": "wrong-password"})
    assert unknown.status_code == incorrect.status_code == 401
    assert unknown.json() == incorrect.json()
    assert set(unknown.json()) >= {"code", "message"}
    actor = world["a"]
    assert actor.client.get("/api/auth/me").json()["user"]["role"] == "user"
    old_cookies = dict(actor.client.cookies)
    assert actor.post("/api/auth/logout").status_code == 204
    assert actor.client.get("/api/auth/me").status_code == 401
    for name, value in old_cookies.items():
        anonymous.cookies.set(name, value)
    assert anonymous.get("/api/auth/me").status_code == 401


def test_cookie_flags_and_public_health(world):
    response = world["anonymous"].post("/api/auth/login", headers={"Origin": ORIGIN}, json={"email": "a@example.com", "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert world["anonymous"].get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/auth/me", "/api/cards", "/api/cards/1", "/api/cards/1/image", "/api/people/options", "/api/admin/users", "/api/admin/grant-targets?scope=person"])
def test_unauthenticated_reads_are_rejected(world, path):
    assert world["anonymous"].get(path).status_code == 401


def test_user_creation_normalizes_email_and_forbids_role_input(world):
    admin = world["admin"]
    response = admin.post("/api/admin/users", json={"email": "  New.User@Example.COM  ", "password": PASSWORD})
    assert response.status_code == 201
    assert response.json()["email"] == "new.user@example.com"
    assert response.json()["role"] == "user"
    assert admin.post("/api/admin/users", json={"email": "new.user@example.com", "password": PASSWORD}).status_code in (400, 409, 422)
    assert admin.post("/api/admin/users", json={"email": "short@example.com", "password": "short"}).status_code in (400, 422)
    assert admin.post("/api/admin/users", json={"email": "spoof@example.com", "password": PASSWORD, "role": "admin"}).status_code in (400, 422)
    assert world["login"]("new.user@example.com").user["role"] == "user"


@pytest.mark.parametrize("method,path,payload", [
    ("get", "/api/admin/users", None),
    ("post", "/api/admin/users", {"email": "forbidden@example.com", "password": PASSWORD}),
    ("get", "/api/admin/grant-targets?scope=person", None),
    ("get", "/api/admin/users/1/grants", None),
    ("post", "/api/admin/users/1/grants", {"scope": "person", "target_id": 1}),
    ("delete", "/api/admin/users/1/grants/1", None),
])
def test_ordinary_users_cannot_use_admin_endpoints(world, method, path, payload):
    kwargs = {"headers": world["a"].headers}
    if payload is not None:
        kwargs["json"] = payload
    assert getattr(world["a"].client, method)(path, **kwargs).status_code == 403


def test_owner_visibility_search_pagination_image_and_hidden_candidates(world):
    a, b = world["a"], world["b"]
    first = card(a, name="Owner One", company_name="Owner Company")
    second = card(a, name="Owner Two", company_name="Other Company")
    secret = card(b, name="Hidden Person", company_name="Hidden Company")
    assert visible_ids(a) == {first["id"], second["id"]}
    assert visible_ids(a, q="Owner One") == {first["id"]}
    assert visible_ids(a, q="Owner Company") == {first["id"]}
    assert visible_ids(a, q="Hidden") == set()
    page = a.client.get("/api/cards", params={"limit": 1, "offset": 0}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert not any("image_bytes" in item for item in page["items"])
    next_page = a.client.get("/api/cards", params={"limit": 1, "offset": 1}).json()
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    assert_access(a, first, True)
    image = a.client.get(f"/api/cards/{first['id']}/image")
    assert image.content == image_bytes()
    assert image.headers["cache-control"] == "private, no-store"
    assert "image/png" in image.headers["content-type"]
    assert_access(a, secret, False)
    for suffix in ("", "/image"):
        missing = a.client.get(f"/api/cards/999999999{suffix}")
        forbidden = a.client.get(f"/api/cards/{secret['id']}{suffix}")
        assert forbidden.status_code == missing.status_code == 404
        assert forbidden.json() == missing.json()
    options = a.client.get("/api/people/options").json()["items"]
    assert {item["id"] for item in options} == {first["person_id"], second["person_id"]}
    assert all("#" in item["label"] for item in options)
    assert "Hidden" not in json.dumps(options)
    assert visible_ids(world["admin"]) == {first["id"], second["id"], secret["id"]}


@pytest.mark.parametrize("scope", ["company", "department", "person"])
def test_scope_grants_isolate_ids_apply_to_future_cards_and_revoke(world, scope):
    a, b, admin = world["a"], world["b"], world["admin"]
    target = card(a, name="Same Name", company_name="Alpha", department="Sales")
    other_company = card(a, name="Same Name", company_name="Beta", department="Sales")
    other_department = card(a, name="Another Person", company_name="Alpha", department="Research")
    same_department = card(a, name="Same Name", company_name="Alpha", department="Sales")
    assert target["department_id"] != other_company["department_id"]
    assert len({item["person_id"] for item in (target, other_company, same_department)}) == 3
    target_id = target[f"{scope}_id"]
    permitted = grant(admin, b, scope, target_id)
    assert grant(admin, b, scope, target_id)["id"] == permitted["id"]
    assert len(admin.client.get(f"/api/admin/users/{b.user['id']}/grants").json()["items"]) == 1
    expected = {target["id"]}
    if scope == "company":
        expected |= {other_department["id"], same_department["id"]}
    elif scope == "department":
        expected.add(same_department["id"])
    assert visible_ids(b) == expected
    assert_access(b, target, True)
    assert_access(b, other_company, False)
    assert visible_ids(b, q="Beta") == set()
    future = card(a, name="Future Card", company_name="Alpha", department="Sales", **({"person_id": target["person_id"]} if scope == "person" else {}))
    assert_access(b, future, True)
    assert admin.delete(f"/api/admin/users/{b.user['id']}/grants/{permitted['id']}").status_code == 204
    assert visible_ids(b) == set()
    assert_access(b, target, False)
    assert_access(b, future, False)
    assert b.client.get("/api/people/options").json()["items"] == []


def test_grants_use_or_and_owner_access_survives_revocation(world):
    a, b, admin = world["a"], world["b"], world["admin"]
    target = card(a, company_name="Alpha", department="Sales")
    company = grant(admin, b, "company", target["company_id"])
    person = grant(admin, b, "person", target["person_id"])
    assert admin.delete(f"/api/admin/users/{b.user['id']}/grants/{company['id']}").status_code == 204
    assert_access(b, target, True)
    assert admin.delete(f"/api/admin/users/{b.user['id']}/grants/{person['id']}").status_code == 204
    assert_access(b, target, False)
    own_grant = grant(admin, a, "company", target["company_id"])
    assert admin.delete(f"/api/admin/users/{a.user['id']}/grants/{own_grant['id']}").status_code == 204
    assert_access(a, target, True)


@pytest.mark.parametrize("extra", [{"created_by": 1}, {"role": "admin"}, {"grants": [{"scope": "company", "target_id": 1}]}])
def test_card_creator_role_and_grant_spoofing_rejected(world, extra):
    actor = world["a"]
    assert save(actor, **extra).status_code in (400, 422)
    assert visible_ids(actor) == set()
    assert card(actor)["created_by"] == actor.user["id"]


def test_inaccessible_person_id_cannot_be_attached_and_accessible_id_can(world):
    hidden = card(world["a"], name="Same Name")
    assert save(world["b"], name="Same Name", person_id=hidden["person_id"]).status_code in (403, 404)
    assert visible_ids(world["b"]) == set()
    grant(world["admin"], world["b"], "person", hidden["person_id"])
    assert card(world["b"], name="Second Card", person_id=hidden["person_id"])["person_id"] == hidden["person_id"]


def test_invalid_grant_targets_and_cross_user_revocation(world):
    a, b, admin = world["a"], world["b"], world["admin"]
    target = card(a, company_name="Alpha")
    for payload in ({"scope": "unknown", "target_id": target["person_id"]}, {"scope": "person", "target_id": 999999999}):
        assert admin.post(f"/api/admin/users/{b.user['id']}/grants", json=payload).status_code in (400, 404, 422)
    assert admin.post("/api/admin/users/999999999/grants", json={"scope": "person", "target_id": target["person_id"]}).status_code == 404
    allowed = grant(admin, b, "person", target["person_id"])
    assert admin.delete(f"/api/admin/users/{a.user['id']}/grants/{allowed['id']}").status_code == 404
    assert_access(b, target, True)


@pytest.mark.parametrize("headers", [
    {"Origin": ORIGIN},
    {"Origin": ORIGIN, "X-CSRF-Token": "invalid"},
    {"Origin": "https://hostile.invalid", "X-CSRF-Token": "VALID"},
    {"X-CSRF-Token": "VALID"},
])
def test_csrf_and_origin_validation(world, headers):
    actor = world["a"]
    headers = {key: (actor.csrf if value == "VALID" else value) for key, value in headers.items()}
    assert actor.client.post("/api/auth/logout", headers=headers).status_code == 403
    assert actor.client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize("origin", [None, "https://hostile.invalid"])
def test_login_origin_validation(world, origin):
    headers = {} if origin is None else {"Origin": origin}
    assert world["anonymous"].post("/api/auth/login", headers=headers, json={"email": "a@example.com", "password": PASSWORD}).status_code == 403


def test_csrf_token_from_another_session_is_rejected(world):
    assert world["a"].client.post("/api/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": world["b"].csrf}).status_code == 403


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_name_validation_is_atomic(world, name):
    assert save(world["a"], name=name).status_code in (400, 422)
    assert visible_ids(world["a"]) == set()


def test_manual_save_trims_name_and_allows_empty_optional_fields(world):
    target = card(world["a"], name="  Valid Name  ")
    assert target["name"] == "Valid Name"
    assert all(target[field] == "" for field in FIELDS if field != "name")
    assert target["company_id"] is None and target["department_id"] is None
    assert save(world["a"], email="x" * 1001).status_code in (400, 422)


@pytest.mark.parametrize("payload", [b"not an image", b"\x89PNG\r\n\x1a\ntruncated"])
def test_invalid_images_are_rejected_on_save_and_extract(world, payload):
    actor = world["a"]
    assert save(actor, image=payload).status_code in (400, 415, 422)
    assert actor.post("/api/extract", files={"image": ("fake.png", payload, "image/png")}).status_code in (400, 415, 422)
    assert visible_ids(actor) == set()


def test_oversized_and_unsupported_images_rejected(world):
    actor = world["a"]
    assert save(actor, image=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert save(actor, image=image_bytes("GIF")).status_code in (400, 415, 422)
    assert visible_ids(actor) == set()


def test_jpeg_and_png_original_bytes_are_preserved(world):
    for fmt in ("PNG", "JPEG"):
        original = image_bytes(fmt)
        target = card(world["a"], image=original)
        assert world["a"].client.get(f"/api/cards/{target['id']}/image").content == original


def test_save_idempotency_is_scoped_to_user(world):
    request_id = str(uuid4())
    a, b = world["a"], world["b"]
    first = card(a, name="First", request_id=request_id)
    retry = save(a, name="First", request_id=request_id)
    assert retry.status_code in (200, 201) and retry.json()["id"] == first["id"]
    second = card(b, name="Second", request_id=request_id)
    assert second["id"] != first["id"] and second["created_by"] == b.user["id"]
    assert visible_ids(a) == {first["id"]} and visible_ids(b) == {second["id"]}


def test_restart_preserves_cards_images_users_roles_and_grants(world):
    admin, a, b = world["admin"], world["a"], world["b"]
    target = card(a, name="Persistent Person", company_name="Persistent Company", department="Sales")
    permitted = grant(admin, b, "department", target["department_id"])
    changed_settings = settings()
    changed_settings["admin_password"] = "different-synthetic-password"
    restarted = create_app(database_path=str(world["path"]), settings=changed_settings)
    with TestClient(restarted) as client:
        assert client.get(f"/api/cards/{target['id']}").status_code == 401
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN}, json={"email": "b@example.com", "password": PASSWORD})
        assert login.status_code == 200 and login.json()["user"]["role"] == "user"
        detail = client.get(f"/api/cards/{target['id']}")
        assert detail.status_code == 200 and detail.json()["created_by"] == a.user["id"]
        assert client.get(f"/api/cards/{target['id']}/image").content == image_bytes()
        assert client.get("/api/admin/users").status_code == 403
    with TestClient(restarted) as client:
        login = client.post("/api/auth/login", headers={"Origin": ORIGIN}, json={"email": "admin@example.com", "password": PASSWORD})
        assert login.status_code == 200 and login.json()["user"]["role"] == "admin"
        grants = client.get(f"/api/admin/users/{b.user['id']}/grants").json()["items"]
        assert grants[0]["id"] == permitted["id"]


async def synthetic_extraction(image, mime):
    assert image == image_bytes() and mime == "image/png"
    return {field: ("Extracted Person" if field == "name" else "") for field in FIELDS}


def test_extraction_does_not_save_and_manual_save_does_not_call_ai(world, monkeypatch):
    from app import ai
    monkeypatch.setattr(ai, "extract_fields", synthetic_extraction)
    actor = world["a"]
    response = actor.post("/api/extract", files={"image": ("synthetic.png", image_bytes(), "image/png")})
    assert response.status_code == 200
    assert response.json()["fields"]["name"] == "Extracted Person"
    assert visible_ids(actor) == set()

    async def unexpected_call(*args):
        raise AssertionError("Saving confirmed fields must not call the AI service")
    monkeypatch.setattr(ai, "extract_fields", unexpected_call)
    assert card(actor, name="Manually Corrected")["name"] == "Manually Corrected"


@pytest.mark.parametrize("status,code", [(503, "ai_not_configured"), (502, "ai_error"), (504, "ai_timeout")])
def test_ai_errors_are_visible_and_do_not_save(world, monkeypatch, status, code):
    from app import ai
    from fastapi import HTTPException
    async def failed_extraction(*args):
        raise HTTPException(status_code=status, detail={"code": code, "message": "Synthetic extraction failure; retry or enter fields manually."})
    monkeypatch.setattr(ai, "extract_fields", failed_extraction)
    actor = world["a"]
    response = actor.post("/api/extract", files={"image": ("synthetic.png", image_bytes(), "image/png")})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert "message" in response.json()
    assert visible_ids(actor) == set()
    assert card(actor, name="Manual Fallback")["name"] == "Manual Fallback"


def test_expired_and_forged_session_tokens_are_rejected(world):
    from datetime import timedelta
    from sqlmodel import Session, select
    from app.models import LoginSession, utcnow
    with Session(world["app"].state.engine) as database:
        sessions = database.exec(select(LoginSession).where(LoginSession.user_id == world["a"].user["id"])).all()
        for session in sessions:
            session.expires_at = utcnow() - timedelta(seconds=1)
            database.add(session)
        database.commit()
    assert world["a"].client.get("/api/auth/me").status_code == 401
    world["anonymous"].cookies.set("session", "synthetic-forged-token")
    assert world["anonymous"].get("/api/cards").status_code == 401


def test_plaintext_password_is_not_stored(world):
    from sqlmodel import Session, select
    from app.models import User
    with Session(world["app"].state.engine) as database:
        users = database.exec(select(User)).all()
        assert len(users) == 3
        assert all(user.password_hash.startswith("$argon2") and PASSWORD not in user.password_hash for user in users)


def test_pixel_limit_and_content_based_image_validation(world, monkeypatch):
    from app import main
    actor = world["a"]
    # A declared JPEG containing real PNG bytes must be classified by its decoded content.
    response = actor.post("/api/cards", data={"data": json.dumps({"name": "Content Detected", "request_id": str(uuid4())})},
                          files={"image": ("misleading.jpg", image_bytes(), "image/jpeg")})
    assert response.status_code == 201
    image = actor.client.get(f"/api/cards/{response.json()['id']}/image")
    assert image.headers["content-type"] == "image/png"
    monkeypatch.setattr(main, "MAX_IMAGE_PIXELS", 100)
    assert save(actor).status_code in (400, 413, 422)


def test_conflicting_request_id_is_rejected_without_overwriting(world):
    actor = world["a"]
    request_id = str(uuid4())
    original = card(actor, name="Original Name", request_id=request_id)
    conflict = save(actor, name="Changed Name", request_id=request_id)
    assert conflict.status_code == 409
    assert visible_ids(actor) == {original["id"]}
    assert actor.client.get(f"/api/cards/{original['id']}").json()["name"] == "Original Name"


def test_storage_failure_rolls_back_and_same_request_can_be_retried(world, monkeypatch):
    from sqlmodel import Session
    from sqlalchemy.exc import OperationalError
    actor = world["a"]
    request_id = str(uuid4())

    def storage_failure(self):
        raise OperationalError("synthetic statement", {}, Exception("synthetic internal detail"))
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", storage_failure)
        response = save(actor, name="Retry After Storage Error", request_id=request_id)
    assert response.status_code in (500, 503)
    assert set(response.json()) >= {"code", "message"}
    assert "synthetic internal detail" not in response.text
    assert visible_ids(actor) == set()
    retried = card(actor, name="Retry After Storage Error", request_id=request_id)
    assert visible_ids(actor) == {retried["id"]}


def test_blank_company_has_no_company_or_department_permission_target(world):
    target = card(world["a"], name="No Company", department="Sales")
    assert target["department"] == "Sales"
    assert target["company_id"] is None and target["department_id"] is None
    for scope in ("company", "department"):
        assert world["admin"].client.get("/api/admin/grant-targets", params={"scope": scope}).json()["items"] == []


def test_scope_target_ids_are_checked_in_their_own_namespace(world):
    first = card(world["a"], company_name="Only Company")
    second = card(world["a"], company_name="Only Company")
    assert second["person_id"] != first["company_id"]
    response = world["admin"].post(f"/api/admin/users/{world['b'].user['id']}/grants",
                                   json={"scope": "company", "target_id": second["person_id"]})
    assert response.status_code == 404
    assert visible_ids(world["b"]) == set()
