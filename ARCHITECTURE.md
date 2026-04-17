# 微信 GUI 控制程序架构设计

## 1. 项目目标

构建一个桌面 GUI 程序，通过界面配置和执行微信相关操作。第一阶段重点是**控制已登录的桌面微信客户端**，而不是自行实现微信协议。

核心原则：

- 先做 **桌面自动化控制**，不碰高风险协议逆向
- GUI、业务逻辑、自动化驱动分层，避免后续难以维护
- 优先支持 **MVP 可跑通**：选联系人、发消息、批量任务、执行日志
- 架构上预留插件化能力，后续可扩展更多动作和任务流

## 2. 范围定义

### 2.1 第一阶段建议范围

- 启动和连接微信控制会话
- 检测微信是否已打开、是否处于登录状态
- 搜索联系人 / 群聊
- 发送文本消息
- 发送图片或文件
- 批量执行消息任务
- GUI 中展示执行状态、日志、失败原因

### 2.2 暂不建议第一阶段实现

- 微信通信协议逆向
- 多账号并发登录管理
- 云端远程控制
- 高并发群发
- 自动加好友、自动拉群等高风险功能

## 3. 技术路线建议

建议先基于 **Python + 桌面 GUI + macOS 辅助功能自动化** 实现。

### 推荐技术栈

- GUI：`PySide6`
- 业务模型：Python `dataclasses` / `pydantic`
- 自动化层：
  - macOS 原生桥接：`pyobjc`
  - 系统脚本能力：`AppleScript` / `System Events`
  - 通用补充：`pyautogui`
  - 图像识别兜底：`opencv-python`
  - 可选 OCR：`PaddleOCR` 或 macOS `Vision`
- 任务调度：`APScheduler`
- 本地存储：`SQLite`
- 日志：`loguru` 或标准库 `logging`
- 配置：`yaml` 或 `toml`
- 打包：`PyInstaller`

### 为什么优先选 Python

- GUI 开发效率高，适合快速验证
- 桌面自动化生态成熟
- 图像识别、OCR、调度、数据存储都容易接入
- 后续如果需要，把自动化引擎拆成独立进程也比较自然

### macOS 第一版实现建议

第一版既然只支持 macOS，建议自动化优先级按下面走：

1. `Accessibility API` / `System Events`：优先获取窗口、菜单、输入控件
2. `AppleScript`：负责应用激活、窗口切换、少量系统级操作
3. `pyautogui`：用于键盘输入、鼠标点击等兜底操作
4. `OpenCV + OCR`：用于控件识别失败时的视觉定位

这个顺序比纯坐标点击更稳，因为 macOS 下微信版本变化时，纯图像方案维护成本会更高。

## 4. 总体架构

建议采用 5 层架构：

1. 表现层 `Presentation`
2. 应用层 `Application`
3. 领域层 `Domain`
4. 基础设施层 `Infrastructure`
5. 自动化适配层 `Automation Adapter`

```text
+--------------------------------------------------+
| GUI (PySide6)                                    |
| 窗口 / 表单 / 任务面板 / 日志面板 / 配置页         |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
| Application                                      |
| UseCases / Command Handlers / Task Orchestrator  |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
| Domain                                           |
| Session / Contact / Message / Task / Result      |
+--------------------------+-----------------------+
                           |
             +-------------+-------------+
             |                           |
             v                           v
+---------------------------+  +--------------------------+
| Infrastructure            |  | Automation Adapter       |
| SQLite / Config / Logging |  | WeChat UI Driver         |
| File Storage / Scheduler  |  | Window / OCR / Image     |
+---------------------------+  +--------------------------+
```

## 5. 模块拆分

### 5.1 `gui`

职责：

- 展示主窗口、配置页、任务面板、日志面板
- 接收用户输入
- 触发应用层命令
- 展示执行结果

建议子模块：

- `gui/main_window.py`
- `gui/pages/session_page.py`
- `gui/pages/message_page.py`
- `gui/pages/task_page.py`
- `gui/pages/log_page.py`
- `gui/widgets/*`
- `gui/viewmodels/*`

### 5.2 `application`

职责：

- 承接 GUI 请求
- 组装领域对象
- 调用自动化服务和存储服务
- 管理任务执行流程

建议子模块：

- `application/usecases/connect_wechat.py`
- `application/usecases/send_message.py`
- `application/usecases/send_file.py`
- `application/usecases/run_batch_task.py`
- `application/usecases/query_logs.py`
- `application/services/task_orchestrator.py`

