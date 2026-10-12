"""pytest 公共配置。

- 在导入 PyQt5 之前设置 QT_QPA_PLATFORM=offscreen，保证无显示器环境（CI）下
  也能创建 QApplication / QWidget，避免平台插件加载失败。
- 把项目根目录加入 sys.path，使 tests 包内可直接 import weather_service 等模块。
- 提供 session 级 qapp fixture，全局复用唯一 QApplication 实例。
"""

import os
import sys

# 必须在任何 PyQt5 组件被实例化之前生效；conftest 在测试模块收集阶段先于
# 测试模块体执行，故在此设置即可覆盖所有用例。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 将项目根目录（conftest 的上一级）加入 sys.path，确保可 import 项目源码。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """提供全局唯一的 QApplication 实例（offscreen）。

    所有需要 GUI 的测试用例显式声明 qapp 参数即可触发创建。
    若已有实例则复用，避免多次构造引发警告。
    """
    app = QApplication.instance() or QApplication(sys.argv)
    return app
