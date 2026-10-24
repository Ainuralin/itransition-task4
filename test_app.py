import os
import pytest
import app as module


@pytest.fixture
def client():
    return module.app.test_client()


def test_routes_and_static_boundary(client):
    assert client.get("/").status_code == 200
    assert client.get("/data.json").is_json
    assert client.get("/analyze.py").status_code == 404
    assert client.get("/../app.py").status_code == 404


def test_chat_disabled_without_key(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert client.get("/api/health").json["chat_ready"] is False
    assert client.post("/api/chat", json={"question": "Revenue?"}).status_code == 503


def test_revenue_tool_matches_summary():
    assert (
        module.calculate("revenue_between", {"store": "STORE1"})["revenue_usd"]
        == 739354.03
    )
    with pytest.raises(ValueError):
        module.calculate("revenue_between", {"store": "STORE1", "start": "2026-02-30"})


def test_customer_alias_spending():
    answer = module.calculate("customer_details", {"store": "STORE1", "user_id": 48403})
    assert answer["alias_ids"] == [48403, 48904, 50056]
    assert answer["total_spending_usd"] == 1317.59


def test_unknown_store_rejected():
    with pytest.raises(ValueError):
        module.calculate("store_summary", {"store": "../"})


def test_tool_loop_with_mock_provider(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-only")
    replies = iter(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "test1",
                        "type": "function",
                        "function": {
                            "name": "store_summary",
                            "arguments": '{"store":"STORE1"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "STORE1 revenue is $739,354.03."},
        ]
    )
    messages = []

    def fake_complete(msg):
        messages.append(list(msg))
        return next(replies)

    monkeypatch.setattr(module, "completion", fake_complete)
    r = client.post(
        "/api/chat", json={"question": "What is total revenue?", "store": "STORE1"}
    )
    assert r.status_code == 200
    assert r.json["tools_used"] == ["store_summary"]
    assert messages[1][-1]["role"] == "tool"
    assert "73935403" in messages[1][-1]["content"]


def test_navigation_dispatch():
    assert module.calculate("show_view", {"store": "STORE5", "tab": "authors"})[
        "action"
    ] == {"store": "STORE5", "tab": "authors"}


def test_request_uses_groq_only(monkeypatch):
    import io
    import json

    monkeypatch.setenv("GROQ_API_KEY", " test-key ")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["payload"] = json.loads(req.data)
        return io.BytesIO(
            b'{"choices":[{"message":{"role":"assistant","content":"ok"}}]}'
        )

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    assert (
        module.completion([{"role": "user", "content": "Revenue?"}])["content"] == "ok"
    )
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert captured["payload"]["model"] == "openai/gpt-oss-120b"
    assert captured["payload"]["parallel_tool_calls"] is False
    assert len(captured["payload"]["tools"]) == 6


@pytest.mark.parametrize(
    "code,status,fragment",
    [
        (429, 429, "limit"),
        (401, 502, "key"),
        (403, 502, "key"),
        (404, 502, "model"),
        (400, 502, "request"),
        (503, 502, "unavailable"),
    ],
)
def test_provider_errors_never_suggest_payment(
    client, monkeypatch, code, status, fragment
):
    from urllib.error import HTTPError

    monkeypatch.setenv("GROQ_API_KEY", "test-only")

    def reject(_):
        raise HTTPError(
            "https://api.groq.com", code, "test", {"Retry-After": "20"}, None
        )

    monkeypatch.setattr(module, "completion", reject)
    result = client.post("/api/chat", json={"question": "Revenue?"})
    assert result.status_code == status
    assert fragment in result.json["error"]
    assert "test-only" not in result.get_data(as_text=True)
    if code == 429:
        assert result.headers["Retry-After"] == "20"


def test_whitespace_key_is_unconfigured(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    monkeypatch.setenv("OPENAI_API_KEY", "ignored")
    assert client.get("/api/health").json["chat_ready"] is False
    assert client.post("/api/chat", json={"question": "Revenue?"}).status_code == 503


def test_malformed_provider_response_is_handled(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-only")
    monkeypatch.setattr(module, "completion", lambda _: {})
    assert client.post("/api/chat", json={"question": "Revenue?"}).status_code == 502
