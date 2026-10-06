import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(c, email="a@example.com", name="Alice", password="password123"):
    return c.post("/api/auth/register", json={"name": name, "email": email, "password": password})


def auth_header(c, email="a@example.com", password="password123"):
    register(c, email=email)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------- Auth ----------
def test_register_success_hides_password(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@example.com"
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_email(client):
    register(client)
    assert register(client, email="A@Example.com").status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "A", "email": "not-an-email", "password": "password123"},
        {"name": "A", "email": "a@example.com", "password": "short"},
        {"name": "", "email": "a@example.com", "password": "password123"},
        {"email": "a@example.com", "password": "password123"},
    ],
)
def test_register_validation(client, payload):
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code == 400
    assert r.json()["error"] == "Validation failed"


def test_login_success_and_failure(client):
    register(client)
    ok = client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["token_type"] == "bearer"
    bad = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrongpass1"})
    assert bad.status_code == 401
    unknown = client.post("/api/auth/login", json={"email": "x@example.com", "password": "password123"})
    assert unknown.status_code == 401


def test_password_is_hashed(client):
    from app.models import User

    register(client)
    with TestingSession() as db:
        user = db.query(User).first()
        assert user.password_hash != "password123"
        assert user.password_hash.startswith("$2")


# ---------- Authorization ----------
def test_tasks_require_auth(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/tasks", json={"title": "x"}).status_code == 401
    assert client.get("/api/tasks", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ---------- Task CRUD ----------
def test_task_crud_flow(client):
    h = auth_header(client)
    r = client.post("/api/tasks", json={"title": "Write README"}, headers=h)
    assert r.status_code == 201
    task = r.json()
    assert task["status"] == "pending" and task["priority"] == "medium"

    tid = task["id"]
    assert client.get(f"/api/tasks/{tid}", headers=h).json()["title"] == "Write README"

    r = client.put(
        f"/api/tasks/{tid}",
        json={"title": "Write docs", "status": "in_progress", "priority": "high", "description": "d"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress" and r.json()["description"] == "d"

    # fields not sent are preserved
    r = client.put(f"/api/tasks/{tid}", json={"title": "Only title"}, headers=h)
    assert r.json()["priority"] == "high" and r.json()["description"] == "d"

    assert client.delete(f"/api/tasks/{tid}", headers=h).status_code == 200
    assert client.get(f"/api/tasks/{tid}", headers=h).status_code == 404


def test_task_validation(client):
    h = auth_header(client)
    for bad in [
        {},
        {"title": "   "},
        {"title": "x", "status": "done"},
        {"title": "x", "priority": "urgent"},
    ]:
        assert client.post("/api/tasks", json=bad, headers=h).status_code == 400


def test_not_found_and_bad_id(client):
    h = auth_header(client)
    assert client.get("/api/tasks/999", headers=h).status_code == 404
    assert client.put("/api/tasks/999", json={"title": "x"}, headers=h).status_code == 404
    assert client.delete("/api/tasks/999", headers=h).status_code == 404
    assert client.get("/api/tasks/abc", headers=h).status_code == 400


def test_users_cannot_access_each_others_tasks(client):
    h1 = auth_header(client, "one@example.com")
    h2 = auth_header(client, "two@example.com")
    tid = client.post("/api/tasks", json={"title": "private"}, headers=h1).json()["id"]

    assert client.get(f"/api/tasks/{tid}", headers=h2).status_code == 404
    assert client.put(f"/api/tasks/{tid}", json={"title": "hack"}, headers=h2).status_code == 404
    assert client.delete(f"/api/tasks/{tid}", headers=h2).status_code == 404
    assert client.get("/api/tasks", headers=h2).json()["total"] == 0
    assert client.get(f"/api/tasks/{tid}", headers=h1).status_code == 200


def test_pagination_and_filters(client):
    h = auth_header(client)
    for i in range(25):
        client.post(
            "/api/tasks",
            json={"title": f"t{i}", "priority": "high" if i % 5 == 0 else "low",
                  "status": "completed" if i < 3 else "pending"},
            headers=h,
        )
    r = client.get("/api/tasks?page=1&page_size=10", headers=h).json()
    assert len(r["items"]) == 10 and r["total"] == 25 and r["total_pages"] == 3
    assert len(client.get("/api/tasks?page=3&page_size=10", headers=h).json()["items"]) == 5
    assert client.get("/api/tasks?page=9", headers=h).json()["items"] == []
    assert client.get("/api/tasks?status=completed", headers=h).json()["total"] == 3
    assert client.get("/api/tasks?priority=high", headers=h).json()["total"] == 5
    assert client.get("/api/tasks?page=0", headers=h).status_code == 400
    assert client.get("/api/tasks?page_size=101", headers=h).status_code == 400
