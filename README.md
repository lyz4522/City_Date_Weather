# 城市日期天气查询

基于 Python + PyQt5 的桌面应用：根据所选城市与日期显示实际天气情况（气温、天气状况、风力风向、湿度）。

## 功能

- 城市下拉选择（内置 12 个常用中国城市经纬度映射）
- 日期选择（今日起未来 7 天，Open-Meteo 预报支持范围）
- 后台线程发起网络请求，不阻塞 UI；窗口关闭时安全等待线程退出
- 友好的错误提示（网络异常 / 日期无数据 / 未知城市等）
- WMO weather code 与风向角度均映射为中文描述
- 结果区对 API 返回值做 HTML 转义，防止异常内容注入
- 天气数据来源：[Open-Meteo](https://open-meteo.com/)（免费、免 API Key）

## 项目结构

```
weather_service.py   # 天气服务：API 调用、解析、城市映射、WMO code 映射（纯业务逻辑，可独立测试）
weather_worker.py    # 后台工作线程（QThread + 信号）
main_window.py       # 主窗口 UI（交互、渲染、closeEvent）
app.py               # 程序入口
requirements.txt     # 运行依赖
requirements-dev.txt # 测试依赖
.gitignore
tests/
  conftest.py            # offscreen 平台设置 + QApplication fixture
  test_weather_service.py # 业务逻辑测试（31 例）
  test_main_window.py    # 主窗口 UI 逻辑测试（7 例）
  test_weather_worker.py  # 后台线程测试（3 例）
```

## 架构

业务逻辑与 UI 分离，保证可测试性：

- `weather_service.py` 不依赖任何 GUI 库，可被单独 `import` 进行单元测试。
- `main_window.py` 仅负责交互与渲染，所有 API 解析逻辑集中在 `weather_service.py`。
- 网络请求在 `WeatherWorker(QThread)` 中执行，通过 `result_ready` / `error_occurred` 信号回传主线程，避免阻塞 UI。

## 依赖

- Python 3.8+（开发环境为 3.13.9）
- PyQt5 5.15+

安装运行依赖：

```bash
pip install -r requirements.txt
```

## 运行

```bash
python app.py
```

## 测试

共 41 个单元测试，覆盖业务逻辑、主窗口交互与后台线程。测试全部使用 mock，**不发起真实网络请求**，可离线运行。

安装测试依赖：

```bash
pip install -r requirements-dev.txt
```

执行测试：

```bash
# 桌面/无显示器环境通用命令（offscreen 平台 + 禁用字节码缓存写入）
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v -p no:cacheprovider
```

预期结果：`41 passed`。
