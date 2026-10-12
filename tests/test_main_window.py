"""MainWindow UI 逻辑测试。

不依赖 pytest-qt，使用 conftest 提供的 qapp fixture + offscreen 平台。
所有网络/线程相关行为均通过 mock 隔离，UI 操作直接调用槽函数。
"""

from unittest.mock import patch

from main_window import MainWindow


# ---------------------------------------------------------------------------
# 辅助：伪造 QCloseEvent
# ---------------------------------------------------------------------------
class FakeEvent:
    """模拟 Qt 关闭事件，仅记录 accept 是否被调用。"""

    def __init__(self):
        self.accepted = False

    def accept(self):
        self.accepted = True


class FakeWorker:
    """模拟 WeatherWorker，用于 closeEvent / _on_query 的线程状态判断。"""

    def __init__(self, running=True):
        self._running = running
        self.wait_called = False
        self.terminate_called = False
        self.started = False

    def isRunning(self):
        return self._running

    def wait(self, _ms=0):
        self.wait_called = True
        self._running = False
        return True

    def terminate(self):
        self.terminate_called = True

    def start(self):
        self.started = True


# ===========================================================================
# closeEvent（验证 M-1 修复：存在且可调用，调用 event.accept）
# ===========================================================================
def test_close_event_no_worker_accepts(qapp):
    """无 worker 时 closeEvent 应直接 accept。"""
    mw = MainWindow()
    ev = FakeEvent()
    mw.closeEvent(ev)
    assert ev.accepted is True


def test_close_event_with_running_worker_waits(qapp):
    """有运行中 worker 时应先 wait 再 accept，且线程已退出则不 terminate。"""
    mw = MainWindow()
    fw = FakeWorker(running=True)
    mw._worker = fw
    ev = FakeEvent()
    mw.closeEvent(ev)
    assert fw.wait_called is True
    assert fw.terminate_called is False  # wait 后线程已退出，无需 terminate
    assert ev.accepted is True


# ===========================================================================
# _render_result
# ===========================================================================
def test_render_result_displays_data(qapp):
    """渲染结果应包含城市、日期、天气、温度等关键字段。"""
    mw = MainWindow()
    data = {
        "city": "北京",
        "date": "2026-10-12",
        "temp_max": 25.5,
        "temp_min": 15.2,
        "weather_desc": "多云",
        "wind_speed": 10.5,
        "wind_dir": "东",
        "humidity": 70,
    }
    mw._render_result(data)
    html = mw.result_view.toHtml()
    assert "北京" in html
    assert "2026-10-12" in html
    assert "多云" in html
    assert "25.5" in html
    assert "15.2" in html
    assert "东" in html
    assert "70" in html


def test_render_result_none_values_placeholder(qapp):
    """缺失值应渲染为“暂无数据”占位文本。"""
    mw = MainWindow()
    data = {
        "city": "北京",
        "date": "2026-10-12",
        "weather_desc": "晴",
        "wind_dir": "北",
        # temp_max/temp_min/wind_speed/humidity 均缺失
    }
    mw._render_result(data)
    html = mw.result_view.toHtml()
    assert "暂无数据" in html


def test_render_result_escapes_html(qapp):
    """含 HTML 特殊字符的值应被转义，避免 XSS（验证 m-4 修复）。"""
    mw = MainWindow()
    data = {
        "city": "北京",
        "date": "2026-10-12",
        "weather_desc": "<script>alert(1)</script>",
        "wind_dir": "<b>北</b>",
    }
    mw._render_result(data)
    html = mw.result_view.toHtml()
    # 原始标签不应作为真实 HTML 出现
    assert "<script>" not in html
    assert "<b>北</b>" not in html
    # 应以转义形式存在
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;" in html


# ===========================================================================
# _on_query
# ===========================================================================
def test_on_query_warns_when_no_city(qapp):
    """无城市选择时应弹出警告且不启动 worker。"""
    mw = MainWindow()
    mw.city_combo.clear()  # 清空城市 -> currentText() 为空
    with patch("main_window.QMessageBox") as mock_qmb:
        mw._on_query()
    # 弹出 warning 警告
    assert mock_qmb.warning.called, "应调用 QMessageBox.warning"
    # 未创建 worker
    assert mw._worker is None
    # 按钮未被禁用
    assert mw.query_btn.isEnabled() is True


def test_on_query_skips_when_worker_running(qapp):
    """已有 worker 运行时点击查询不应重复启动。"""
    mw = MainWindow()
    fw = FakeWorker(running=True)
    mw._worker = fw
    # city_combo 默认有“北京”，日期默认今天，均为合法值
    mw._on_query()
    # 不应替换为新 worker，也不应再次 start
    assert mw._worker is fw
    assert fw.started is False
    # 按钮不应被禁用（提前 return）
    assert mw.query_btn.isEnabled() is True
