"""WeatherWorker 后台线程测试。

不依赖 pytest-qt，使用 PyQt5.QtTest.QSignalSpy + conftest 的 qapp fixture。
通过 `with patch(...)` 体内隔离 weather_worker.get_weather，仅验证线程化封装。

注：不使用 `@patch` 装饰器形式，因当前 pytest 版本下 `@patch` 与 pytest
fixture 参数（qapp）混用会导致 "fixture 'mock_*' not found"。
"""

from unittest.mock import patch

from PyQt5.QtTest import QSignalSpy

from weather_worker import WeatherWorker


def _full_result():
    """构造一份完整天气结果 dict。"""
    return {
        "city": "北京",
        "date": "2026-10-12",
        "temp_max": 25.5,
        "temp_min": 15.2,
        "weather_desc": "多云",
        "wind_speed": 10.5,
        "wind_dir": "东",
        "humidity": 70,
    }


def test_worker_emits_result_ready(qapp):
    """get_weather 成功时 result_ready 信号应携带正确 dict。"""
    with patch("weather_worker.get_weather", return_value=_full_result()) as mock_get_weather:
        w = WeatherWorker("北京", "2026-10-12")
        spy = QSignalSpy(w.result_ready)
        w.start()

        assert spy.wait(5000), "result_ready 信号未在超时内到达"
        assert len(spy) == 1
        result = spy[0][0]
        assert result["city"] == "北京"
        assert result["date"] == "2026-10-12"
        assert result["temp_max"] == 25.5
        assert result["weather_desc"] == "多云"
        assert result["wind_dir"] == "东"
        # 确保线程真正退出，避免对象析构异常
        assert w.wait(2000)
        # get_weather 被以正确参数调用一次
        mock_get_weather.assert_called_once_with("北京", "2026-10-12")


def test_worker_emits_error_on_value_error(qapp):
    """get_weather 抛 ValueError 时 error_occurred 信号应被发射。"""
    with patch("weather_worker.get_weather", side_effect=ValueError("未知城市: 火星")):
        w = WeatherWorker("火星", "2026-10-12")
        spy = QSignalSpy(w.error_occurred)
        w.start()

        assert spy.wait(5000), "error_occurred 信号未在超时内到达"
        assert len(spy) == 1
        msg = spy[0][0]
        assert "未知城市" in msg
        assert w.wait(2000)


def test_worker_emits_error_on_runtime_error(qapp):
    """get_weather 抛 RuntimeError 时 error_occurred 信号应被发射。"""
    with patch("weather_worker.get_weather", side_effect=RuntimeError("网络请求失败: timeout")):
        w = WeatherWorker("北京", "2026-10-12")
        spy = QSignalSpy(w.error_occurred)
        w.start()

        assert spy.wait(5000), "error_occurred 信号未在超时内到达"
        assert len(spy) == 1
        msg = spy[0][0]
        assert "网络请求失败" in msg
        assert w.wait(2000)
