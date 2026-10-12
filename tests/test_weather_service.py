"""weather_service 核心业务逻辑的完整单元测试。

覆盖：
- CITIES / WMO_CODE_DESC 数据完整性
- weathercode_to_desc：已知/未知/None/非法类型
- winddirection_to_desc：八方位 + 边界 + None/非法
- _format_value：正常/越界/负索引/None元素/空列表
- get_weather：mock urlopen 的正常路径、URL 拼接、未知城市、非法日期、
  URLError、非 JSON、非 dict、daily 缺失/空、目标日期缺失等异常分支

所有网络请求均被 mock，绝不发起真实 HTTP。
"""

import json
import urllib.error

import pytest
from unittest.mock import patch

from weather_service import (
    CITIES,
    WMO_CODE_DESC,
    _format_value,
    get_weather,
    weathercode_to_desc,
    winddirection_to_desc,
)


# ---------------------------------------------------------------------------
# 测试辅助：构造伪造的 urlopen 返回（上下文管理器 + read()）
# ---------------------------------------------------------------------------
class _FakeResponse:
    """模拟 urllib.request.urlopen 返回的上下文管理器响应对象。"""

    def __init__(self, payload):
        if isinstance(payload, str):
            self._data = payload.encode("utf-8")
        else:
            self._data = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._data


def _resp(payload):
    """快捷构造一个 FakeResponse。"""
    return _FakeResponse(payload)


# ===========================================================================
# 数据完整性
# ===========================================================================
def test_cities_have_coords():
    """CITIES 至少 12 个城市，每个值为长度 2 的数值经纬度。"""
    assert len(CITIES) >= 12
    for name, coord in CITIES.items():
        assert isinstance(name, str) and name, f"城市名非法: {name!r}"
        assert len(coord) == 2, f"{name} 经纬度长度应为 2，实际 {len(coord)}"
        lat, lon = coord
        assert isinstance(lat, (int, float)), f"{name} 纬度非数值: {lat!r}"
        assert isinstance(lon, (int, float)), f"{name} 经度非数值: {lon!r}"
        # 经纬度应在合理范围
        assert -90 <= lat <= 90, f"{name} 纬度越界: {lat}"
        assert -180 <= lon <= 180, f"{name} 经度越界: {lon}"


def test_wmo_code_desc_non_empty():
    """WMO_CODE_DESC 非空且包含常用 code。"""
    assert WMO_CODE_DESC, "WMO_CODE_DESC 不应为空"
    assert WMO_CODE_DESC.get(0) == "晴"
    assert WMO_CODE_DESC.get(2) == "多云"
    assert WMO_CODE_DESC.get(3) == "阴"
    assert WMO_CODE_DESC.get(61) == "小雨"
    assert WMO_CODE_DESC.get(95) == "雷暴"


# ===========================================================================
# weathercode_to_desc
# ===========================================================================
def test_weathercode_known():
    assert weathercode_to_desc(0) == "晴"
    assert weathercode_to_desc(2) == "多云"
    assert weathercode_to_desc(3) == "阴"
    assert weathercode_to_desc(61) == "小雨"
    assert weathercode_to_desc(95) == "雷暴"


def test_weathercode_none():
    assert weathercode_to_desc(None) == "未知"


def test_weathercode_unknown_code():
    assert weathercode_to_desc(999) == "未知"


def test_weathercode_illegal_string():
    """非法字符串 code 应安全返回“未知”。"""
    assert weathercode_to_desc("abc") == "未知"


def test_weathercode_illegal_list():
    """非法类型（list）应安全返回“未知”。"""
    assert weathercode_to_desc([1, 2]) == "未知"


# ===========================================================================
# winddirection_to_desc
# ===========================================================================
def test_winddirection_cardinals():
    """八方位主刻度映射正确。"""
    assert winddirection_to_desc(0) == "北"
    assert winddirection_to_desc(90) == "东"
    assert winddirection_to_desc(180) == "南"
    assert winddirection_to_desc(270) == "西"
    assert winddirection_to_desc(45) == "东北"
    assert winddirection_to_desc(225) == "西南"
    assert winddirection_to_desc(360) == "北"


def test_winddirection_none():
    assert winddirection_to_desc(None) == "未知"


def test_winddirection_illegal():
    """非法类型应返回“未知”。"""
    assert winddirection_to_desc("abc") == "未知"
    assert winddirection_to_desc([1]) == "未知"


def test_winddirection_boundary():
    """区间边界：22.5° 应属“北”，22.6° 应属“东北”（验证区间划分）。"""
    assert winddirection_to_desc(22.5) == "北"
    assert winddirection_to_desc(22.6) == "东北"


# ===========================================================================
# _format_value
# ===========================================================================
def test_format_value_normal():
    assert _format_value([1, 2, 3], 1) == 2


def test_format_value_index_out_of_range():
    """index 越界（>=len）应返回 None。"""
    assert _format_value([1, 2], 5) is None


def test_format_value_negative_index():
    """负索引应返回 None（验证 m-2 修复生效，避免 Python 负索引取值）。"""
    assert _format_value([1, 2, 3], -1) is None


def test_format_value_none_element():
    """元素为 None 应返回 None。"""
    assert _format_value([None, 2], 0) is None


def test_format_value_empty_list():
    assert _format_value([], 0) is None


def test_format_value_none_values():
    """values 本身为 None 应返回 None。"""
    assert _format_value(None, 0) is None