### 5.3 `domain`

职责：

- 定义核心业务模型和规则
- 不依赖 GUI、不依赖具体自动化工具

建议核心模型：

- `WeChatSession`
- `Contact`
- `ChatTarget`
- `MessageContent`
- `Attachment`
- `AutomationTask`
- `TaskStep`
- `ExecutionRecord`
- `ExecutionResult`

### 5.4 `automation`

职责：

- 负责真正操作微信桌面客户端
- 屏蔽不同自动化实现细节
- 提供统一驱动接口

建议接口设计：

```python
class WeChatDriver(Protocol):
    def is_running(self) -> bool: ...
    def is_logged_in(self) -> bool: ...
    def activate(self) -> None: ...
    def search_chat(self, keyword: str) -> bool: ...
    def open_chat(self, name: str) -> None: ...
    def send_text(self, text: str) -> None: ...
    def send_file(self, file_path: str) -> None: ...
    def capture_state(self) -> dict: ...
```

实现层建议拆分：

- `automation/drivers/accessibility_driver.py`
- `automation/drivers/applescript_driver.py`
- `automation/drivers/image_driver.py`
- `automation/detectors/window_detector.py`
- `automation/detectors/login_detector.py`
- `automation/ocr/*`

说明：

- `accessibility_driver` 负责优先通过 macOS 辅助功能接口读取和操作 UI
- `applescript_driver` 负责应用激活、窗口切换、系统脚本桥接
- `image_driver` 负责兜底，比如拿不到控件信息时用图像定位
- 后续可支持不同微信版本的适配器

### 5.5 `infrastructure`

职责：

- 数据落盘
- 调度
- 配置读取
- 日志记录

建议子模块：

- `infrastructure/db/sqlite.py`
- `infrastructure/repositories/task_repo.py`
- `infrastructure/repositories/log_repo.py`
- `infrastructure/config/settings.py`
- `infrastructure/scheduler/scheduler.py`
- `infrastructure/logging/logger.py`

## 6. 关键设计点

### 6.1 驱动层必须抽象

不要在 GUI 或 UseCase 里直接写鼠标点击、键盘输入逻辑。  
所有对微信的控制都应通过 `WeChatDriver` 接口走。

这样有几个好处：

- 后续更换自动化库成本低
- 可以做模拟驱动用于测试
- 可以按微信版本做多适配实现

### 6.2 任务编排和单步动作分离

建议把“给张三发一句话”定义为 `Action`，把“依次给 20 个联系人发送不同内容”定义为 `Task`。

结构上分成：

- `Action`: 单个原子操作
- `Task`: 由多个 Action 组成
- `TaskOrchestrator`: 负责任务执行、重试、暂停、取消、日志

### 6.3 GUI 不直接阻塞主线程

自动化操作和调度任务要运行在后台线程或工作队列中。

建议：

- GUI 主线程只负责渲染和交互
- 应用层通过 `QThread`、`QRunnable` 或任务总线派发工作
- 日志和状态通过事件回传给界面

### 6.4 日志与截图证据要标准化

自动化很容易失败，必须可追踪。

每次任务执行建议记录：

- 任务 ID
- 时间
- 操作目标
- 执行动作
- 成功 / 失败
- 错误信息
- 当前截图路径

这样方便排查“微信界面改版导致找不到控件”的问题。

### 6.5 配置与运行态分离

建议区分：

- 静态配置：程序设置、默认延迟、截图目录、重试次数
- 运行态数据：当前任务、执行日志、会话状态

避免把运行中状态写进配置文件导致混乱。

## 7. 推荐目录结构

```text
wx-gui/
├── ARCHITECTURE.md
├── README.md
├── requirements.txt
├── app/
│   ├── main.py
│   ├── gui/
│   │   ├── main_window.py
│   │   ├── pages/
│   │   ├── widgets/
│   │   └── viewmodels/
│   ├── application/
│   │   ├── usecases/
│   │   ├── services/
│   │   ├── dto/
│   │   └── events/
│   ├── domain/
│   │   ├── models/
│   │   ├── value_objects/
│   │   ├── repositories/
│   │   └── services/
│   ├── automation/
│   │   ├── drivers/
│   │   ├── detectors/
│   │   ├── ocr/
│   │   └── exceptions/
│   ├── infrastructure/
│   │   ├── config/
│   │   ├── db/
│   │   ├── repositories/
│   │   ├── scheduler/
│   │   └── logging/
│   └── shared/
│       ├── constants/
│       ├── utils/
│       └── exceptions/
├── data/
│   ├── app.db
│   ├── logs/
│   └── screenshots/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── scripts/
```

