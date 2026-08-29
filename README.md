# PopTrans 划词翻译

Windows 全局划词翻译工具：在任意应用中选中文字，鼠标旁弹出「译」按钮，点击即在卡片中流式显示大模型翻译。自动识别语言方向（默认中文↔英文互译），支持接入任意 OpenAI 兼容接口（智谱 GLM、DeepSeek、Kimi、通义、OpenAI 等）。

```
选中文字 ──> 光标旁弹出「译」按钮 ──> 点击 ──> 翻译卡片流式输出
    │                                        │
    └── 或按 Ctrl+Alt+Y 直接翻译 ─────────────┘
```

![翻译卡片](docs/screenshot.png)

## 下载安装

- **打包版**：从 [Releases](../../releases) 下载 `PopTrans.exe`（单文件、免安装，Windows 10+）
- **源码运行**：见下方「快速开始」

## 功能

- **划词取词**：拖选或双击文字后，光标旁弹出圆形迷你「译」按钮（不抢焦点、不打断输入）
- **流式翻译**：大模型流式输出，边生成边显示
- **自动语言检测**：中/日/韩/俄/阿/英文按 Unicode 特征本地识别，中英自动互译，也可固定目标语言
- **全局热键**：默认 `Ctrl+Alt+Y`，按下直接翻译当前选中文本（跳过按钮）
- **OCR 取词**：默认 `Ctrl+Alt+O`，框选屏幕任意区域，识别其中的文字并翻译——图片里、PDF 里不可复制的文字都能翻
- **公式还原**：复制自 PDF 的公式丢失上下标时，由大模型恢复为 LaTeX，并在卡片中渲染成与论文一致的公式形式
- **卡片可拖动**：按住翻译卡片顶部即可拖到顺手的位置
- **开机自启**：设置里勾选即可（写入当前用户启动项，无需管理员权限）
- **剪贴板保护**：取词用的模拟复制会自动恢复你原来的剪贴板内容
- **托盘常驻**：随时开关划词、触发 OCR、修改设置、退出
- **检查更新**：设置里填写更新清单 URL 后，启动时后台自动检查、托盘可手动检查；发现新版本弹窗提供下载页（清单为 JSON：`{"version", "url", "notes"}`，可托管在 GitHub raw / 对象存储等任意静态服务）
- **应用黑名单**：终端（cmd/PowerShell 等）默认不触发，可自行添加

## 快速开始（从源码运行）

需要 Python 3.10+（Windows）。

```bat
pip install -r requirements.txt
python main.py
```

首次启动会自动弹出设置界面：

1. 选择服务商预设（或直接填 API 地址 / 模型）
2. 粘贴 API 密钥
3. 点击「测试连接」确认可用
4. 保存

之后在任意应用里选中文字即可使用。

## 推荐免费/低价配置示例

