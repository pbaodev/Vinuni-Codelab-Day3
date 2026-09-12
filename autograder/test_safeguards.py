"""Regression tests bổ sung; giữ nguyên bộ chấm gốc của lab."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "starter-code"))
from template import ReActAgent
from tools import TOOL_MAP


def test_reverse_route_no_results():
    result = ReActAgent().run("Tìm chuyến bay từ SGN đi HAN dưới 500k.")
    assert result["trace"][0]["action"]["args"] == {
        "origin": "SGN", "destination": "HAN", "max_price": 500000,
    }
    assert "SGN đi HAN" in result["answer"]
    assert "Không tìm thấy" in result["answer"]


def test_weather_uses_requested_city():
    result = ReActAgent().run("Tìm chuyến bay từ DAD đi HAN và thời tiết HAN nên mặc gì?")
    assert "VN110" in result["answer"]
    assert "22°C" in result["answer"]


def test_missing_route_asks_for_details():
    result = ReActAgent().run("Tìm vé máy bay dưới 2 triệu")
    assert not any("action" in step for step in result["trace"])
    assert "điểm đi" in result["answer"]


def test_unrelated_query_has_no_fake_travel_results():
    result = ReActAgent().run("Xin chào")
    assert "°C" not in result["answer"]
    assert not any("action" in step for step in result["trace"])


def test_action_normalizes_tool_name():
    agent = ReActAgent()
    observation = agent.execute_action(
        json.dumps({"name": " Get_Weather_Forecast ", "args": {"city_code": "HAN"}}),
        iteration=1, thought="Tra cứu thời tiết.",
    )
    assert observation["temperature_c"] == 22
    assert agent.trace[0]["action"]["name"] == "get_weather_forecast"


@pytest.mark.parametrize("action", [
    "get_flight_info('HAN')", "[]", "null",
    '{"name": 1, "args": {}}',
    '{"name": "get_weather_forecast", "args": []}',
    '{"name": "unknown_tool", "args": {}}',
    '{"name": "get_weather_forecast", "args": {}}',
])
def test_invalid_action_is_observation(action):
    agent = ReActAgent()
    observation = agent.execute_action(action, iteration=1, thought="Tra cứu.")
    assert "error" in observation
    assert agent.trace[0]["observation"] == observation


@pytest.mark.parametrize("raises", [False, True])
def test_tool_failure_stops_after_two_attempts(monkeypatch, raises):
    def broken_weather(**kwargs):
        if raises:
            raise RuntimeError("Service unavailable")
        return {"error": "City not found"}

    monkeypatch.setitem(TOOL_MAP, "get_weather_forecast", broken_weather)
    result = ReActAgent(max_iterations=5).run("Thời tiết HAN thế nào?")
    failures = [step for step in result["trace"] if "observation" in step]
    assert result["status"] == "tool_error"
    assert len(failures) == 2
    assert all("error" in step["observation"] for step in failures)
    assert "không thể" in result["answer"].lower()


def test_temporary_tool_failure_can_recover(monkeypatch):
    weather = TOOL_MAP["get_weather_forecast"]
    attempts = []

    def flaky_weather(**kwargs):
        attempts.append(kwargs)
        return {"error": "Temporary failure"} if len(attempts) == 1 else weather(**kwargs)

    monkeypatch.setitem(TOOL_MAP, "get_weather_forecast", flaky_weather)
    result = ReActAgent().run("Thời tiết HAN thế nào?")
    assert result["status"] == "completed"
    assert "22°C" in result["answer"]


def test_iteration_limit_and_independent_trace():
    agent = ReActAgent(max_iterations=2)
    result = agent.run("Tìm chuyến bay HAN đi SGN dưới 2 triệu và thời tiết SGN")
    assert result["status"] == "max_iterations_reached"
    assert result["iterations"] == 2
    first_trace = result["trace"]
    second = agent.run("Thời tiết HAN thế nào?")
    assert second["status"] == "completed"
    assert len(first_trace) == 2
    assert len(second["trace"]) == 1
