"""Registration, login, sessions, language preference."""
import time

from app.auth import make_token, read_token, verify_password, hash_password


def test_register_then_login(client):
    r = client.post("/api/auth/register", json={
        "name": "Lakshmi Devi", "email": "Lakshmi@Example.com", "password": "strongpass1", "language": "kn"})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "lakshmi@example.com"       # emails are normalised
    assert r.json()["user"]["language"] == "kn"
    login = client.post("/api/auth/login", json={"email": "lakshmi@example.com", "password": "strongpass1"})
    assert login.status_code == 200 and login.json()["token"]


def test_duplicate_email_is_rejected(client):
    body = {"name": "Dup User", "email": "dup@example.com", "password": "strongpass1"}
    assert client.post("/api/auth/register", json=body).status_code == 201
    assert client.post("/api/auth/register", json=body).status_code == 409


def test_wrong_password_is_rejected(client):
    client.post("/api/auth/register", json={"name": "Wrong Pass", "email": "wp@example.com", "password": "rightpass1"})
    r = client.post("/api/auth/login", json={"email": "wp@example.com", "password": "wrongpass"})
    assert r.status_code == 401


def test_invalid_registration_inputs(client):
    assert client.post("/api/auth/register", json={"name": "A", "email": "a@b.co", "password": "longenough"}).status_code == 422
    assert client.post("/api/auth/register", json={"name": "Good Name", "email": "not-an-email", "password": "longenough"}).status_code == 400
    assert client.post("/api/auth/register", json={"name": "Good Name", "email": "ok@b.co", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={"name": "Good Name", "email": "ok2@b.co", "password": "longenough", "language": "fr"}).status_code == 400


def test_protected_routes_reject_bad_tokens(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_expired_token_is_rejected():
    expired = make_token(1, "test-secret", hours=-1)
    assert read_token(expired, "test-secret") is None


def test_token_signed_with_other_secret_is_rejected():
    token = make_token(1, "other-secret", hours=1)
    assert read_token(token, "test-secret") is None


def test_token_roundtrip():
    token = make_token(42, "test-secret", hours=1)
    assert read_token(token, "test-secret") == 42


def test_password_hash_is_salted_and_verifiable():
    a, b = hash_password("samepass123"), hash_password("samepass123")
    assert a != b
    assert verify_password("samepass123", a) and not verify_password("other", a)


def test_language_switch_is_saved(client, auth_headers):
    assert client.patch("/api/me", json={"language": "hi"}, headers=auth_headers).json()["language"] == "hi"
    assert client.get("/api/me", headers=auth_headers).json()["language"] == "hi"
    assert client.patch("/api/me", json={"language": "xx"}, headers=auth_headers).status_code == 400
    client.patch("/api/me", json={"language": "en"}, headers=auth_headers)