| 服务商 | API 地址 | 模型 | 密钥获取 |
|---|---|---|---|
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash`（免费） | [bigmodel.cn](https://open.bigmodel.cn) |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | [platform.deepseek.com](https://platform.deepseek.com) |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | [platform.openai.com](https://platform.openai.com) |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` | [platform.moonshot.cn](https://platform.moonshot.cn) |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` | [阿里云百炼](https://bailian.console.aliyun.com) |

任何 OpenAI 兼容接口（包括本地 Ollama：`http://127.0.0.1:11434/v1`）填入地址 + 模型名即可使用。

## 使用方式

- **划词翻译**：选中文字 → 点击弹出的圆形「译」按钮 → 卡片流式显示译文
- **热键直翻**：选中文字 → `Ctrl+Alt+Y` → 直接弹出翻译卡片（组合键被其他软件占用时，请在设置里换一个）
- **OCR 取词**：`Ctrl+Alt+O`（或托盘菜单「OCR 取词」）→ 屏幕变暗 → 框选文字区域 → 自动识别并翻译；`Esc` 取消
- **拖动卡片**：按住卡片顶部（语言徽章一栏）拖到任意位置
- **缩放卡片**：拖右下角的缩放手柄调整大小；手动缩放后高度不再自动调整，关闭卡片恢复自动
- 翻译卡片内：**复制译文** / **重试** / 关闭（✕ 或 Esc）；多次翻译可同时存在多张卡片，各自拖动/关闭，关闭后的卡片自动复用（最多同时 6 张）

## 设置项

| 分类 | 配置 | 说明 |
|---|---|---|
| API | 服务商预设 / 地址 / 密钥 / 模型 / 测试连接 | 兼容所有 OpenAI 格式接口 |
| 翻译方向 | 自动中英互译 / 固定目标语言 | 自动模式：中文→英文，其他→中文 |
| 划词 | 启用开关、热键开关与组合、应用黑名单 | 黑名单每行一个进程名，如 `cmd.exe` |
| OCR 取词 | 启用开关、热键组合 | 默认 RapidOCR（PaddleOCR 模型，离线、中英文准确）；未安装时自动回退 Windows 自带 OCR（需系统已安装对应语言“文本识别”功能） |
| 卡片 | 主题（浅色/深色/米色/护眼绿/高对比）、译文字号 | 保存后对新旧卡片同时生效，公式颜色随主题自动匹配 |
| 其他 | 开机自启、自动复制译文到剪贴板 | 开机自启写入当前用户启动项 |

配置文件位于 `%APPDATA%\PopTrans\config.json`。

> OCR 说明：默认使用 RapidOCR（PaddleOCR 模型 + ONNX Runtime，离线运行，中英文/小字识别准确），启动时后台预热模型，典型区域识别约 1-2 秒；若未安装 rapidocr-onnxruntime 则自动回退 Windows 自带 OCR。识别结果会交给大模型翻译，轻微识别误差通常不影响译文可读性。

## 开发

```bat
:: 启动（调试日志）
set POPTRANS_DEBUG=1 && python main.py

:: 本地 mock 大模型（无需真实 key 做端到端调试）
python tools/mock_llm.py          # http://127.0.0.1:8765/v1
python tools/e2e_click.py word    # 注入双击选词（开发辅助）

:: 重新生成图标
python tools/gen_icon.py

:: 打包单文件 exe
build.bat                         # 产物在 dist/PopTrans.exe

:: 发布新版本
::   1. 修改 app/config.py 的 APP_VERSION
::   2. build.bat 打包，把 dist/PopTrans.exe 与 version.json 上传到静态托管
::      version.json 示例：{"version": "1.1.0", "url": "https://.../PopTrans.exe", "notes": "更新说明"}
::   3. 配置了更新地址的用户启动时自动收到弹窗提示
```

## 项目结构

```
main.py                  # 入口：装配、单实例（命名互斥体）、事件接线
app/
  config.py              # 配置（JSON 持久化 + 服务商预设）
  detector.py            # 语言检测（Unicode 启发式）+ 方向规则
  translator.py          # OpenAI 兼容流式客户端（QThread + 信号）
  listener.py            # 全局鼠标监听 + 模拟 Ctrl+C 取词
  hotkey.py              # Win32 RegisterHotKey 全局热键
  ocr.py                 # OCR：Qt 截图 + RapidOCR（回退 Windows.Media.Ocr，后台线程）
  autostart.py           # 开机自启（HKCU Run 注册表项）
  resources.py           # 图标资源加载
  ui/
    mini_button.py       # 划词迷你按钮（圆形、不抢焦点）
    card.py              # 翻译卡片（圆角、流式渲染、可拖动）
    ocr_selector.py      # OCR 框选遮罩（全屏蒙层 + 橡皮筋选区）
    settings_dialog.py   # 设置界面
    tray.py              # 托盘图标与菜单
tools/
  mock_llm.py            # 本地 mock LLM（SSE 流式）
  e2e_click.py           # 端到端测试辅助（注入鼠标/键盘事件）
  ui_selftest.py         # UI 组件离线渲染与交互自测
  gen_icon.py            # 图标生成脚本
```

## 实现说明 / 已知边界

- **取词原理**：模拟 `Ctrl+C` 读取剪贴板，约 0.6s 内自动恢复原剪贴板；这是兼容性最好的方案，几乎所有应用都支持。代价是取词瞬间会短暂切换剪贴板内容。
- **误触保护**：1.5s 防抖；进程黑名单（终端默认拉黑，因为 `Ctrl+C` 有特殊含义）；仅拖选（位移 >10px）或双击才触发。
- **弹窗不抢焦点**：迷你按钮用 `WA_ShowWithoutActivating` + `Tool` 窗口实现；圆角通过 `WA_TranslucentBackground` + 样式表实现（顶层窗口不能用 `QGraphicsDropShadowEffect`，会原生崩溃）。
- **热键**：用 Win32 `RegisterHotKey` 注册（不受中文输入法影响；pynput 的字符匹配方案在 IME 下会失效）。组合键被占用时该热键静默失效，换个组合即可。
- **OCR 线程**：WinRT 异步调用必须在普通后台线程执行——Qt 主线程的 STA COM 会让 `BitmapDecoder.create_async` 死锁，故截图在主线程完成后交给工作线程识别（带 20s 超时）。
- **多显示器**：OCR 框选遮罩覆盖所有屏幕；截图统一用主屏对象按虚拟桌面全局坐标抓取——Windows 下主屏对象走虚拟桌面 DC，副屏区域同样有效（若改用副屏对象传全局坐标会偏移加倍、抓出纯黑图）。
- **翻译上下文**：单次划词即单次请求，长文本上限 5000 字符。

## License

MIT
