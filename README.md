# EchoScribe

EchoScribe 是一个桌面端音频录制、转录与翻译工具。

## 功能

- 录制 Windows 系统声音（PyAudioWPatch WASAPI loopback）
- 录制麦克风声音（sounddevice）
- 将两路音频混音为一个 WAV 文件（自动重采样）
- 使用 aihubmix Whisper API 进行语音转录
- 使用 aihubmix Chat Completions API 将转录文本翻译成中文
- 导出转录和翻译结果为 TXT 文件
- 录制计时显示

## 环境要求

- Python 3.10+
- Windows 10 / Windows 11
- 不需要 FFmpeg！

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行方式

```bash
python main.py
```

## 配置

首次启动时会自动创建 `config.json`，默认会从 `.env` 读取 API 配置。你也可以在应用界面上修改 API Key、麦克风设备名等设置并保存。

`config.json` 字段说明：

- `api_key` — aihubmix API Key
- `mic_device_name` — 麦克风设备名或索引（留空使用默认）
- `system_device_name` — 系统音频设备（留空使用默认）
- `output_dir` — 录音文件输出目录，默认为 `recordings`
- `translation_model` — 翻译模型
- `whisper_model` — Whisper 转录模型
- `base_url` — aihubmix API 基础地址

## 使用流程

1. 运行 `python main.py` 启动应用。
2. 输入 aihubmix API Key（首次需要）。
3. 可选：选择麦克风设备和系统音频设备。
4. 点击“开始录制”。
5. 播放电脑声音并对着麦克风说话。
6. 点击“停止录制并转录”。
7. 等待转录和翻译完成。
8. 点击“导出 TXT”保存结果。

## 查找麦克风设备

点击“列出麦克风设备”按钮，查看可用的麦克风设备列表。选中后点击“填入设备名”。

## 录制系统声音

系统声音录制使用 WASAPI loopback（PyAudioWPatch），可直接录制浏览器等软件的声音。

## 项目结构

```
.
├── main.py              # 应用入口
├── requirements.txt     # 依赖
├── config.json          # 用户配置（运行时生成）
├── .env                # 默认 API 配置
├── app/
│   ├── __init__.py
│   ├── main_window.py   # 主窗口 UI
│   ├── recorder.py      # 录音逻辑（PyAudioWPatch + sounddevice）
│   ├── audio_tools.py   # 音频工具：混音、重采样
│   ├── transcriber.py   # Whisper 转录
│   ├── translator.py    # 中文翻译
│   ├── settings.py      # 配置读写
│   └── workers.py       # 后台线程任务
└── recordings/          # 录音输出目录
```

## 依赖说明

- PySide6 — GUI 框架
- PyAudioWPatch — Windows 系统音频录制（WASAPI loopback）
- sounddevice — 麦克风录制
- numpy — 音频数据处理
- scipy — 音频重采样
- soundfile — 音频文件读写
- requests — API 调用