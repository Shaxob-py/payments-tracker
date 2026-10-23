import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    from app.main import app
    with TestClient(app) as c:  # запускает lifespan -> init_db
        yield c


def mk(client, name="Алиса", fee=500_000, group="A1"):
    r = client.post("/students", json={"name": name, "phone": "+998901112233", "group": group, "monthly_fee": fee})
    assert r.status_code == 201, r.text
    return r.json()


def test_student_crud(client):
    s = mk(client)
    assert client.get("/students").json() == [s]
    r = client.put(f"/students/{s['id']}", json={"monthly_fee": 600_000, "group": "B2"})
    assert r.status_code == 200
    assert r.json()["monthly_fee"] == 600_000 and r.json()["group"] == "B2" and r.json()["name"] == "Алиса"
    assert client.delete(f"/students/{s['id']}").status_code == 204
    assert client.get(f"/students/{s['id']}").status_code == 404
    assert client.delete(f"/students/{s['id']}").status_code == 404


def test_validation(client):
    assert client.post("/students", json={"name": " ", "phone": "1", "group": "g", "monthly_fee": 1}).status_code == 422
    assert client.post("/students", json={"name": "x", "phone": "1", "group": "g", "monthly_fee": -5}).status_code == 422
    s = mk(client)
    assert client.post("/payments", json={"student_id": s["id"], "amount": 0}).status_code == 422
    assert client.post("/payments", json={"student_id": 999, "amount": 10}).status_code == 404


def test_payments_list_and_delete_cascade(client):
    s = mk(client)
    client.post("/payments", json={"student_id": s["id"], "amount": 100, "paid_at": "2026-10-01"})
    client.post("/payments", json={"student_id": s["id"], "amount": 200, "paid_at": "2026-10-05"})
    lst = client.get(f"/students/{s['id']}/payments").json()
    assert [p["amount"] for p in lst] == [200, 100]
    client.delete(f"/students/{s['id']}")
    s2 = mk(client, name="Боб")
    assert client.get(f"/students/{s2['id']}/payments").json() == []


def test_debtors(client):
    a = mk(client, "Алиса", 500_000)   # заплатила частично
    b = mk(client, "Боб", 300_000)     # заплатил полностью
    c = mk(client, "Вика", 400_000)    # не платила
    d = mk(client, "Гена", 100_000)    # переплатил
    e = mk(client, "Дина", 0)          # бесплатно — не должник
    pay = lambda sid, amt, dt: client.post("/payments", json={"student_id": sid, "amount": amt, "paid_at": dt})
    pay(a["id"], 200_000, "2026-10-03"); pay(a["id"], 100_000, "2026-10-20")
    pay(b["id"], 300_000, "2026-10-31")
    pay(d["id"], 150_000, "2026-10-01")
    pay(a["id"], 999_999, "2026-09-30")   # другой месяц — не учитывается
    pay(c["id"], 400_000, "2026-11-01")   # граница месяца

    r = client.get("/debtors", params={"month": "2026-10"})
    assert r.status_code == 200
    got = {x["name"]: x for x in r.json()}
    assert set(got) == {"Алиса", "Вика"}
    assert got["Алиса"]["paid"] == 300_000 and got["Алиса"]["debt"] == 200_000
    assert got["Вика"]["paid"] == 0 and got["Вика"]["debt"] == 400_000
    assert [x["name"] for x in r.json()] == ["Вика", "Алиса"]  # больший долг первым

    nov = {x["name"] for x in client.get("/debtors", params={"month": "2026-11"}).json()}
    assert "Вика" not in nov and "Боб" in nov


def test_debtors_december_and_bad_month(client):
    s = mk(client)
    client.post("/payments", json={"student_id": s["id"], "amount": 500_000, "paid_at": "2026-12-31"})
    assert client.get("/debtors", params={"month": "2026-12"}).json() == []
    assert client.get("/debtors", params={"month": "2026-13"}).status_code == 422
    assert client.get("/debtors", params={"month": "abc"}).status_code == 422
    assert client.get("/debtors").status_code == 200  # текущий месяц по умолчанию
