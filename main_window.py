"""主窗口模块。

构建 UI、连接信号槽，并将后台线程查询结果绑定到界面展示。
所有 API 解析逻辑均位于 weather_service.py，本模块只负责交互与渲染。
"""

from html import escape as html_escape

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from weather_service import CITIES
from weather_worker import WeatherWorker

# 日期选择范围：今日起未来 N 天（Open-Meteo 预报最长约 16 天，此处取 6 天共 7 天可选）。
FORECAST_DAYS = 6


class MainWindow(QMainWindow):
    """城市 + 日期天气查询主窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("城市日期天气查询")
        self.resize(540, 480)

        # 持有当前后台线程引用，防止被 Python GC 回收导致线程异常终止。
        self._worker = None

        self._init_ui()
        self._init_connections()
        self.statusBar().showMessage("请选择城市和日期后点击查询")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 标题
        title = QLabel("城市日期天气查询")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        root.addWidget(title)

        # 控制行：城市下拉 + 日期选择 + 查询按钮
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("城市:"))
        self.city_combo = QComboBox()
        for name in CITIES:
            self.city_combo.addItem(name)
        ctrl.addWidget(self.city_combo, 1)

        ctrl.addSpacing(10)
        ctrl.addWidget(QLabel("日期:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        # 限定可选范围为今日起未来 7 天（Open-Meteo 预报支持窗口）。
        today = QDate.currentDate()
        self.date_edit.setDate(today)
        self.date_edit.setMinimumDate(today)
        self.date_edit.setMaximumDate(today.addDays(FORECAST_DAYS))
        ctrl.addWidget(self.date_edit, 1)

        ctrl.addSpacing(10)
        self.query_btn = QPushButton("查询")
        ctrl.addWidget(self.query_btn)
        root.addLayout(ctrl)

        # 提示
        hint = QLabel("提示：日期可选范围为今日起未来 7 天")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

        # 结果展示区（只读）
        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("查询结果将显示在此处……")
        root.addWidget(self.result_view, 1)

    def _init_connections(self):
        self.query_btn.clicked.connect(self._on_query)

    # ------------------------------------------------------------------
    # 槽函数
    # ------------------------------------------------------------------
    def _on_query(self):
        """点击查询：启动后台线程，禁用按钮防止重复提交。"""
        city = self.city_combo.currentText().strip()
        date_str = self.date_edit.date().toString("yyyy-MM-dd")

        if not city:
            QMessageBox.warning(self, "提示", "请选择城市")
            return

        # 若上一次查询仍在进行，忽略重复点击。
        if self._worker is not None and self._worker.isRunning():
            return

        self.query_btn.setEnabled(False)
        self.result_view.clear()
        self.statusBar().showMessage(f"正在查询 {city} {date_str} 的天气……")

        # 创建后台线程并连接结果/错误/结束信号。
        self._worker = WeatherWorker(city, date_str, self)
        self._worker.result_ready.connect(self._on_result_ready)
        self._worker.error_occurred.connect(self._on_error_occurred)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_result_ready(self, result):
        """查询成功：渲染结构化结果到结果区。"""
        self._render_result(result)
        self.statusBar().showMessage("查询完成", 5000)

    def _on_error_occurred(self, message):
        """查询失败：弹出友好提示并更新状态栏。"""
        self.result_view.clear()
        QMessageBox.warning(self, "查询失败", message)
        self.statusBar().showMessage("查询失败")

    def _on_worker_finished(self):
        """线程结束：恢复按钮可用并清理 worker 引用。"""
        self.query_btn.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def closeEvent(self, event):
        """窗口关闭前等待后台线程退出，避免销毁运行中的线程导致崩溃。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
            if self._worker.isRunning():
                self._worker.terminate()
                self._worker.wait(1000)
        event.accept()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def _render_result(self, r):
        """将天气字典渲染为简洁 HTML 表格。"""
        city = html_escape(str(r.get("city", "")))
        d = html_escape(str(r.get("date", "")))
        desc = html_escape(str(r.get("weather_desc", "未知")))
        wdir = html_escape(str(r.get("wind_dir", "未知")))

        def fmt(val, unit=""):
            """缺失值统一显示为占位文本。"""
            if val is None:
                return "暂无数据"
            return html_escape(f"{val}{unit}")

        html = (
            "<div style='line-height:1.9; font-size:14px;'>"
            f"<h3 style='margin:4px 0;'>{city} - {d} 天气</h3>"
            "<table cellpadding='4' cellspacing='0'>"
            f"<tr><td>天气状况:</td><td><b>{desc}</b></td></tr>"
            f"<tr><td>最高气温:</td><td>{fmt(r.get('temp_max'), ' ℃')}</td></tr>"
            f"<tr><td>最低气温:</td><td>{fmt(r.get('temp_min'), ' ℃')}</td></tr>"
            f"<tr><td>风力风速:</td><td>{fmt(r.get('wind_speed'), ' km/h')} (风向: {wdir})</td></tr>"
            f"<tr><td>相对湿度:</td><td>{fmt(r.get('humidity'), ' %')}</td></tr>"
            "</table>"
            "<p style='color:gray; font-size:11px;'>数据来源: Open-Meteo</p>"
            "</div>"
        )
        self.result_view.setHtml(html)