## 8. 核心流程设计

### 8.1 连接微信

```text
GUI 点击“连接微信”
-> ConnectWeChatUseCase
-> WeChatDriver.is_running()
-> WeChatDriver.is_logged_in()
-> 返回连接状态
-> GUI 更新状态面板
```

### 8.2 发送单条消息

```text
GUI 输入联系人和消息内容
-> SendMessageUseCase
-> TaskOrchestrator 创建执行记录
-> WeChatDriver.activate()
-> WeChatDriver.open_chat(target)
-> WeChatDriver.send_text(text)
-> 保存日志和结果
-> GUI 展示成功或失败
```

### 8.3 批量任务执行

```text
GUI 导入联系人和消息模板
-> RunBatchTaskUseCase
-> TaskOrchestrator 切分为多个 Action
-> Scheduler/Worker 逐个执行
-> 每一步记录日志、截图、结果
-> GUI 实时展示进度
```

## 9. 数据模型建议

### `AutomationTask`

- `id`
- `name`
- `type`
- `status`
- `created_at`
- `updated_at`
- `payload_json`

### `ExecutionRecord`

- `id`
- `task_id`
- `step_name`
- `target`
- `status`
- `message`
- `screenshot_path`
- `started_at`
- `finished_at`

### `AppSettings`

- `wechat_window_title`
- `default_action_delay_ms`
- `max_retry_count`
- `screenshot_on_error`
- `log_retention_days`

## 10. 异常处理设计

定义统一异常层级：

- `AppError`
- `DriverError`
- `WindowNotFoundError`
- `LoginRequiredError`
- `TargetNotFoundError`
- `MessageSendFailedError`
- `TaskCancelledError`

原则：

- 驱动层抛技术异常
- 应用层做异常翻译
- GUI 层只展示用户可理解的信息

## 11. 测试策略

### 单元测试

覆盖：

- UseCase 参数校验
- TaskOrchestrator 编排逻辑
- 日志与结果存储
- 配置解析

### 集成测试

覆盖：

- SQLite 持久化
- 调度执行
- 驱动适配器接口契约

### 自动化测试建议

真实微信自动化很难做稳定的 CI，因此建议：

- 大多数逻辑通过 Mock Driver 测
- 少量手工验证真实微信环境
- 建立“演示环境”回归脚本

## 12. 安全与风险

这个项目有几个现实风险需要提前规避：

- 微信客户端版本变化会导致控件定位失效
- 高强度自动化操作可能触发风控
- 不同操作系统下自动化方案差异较大
- 图像识别方案对分辨率和缩放敏感
- macOS 需要用户授予“辅助功能”和可能的“屏幕录制”权限

建议策略：

- 第一版只支持一个明确平台，优先 macOS
- 所有动作加入节流和随机延迟能力
- 错误时自动截图
- 不实现高风险社交增长类功能
- 首次启动增加权限自检，引导用户开启辅助功能权限

## 13. MVP 开发顺序

建议按下面顺序推进：

1. 项目骨架和依赖管理
2. 主窗口 + 日志面板 + 配置管理
3. `WeChatDriver` 抽象接口
4. 微信窗口检测和激活
5. 搜索联系人 + 打开聊天窗口
6. 发送文本消息
7. 执行日志和错误截图
8. 批量任务
9. 定时调度
10. 文件发送和更多动作扩展

## 14. 后续可扩展能力

未来可以在现有架构上追加：

- 消息模板系统
- 定时发送
- 条件任务流
- OCR 读取聊天界面状态
- 自动回复规则
- 插件机制
- 远程任务下发

## 15. 我对这个项目的最终建议

如果你的目标是“做一个稳定、可维护、后续能逐步扩功能的 GUI 控制微信工具”，最合适的路径不是一开始猛堆自动化代码，而是：

- 先把 **驱动接口抽象** 定死
- 再把 **GUI 与任务编排** 分开
- 用 **日志 + 截图 + 任务记录** 保证可维护性
- 第一版只聚焦 1 到 2 个核心能力跑通

这样后面无论你想继续做“批量消息”、“定时任务”还是“插件式动作扩展”，都不用推翻重来。
