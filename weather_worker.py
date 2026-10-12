"""后台工作线程模块。

在独立 QThread 中调用天气服务，避免网络请求阻塞 UI 主线程。
通过 Qt 信号把查询结果或错误回传主线程进行展示。

注意：自定义信号名刻意避开 QThread 内置的 finished 信号（无参），
使用 result_ready / error_occurred 避免同名冲突。
"""

from PyQt5.QtCore import QThread, pyqtSignal

from weather_service import get_weather


class WeatherWorker(QThread):
    """天气查询后台线程。

    用法：
        worker = WeatherWorker(city, date_str)
        worker.result_ready.connect(on_ok)     # 接收 dict 结果
        worker.error_occurred.connect(on_err)  # 接收 str 错误信息
        worker.finished.connect(worker.deleteLater)  # 线程结束自动清理
        worker.start()

    信号:
        result_ready(dict):  查询成功，携带结构化天气数据。
        error_occurred(str): 查询失败，携带用户友好的错误信息。
    """

    # 注意：不要命名为 finished，会与 QThread 内置信号同名冲突。
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, city, date_str, parent=None):
        super().__init__(parent)
        self._city = city
        self._date_str = date_str

    def run(self):
        """线程入口：调用业务逻辑并以信号回传结果/错误。"""
        try:
            result = get_weather(self._city, self._date_str)
            self.result_ready.emit(result)
        except ValueError as exc:
            # 输入类错误（未知城市/日期格式）。
            self.error_occurred.emit(str(exc))
        except RuntimeError as exc:
            # 网络/解析/数据缺失类错误。
            self.error_occurred.emit(str(exc))
        except Exception as exc:  # 兜底，保证任何异常都不会让线程静默崩溃。
            self.error_occurred.emit(f"查询天气时发生未知错误: {exc}")
