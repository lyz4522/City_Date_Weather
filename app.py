"""程序入口：创建 QApplication 与主窗口并启动事件循环。

运行方式：python app.py
"""

import sys

from PyQt5.QtWidgets import QApplication

from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
