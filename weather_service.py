"""天气服务模块。

封装 Open-Meteo 免费免 Key 天气 API 的调用、城市经纬度映射、WMO 天气代码翻译。

本模块刻意保持为纯业务逻辑（不依赖任何 GUI 库），便于被独立 import 进行单元测试。
所有 API 解析逻辑集中在此处，主窗口只负责调用与展示。
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime


# Open-Meteo 每日预报接口（完全免费、无需 API Key）。
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# 城市名 -> (纬度, 经度) 映射，覆盖常用中国城市。
CITIES = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "成都": (30.5728, 104.0668),
    "杭州": (30.2741, 120.1551),
    "武汉": (30.5928, 114.3052),
    "西安": (34.3416, 108.9398),
    "南京": (32.0603, 118.7969),
    "重庆": (29.5630, 106.5516),
    "天津": (39.3434, 117.3616),
    "苏州": (31.2989, 120.5853),
}

# WMO weather interpretation code -> 中文天气描述。
# 参考 Open-Meteo 官方文档：0=晴、1-3=晴朗/多云/阴、45/48=雾、
# 51-67=毛毛雨/雨、71-77=雪、80-82=阵雨、85-86=阵雪、95-99=雷暴。
WMO_CODE_DESC = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中毛毛雨",
    55: "大毛毛雨",
    56: "轻冻毛毛雨",
    57: "重冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻冻雨",
    67: "重冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}

# 请求超时时间（秒），避免长时间卡死后台线程。
REQUEST_TIMEOUT = 15


def weathercode_to_desc(code):
    """将 WMO weather interpretation code 翻译为中文天气描述。

    参数:
        code: WMO 天气代码（int 或 None）

    返回:
        str: 中文天气描述；未知或缺失返回 "未知"。
    """
    if code is None:
        return "未知"
    try:
        return WMO_CODE_DESC.get(int(code), "未知")
    except (TypeError, ValueError):
        return "未知"


def winddirection_to_desc(deg):
    """将风向角度（0-360）转换为中文方位描述（八方位）。

    参数:
        deg: 风向角度（int/float 或 None）

    返回:
        str: 北/东北/东/东南/南/西南/西/西北；缺失返回 "未知"。
    """
    if deg is None:
        return "未知"
    try:
        angle = float(deg)
    except (TypeError, ValueError):
        return "未知"
    # 每个方位覆盖 45° 区间，0° 正北、按顺时针递增。
    # 末位多放一个 "北" 以覆盖 337.5°-360° 的环绕情况。
    directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北", "北"]
    index = int((angle + 22.5) / 45.0)
    # 边界角度（22.5/67.5/.../337.5）应归属低方位（闭区间右端归属低方位）
    if index > 0 and (angle % 45.0) == 22.5:
        index -= 1
    if index < 0:
        index = 0
    elif index > 8:
        index = 8
    return directions[index]


def _format_value(values, index):
    """安全从日数据列表中取第 index 项，缺失或越界返回 None。"""
    if not values or index < 0 or index >= len(values) or values[index] is None:
        return None
    return values[index]


def get_weather(city, date_str):
    """查询指定城市、指定日期的天气情况。

    流程：城市校验 -> 日期校验 -> 拼接 Open-Meteo 请求 -> 发起 HTTP ->
    解析 JSON -> 提取当日字段并翻译为中文描述。

    参数:
        city: 城市名，需存在于 CITIES 字典中。
        date_str: 日期字符串，格式 YYYY-MM-DD（建议在 Open-Meteo 预报支持的范围内）。

    返回:
        dict: 结构化天气数据，字段如下：
            city          城市名
            date          日期字符串 YYYY-MM-DD
            temp_max      最高气温（℃，float 或 None）
            temp_min      最低气温（℃，float 或 None）
            weather_desc  天气状况中文描述
            wind_speed    最大风速（km/h，float 或 None）
            wind_dir      主导风向中文描述
            humidity      最大相对湿度（%，float 或 None）

    异常:
        ValueError:  未知城市或日期格式非法。
        RuntimeError: 网络请求失败、响应解析失败或所选日期无数据。
    """
    # 1. 城市校验：取经纬度。
    if city not in CITIES:
        raise ValueError(f"未知城市: {city}")
    lat, lon = CITIES[city]

    # 2. 日期格式校验。
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError(f"日期格式非法，应为 YYYY-MM-DD: {date_str}")

    # 3. 拼接请求参数：只取所需 daily 字段，限定起止日期为同一天以减少传输量。
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "weathercode",
            "windspeed_10m_max",
            "winddirection_10m_dominant",
            "relative_humidity_2m_max",
        ]),
        "timezone": "Asia/Shanghai",
        "start_date": date_str,
        "end_date": date_str,
    }
    url = f"{OPEN_METEO_FORECAST_URL}?{urllib.parse.urlencode(params)}"

    # 4. 发起 HTTP 请求（使用标准库 urllib，无需额外依赖）。
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "CityDateWeather/1.0"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络请求失败: {exc}") from exc
    except Exception as exc:  # 超时等其他不可预期异常。
        raise RuntimeError(f"网络请求异常: {exc}") from exc

    # 5. 解析 JSON。
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"返回数据解析失败: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("API 返回数据格式异常")

    # 6. 提取目标日期数据。
    daily = data.get("daily")
    if not daily:
        raise RuntimeError("API 未返回每日天气数据")

    times = daily.get("time") or []
    if date_str not in times:
        raise RuntimeError(f"所选日期无天气数据: {date_str}")

    idx = times.index(date_str)
    temp_max = _format_value(daily.get("temperature_2m_max"), idx)
    temp_min = _format_value(daily.get("temperature_2m_min"), idx)
    code = _format_value(daily.get("weathercode"), idx)
    wind_speed = _format_value(daily.get("windspeed_10m_max"), idx)
    wind_dir_deg = _format_value(daily.get("winddirection_10m_dominant"), idx)
    humidity = _format_value(daily.get("relative_humidity_2m_max"), idx)

    return {
        "city": city,
        "date": date_str,
        "temp_max": temp_max,
        "temp_min": temp_min,
        "weather_desc": weathercode_to_desc(code),
        "wind_speed": wind_speed,
        "wind_dir": winddirection_to_desc(wind_dir_deg),
        "humidity": humidity,
    }