# ===========================================================================
# get_weather：mock urlopen 全场景
# ===========================================================================
@patch("weather_service.urllib.request.urlopen")
def test_get_weather_normal(mock_urlopen):
    """正常路径：构造符合 Open-Meteo daily 结构的假响应，断言解析与翻译正确。"""
    payload = {
        "daily": {
            "time": ["2026-10-12"],
            "temperature_2m_max": [25.5],
            "temperature_2m_min": [15.2],
            "weathercode": [2],
            "windspeed_10m_max": [10.5],
            "winddirection_10m_dominant": [90],
            "relative_humidity_2m_max": [70],
        }
    }
    mock_urlopen.return_value = _resp(json.dumps(payload))

    result = get_weather("北京", "2026-10-12")

    assert result["city"] == "北京"
    assert result["date"] == "2026-10-12"
    assert result["temp_max"] == 25.5
    assert result["temp_min"] == 15.2
    assert result["weather_desc"] == "多云"  # weathercode 2 -> 多云
    assert result["wind_speed"] == 10.5
    assert result["wind_dir"] == "东"  # 90° -> 东
    assert result["humidity"] == 70
    # 确保只发起一次请求
    assert mock_urlopen.call_count == 1


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_request_url(mock_urlopen):
    """验证传给 urlopen 的 URL 拼接含必需参数。"""
    payload = {"daily": {"time": ["2026-10-12"], "weathercode": [0]}}
    mock_urlopen.return_value = _resp(json.dumps(payload))

    get_weather("北京", "2026-10-12")

    assert mock_urlopen.call_count == 1
    # call_args[0][0] 是第一个位置参数，即 urllib.request.Request 对象
    req = mock_urlopen.call_args[0][0]
    url = req.full_url
    assert "latitude=39.9042" in url
    assert "longitude=116.4074" in url
    assert "daily=temperature_2m_max" in url
    assert "timezone=Asia" in url  # "/" 被 urlencode 为 %2F
    assert "start_date=2026-10-12" in url
    assert "end_date=2026-10-12" in url
    # 请求超时参数
    assert mock_urlopen.call_args.kwargs.get("timeout") == 15


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_partial_and_none_fields(mock_urlopen):
    """部分字段缺失 / None 时，对应结果应为 None，中文描述兜底“未知”。"""
    payload = {
        "daily": {
            "time": ["2026-10-12"],
            "weathercode": [None],          # -> weather_desc "未知"
            "winddirection_10m_dominant": [None],  # -> wind_dir "未知"
            # temperature_2m_max / temp_min / wind_speed / humidity 全缺
        }
    }
    mock_urlopen.return_value = _resp(json.dumps(payload))

    result = get_weather("北京", "2026-10-12")
    assert result["temp_max"] is None
    assert result["temp_min"] is None
    assert result["wind_speed"] is None
    assert result["humidity"] is None
    assert result["weather_desc"] == "未知"
    assert result["wind_dir"] == "未知"


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_unknown_city(mock_urlopen):
    """未知城市应抛 ValueError，且不发起网络请求。"""
    with pytest.raises(ValueError, match="未知城市"):
        get_weather("火星", "2026-10-12")
    assert mock_urlopen.call_count == 0


@pytest.mark.parametrize("bad_date", ["2026-13-45", "2026/01/01", None, ""])
@patch("weather_service.urllib.request.urlopen")
def test_get_weather_invalid_date(mock_urlopen, bad_date):
    """非法日期格式应抛 ValueError。"""
    with pytest.raises(ValueError, match="日期格式非法"):
        get_weather("北京", bad_date)
    assert mock_urlopen.call_count == 0


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_urlerror(mock_urlopen):
    """urlopen 抛 URLError -> get_weather 抛 RuntimeError（消息含“网络请求失败”）。"""
    mock_urlopen.side_effect = urllib.error.URLError("boom")
    with pytest.raises(RuntimeError, match="网络请求失败"):
        get_weather("北京", "2026-10-12")


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_non_json_response(mock_urlopen):
    """urlopen 返回非 JSON 字符串 -> json 解析失败抛 RuntimeError。"""
    mock_urlopen.return_value = _resp("not a json {")
    with pytest.raises(RuntimeError, match="解析失败"):
        get_weather("北京", "2026-10-12")


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_non_dict_json(mock_urlopen):
    """返回合法 JSON 但不是 dict -> 抛 RuntimeError（消息含“格式异常”，验证 m-3）。"""
    mock_urlopen.return_value = _resp("[1, 2, 3]")
    with pytest.raises(RuntimeError, match="格式异常"):
        get_weather("北京", "2026-10-12")


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_daily_missing(mock_urlopen):
    """daily 缺失 -> 抛 RuntimeError。"""
    mock_urlopen.return_value = _resp(json.dumps({"other": 1}))
    with pytest.raises(RuntimeError, match="未返回每日天气"):
        get_weather("北京", "2026-10-12")


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_daily_empty(mock_urlopen):
    """daily 为空 dict -> 抛 RuntimeError。"""
    mock_urlopen.return_value = _resp(json.dumps({"daily": {}}))
    with pytest.raises(RuntimeError, match="未返回每日天气"):
        get_weather("北京", "2026-10-12")


@patch("weather_service.urllib.request.urlopen")
def test_get_weather_date_not_in_times(mock_urlopen):
    """daily.time 不含目标日期 -> 抛 RuntimeError（消息含“无天气数据”）。"""
    payload = {"daily": {"time": ["2026-10-11"], "weathercode": [0]}}
    mock_urlopen.return_value = _resp(json.dumps(payload))
    with pytest.raises(RuntimeError, match="无天气数据"):
        get_weather("北京", "2026-10-12")
