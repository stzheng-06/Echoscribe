1. 项目概述
EchoScribe 是一个桌面端音频录制、转录与翻译工具。

MVP 阶段主要面向 Windows 用户，支持录制电脑系统声音和麦克风声音，并将两路音频混合成一个音频文件，然后调用 aihubmix 上的 Whisper API 进行语音转录。转录完成后，用户可以选择将转录文本翻译成中文。

项目后续计划兼容 Linux 和 macOS，但 MVP 优先保证 Windows 可用。

2. MVP 目标
2.1 MVP 核心目标
实现一个最小可用桌面应用，支持：

输入并保存 aihubmix API Key
录制 Windows 系统声音
录制麦克风声音
将系统声音和麦克风声音混音为一个音频文件
上传音频到 aihubmix Whisper API 进行转录
显示转录结果
将转录文本翻译为中文
显示翻译结果
导出转录文本和翻译文本
3. 目标用户
3.1 MVP 阶段用户
需要录制短音频并转录的人
需要记录会议、网课、播客、视频片段的人
希望同时录制电脑声音和自己麦克风声音的人
有基本电脑操作能力的 Windows 用户
3.2 典型使用场景
场景一：会议记录
用户参加线上会议，希望录下对方声音和自己的发言，会议结束后自动生成文字记录。

场景二：网课学习
用户播放一段 3 分钟以内的英文课程，同时可以用麦克风补充自己的注释，结束后生成转录文本和中文翻译。

场景三：短视频内容整理
用户播放一段短视频，录制视频声音，转录成文字并翻译成中文。

4. 产品范围
4.1 MVP 包含功能
功能模块	是否包含
API Key 设置	包含
系统声音录制	包含
麦克风录制	包含
系统声音 + 麦克风混音	包含
Whisper 转录	包含
中文翻译	包含
文本显示	包含
文本导出	包含
本地配置保存	包含
基础错误提示	包含
4.2 MVP 不包含功能
功能	MVP 是否包含
实时转录	不包含
实时字幕悬浮窗	不包含
长音频切片	不包含
说话人分离	不包含
字幕时间轴编辑	不包含
SRT/VTT 字幕导出	不包含
云端同步	不包含
用户账号系统	不包含
自动更新	不包含
macOS/Linux 完整支持	不包含
复杂音频降噪	不包含
5. 技术选型
5.1 桌面框架
使用：

Text
Python + PySide6
选择原因：

用户已有 Python 基础
适合快速开发 MVP
方便使用 AI 辅助编码
可跨平台扩展
UI 开发相对简单
5.2 音频录制
MVP 使用：

Text
PyAudioWPatch + sounddevice + numpy + scipy + soundfile
系统声音（WASAPI loopback）：

Python
PyAudioWPatch WASAPI loopback
麦克风声音：

Python
sounddevice InputStream
混音：

Python
scipy.signal.resample + numpy 混合
5.3 API 调用
使用：

Text
requests
转录接口：

Text
POST https://aihubmix.com/v1/audio/transcriptions
翻译接口：

Text
POST https://aihubmix.com/v1/chat/completions
5.4 配置存储
MVP 使用本地 JSON 文件：

Text
config.json
保存内容：

aihubmix API Key
麦克风设备名
最近一次输出目录
5.5 打包方式
MVP 开发阶段：

Text
python main.py
后续打包：

Text
PyInstaller
6. 产品核心流程
6.1 用户主流程
Text
打开 EchoScribe
    ↓
输入 aihubmix API Key
    ↓
输入或选择麦克风设备名
    ↓
点击“保存设置”
    ↓
点击“开始录制”
    ↓
系统开始同时录制系统声音和麦克风声音
    ↓
用户点击“停止录制并转录”
    ↓
程序停止录音
    ↓
程序混合 system.wav 和 mic.wav
    ↓
生成 mixed.wav
    ↓
上传 mixed.wav 到 aihubmix Whisper API
    ↓
显示转录文本
    ↓
调用翻译接口
    ↓
显示中文翻译
    ↓
用户可导出文本
7. 页面设计
7.1 主窗口
MVP 只做一个主窗口。

窗口标题：

Text
EchoScribe
窗口主要区域：

Text
--------------------------------------------------
EchoScribe
API Key:
[________________________________________]
麦克风设备名:
[________________________________________]
[保存设置] [列出音频设备]
录制控制:
[开始录制] [停止录制并转录]
状态:
当前状态：等待操作
转录结果:
[多行文本框]
翻译结果:
[多行文本框]
[导出 TXT]
--------------------------------------------------
8. 功能需求
8.1 设置功能
功能描述
用户可以输入 aihubmix API Key 和麦克风设备名，并保存到本地配置文件。

输入
API Key
麦克风设备名
输出
config.json
验收标准
用户点击“保存设置”后，配置写入 config.json
下次打开应用时自动加载配置
API Key 输入框默认以密码形式显示
如果 API Key 为空，转录和翻译前应提示用户填写
8.2 列出音频设备
功能描述
用户点击“列出音频设备”后，程序调用 FFmpeg 列出 Windows 可用音频设备，方便用户复制麦克风设备名。

技术实现
执行：

Bash
ffmpeg -list_devices true -f dshow -i dummy
输出
在弹窗或文本区域中显示 FFmpeg 返回的设备列表。

验收标准
点击按钮后能显示设备列表
如果 FFmpeg 不存在，应提示用户安装 FFmpeg 或配置路径
8.3 开始录制
功能描述
用户点击“开始录制”后，程序同时启动两个 FFmpeg 进程：

录制系统声音
录制麦克风声音
输入
麦克风设备名
当前时间戳
输出
生成临时文件：

Text
recordings/{timestamp}_system.wav
recordings/{timestamp}_mic.wav
技术命令
系统声音：

Bash
ffmpeg -y -f wasapi -loopback 1 -i default recordings/{timestamp}_system.wav
麦克风声音：

Bash
ffmpeg -y -f dshow -i audio="{mic_device_name}" recordings/{timestamp}_mic.wav
验收标准
点击开始后状态变为“正在录制”
开始录制按钮禁用
停止录制按钮启用
recordings 目录下产生 system.wav 和 mic.wav
如果启动 FFmpeg 失败，显示错误提示
单次录制建议不超过 3 分钟
8.4 停止录制并混音
功能描述
用户点击“停止录制并转录”后，程序停止两个 FFmpeg 进程，并将系统声音和麦克风声音混合为一个音频文件。

输入
Text
recordings/{timestamp}_system.wav
recordings/{timestamp}_mic.wav
输出
Text
recordings/{timestamp}_mixed.wav
技术命令
Bash
ffmpeg -y \
-i recordings/{timestamp}_system.wav \
-i recordings/{timestamp}_mic.wav \
-filter_complex "amix=inputs=2:duration=longest:normalize=0" \
recordings/{timestamp}_mixed.wav
验收标准
点击停止后录制进程正常结束
成功生成 mixed.wav
如果某一路音频不存在，应提示用户
如果混音失败，应显示错误信息
混音完成后进入转录流程
8.5 Whisper 转录
功能描述
上传混音后的音频文件到 aihubmix Whisper API，获取转录文本。

API
Text
POST https://aihubmix.com/v1/audio/transcriptions
请求参数
Text
file: mixed.wav
model: whisper-1
response_format: json
可选参数
Text
language: auto 或用户指定
响应示例
Json
{
  "text": "This is a transcription result."
}
验收标准
成功上传 mixed.wav
成功解析返回 JSON
将 text 字段显示到转录结果框
网络错误时显示错误提示
API Key 错误时显示鉴权失败提示
请求超时时显示超时提示
8.6 中文翻译
功能描述
将转录文本发送到 aihubmix 的 chat/completions 接口，翻译成中文。

API
Text
POST https://aihubmix.com/v1/chat/completions
请求参数示例
Json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "你是专业翻译。请把用户提供的转录文本翻译成自然流畅的中文，保留专有名词。"
    },
    {
      "role": "user",
      "content": "This is a transcription result."
    }
  ]
}
验收标准
转录成功后自动调用翻译接口
翻译结果显示到翻译结果框
如果翻译失败，不影响转录结果展示
翻译失败时显示错误提示
8.7 导出 TXT
功能描述
用户可以将转录文本和翻译文本导出为 TXT 文件。

导出内容格式
Text
EchoScribe Export
=================
Created At:
2025-01-01 12:00:00
Audio File:
recordings/20250101_120000_mixed.wav
Transcription:
转录文本内容
Translation:
翻译文本内容
验收标准
点击“导出 TXT”后弹出文件保存框
用户选择路径后生成 TXT 文件
文件内容包含转录文本和翻译文本
如果没有转录结果，应提示用户暂无可导出内容
9. 非功能需求
9.1 性能需求
单次音频长度目标为 3 分钟以内
停止录制后 5 秒内应开始上传转录
UI 在录制、混音、上传、翻译过程中不能卡死
所有耗时操作必须放入后台线程
9.2 兼容性需求
MVP：

Text
Windows 10 / Windows 11
后续扩展：

Text
macOS
Linux
9.3 稳定性需求
录制过程中不能重复点击开始录制
停止录制时应安全关闭 FFmpeg 进程
异常退出时尽量清理残留进程
网络错误不能导致程序崩溃
9.4 安全性需求
API Key 只保存在本地
MVP 阶段不上传任何配置文件
不记录用户 API Key 到日志
错误信息中不得打印完整 API Key
10. 项目结构
建议项目结构：

Text
echoscribe/
  main.py
  requirements.txt
  README.md
  PRD.md
  config.json
  app/
    __init__.py
    main_window.py
    recorder.py
    transcriber.py
    translator.py
    settings.py
    workers.py
    audio_tools.py
  recordings/
10.1 文件职责
main.py
应用入口。

职责：

创建 QApplication
初始化 MainWindow
启动事件循环
app/main_window.py
主窗口 UI 和用户交互逻辑。

职责：

渲染输入框、按钮、文本框
绑定按钮事件
调用 recorder、transcriber、translator
更新状态栏
app/recorder.py
录音相关逻辑。

职责：

启动 PyAudioWPatch 录制系统音频（WASAPI loopback）
启动 sounddevice 录制麦克风
停止录制并保存 WAV 文件
管理 system.wav、mic.wav、mixed.wav 路径
app/audio_tools.py
音频处理工具。

职责：

混音
检查 FFmpeg 是否存在
列出音频设备
app/transcriber.py
Whisper 转录逻辑。

职责：

上传音频文件到 aihubmix
解析转录结果
抛出可读错误
app/translator.py
翻译逻辑。

职责：

调用 chat/completions
返回中文翻译文本
app/settings.py
配置读写。

职责：

读取 config.json
保存 config.json
提供默认配置
app/workers.py
后台线程任务。

职责：

录音停止、混音、转录、翻译等耗时任务封装为 QThread Worker
通过 signal 通知 UI 更新
11. 配置文件格式
文件：

Text
config.json
示例：

Json
{
  "api_key": "",
  "mic_device_name": "",
  "output_dir": "recordings",
  "translation_model": "gpt-4o-mini",
  "whisper_model": "whisper-1"
}
字段说明：

字段	说明
api_key	aihubmix API Key
mic_device_name	FFmpeg dshow 麦克风设备名
output_dir	录音文件输出目录
translation_model	翻译使用的聊天模型
whisper_model	Whisper 转录模型
12. 关键类设计
12.1 Recorder
Python
class WindowsFfmpegRecorder:
    def __init__(self, output_dir: str, mic_device_name: str):
        pass
    def start(self) -> None:
        pass
    def stop(self) -> str:
        pass
    def is_recording(self) -> bool:
        pass
12.2 Transcriber
Python
class Transcriber:
    def __init__(self, api_key: str, model: str = "whisper-1"):
        pass
    def transcribe(self, audio_path: str) -> str:
        pass
12.3 Translator
Python
class Translator:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        pass
    def translate_to_chinese(self, text: str) -> str:
        pass
12.4 SettingsManager
Python
class SettingsManager:
    def __init__(self, path: str = "config.json"):
        pass
    def load(self) -> dict:
        pass
    def save(self, settings: dict) -> None:
        pass
13. 状态设计
应用状态包括：

Text
idle
recording
stopping
mixing
transcribing
translating
done
error
状态展示示例：

状态	UI 文案
idle	等待操作
recording	正在录制
stopping	正在停止录制
mixing	正在混音
transcribing	正在转录
translating	正在翻译
done	完成
error	发生错误
14. 错误处理
14.1 FFmpeg 不存在
提示：

Text
未检测到 FFmpeg。请先安装 FFmpeg，并将其添加到系统 PATH。
14.2 麦克风设备名为空
提示：

Text
请先填写麦克风设备名。你可以点击“列出音频设备”查看可用设备。
14.3 系统声音录制失败
提示：

Text
系统声音录制失败。请确认 FFmpeg 支持 WASAPI，或检查默认播放设备。
14.4 麦克风录制失败
提示：

Text
麦克风录制失败。请确认设备名称正确，并检查麦克风权限。
14.5 API Key 为空
提示：

Text
请先填写 aihubmix API Key。
14.6 转录失败
提示：

Text
转录失败，请检查网络、API Key 或音频文件格式。
14.7 翻译失败
提示：

Text
翻译失败，但转录结果已保留。
15. MVP 验收标准
MVP 版本完成需要满足以下条件：

15.1 基础运行
可以通过 python main.py 启动应用
主窗口正常显示
无启动报错
15.2 配置保存
可以填写 API Key
可以填写麦克风设备名
点击保存后写入 config.json
重启后能自动加载配置
15.3 设备列表
点击“列出音频设备”可以显示 FFmpeg 设备列表
FFmpeg 不存在时有明确提示
15.4 录音
点击“开始录制”后能够启动录音
状态显示为“正在录制”
能同时生成系统声音和麦克风声音文件
点击“停止录制并转录”后能结束录音
15.5 混音
停止后能生成 mixed.wav
mixed.wav 可以正常播放
mixed.wav 包含系统声音和麦克风声音
15.6 转录
mixed.wav 能上传到 aihubmix Whisper API
能显示转录文本
API 调用失败时显示错误，不崩溃
15.7 翻译
转录完成后自动翻译成中文
能显示翻译文本
翻译失败时保留转录结果
15.8 导出
可以导出 TXT
TXT 包含转录文本和翻译文本
16. 开发里程碑
Milestone 1：项目骨架和 UI
目标：

创建项目结构
实现 PySide6 主窗口
实现配置保存和加载
完成标准：

应用可以启动
可以保存 API Key 和麦克风设备名
Milestone 2：API 转录功能
目标：

先支持选择本地音频文件上传转录
显示 Whisper 返回文本
完成标准：

不依赖录音，先跑通 aihubmix Whisper API
Milestone 3：翻译功能
目标：

将转录结果翻译成中文
显示翻译结果
完成标准：

能通过 chat/completions 得到中文翻译
Milestone 4：FFmpeg 录音功能
目标：

实现 Windows 系统声音录制
实现 Windows 麦克风录制
实现开始和停止录音
完成标准：

录音文件可正常生成和播放
Milestone 5：混音和完整流程
目标：

停止录音后自动混音
自动上传转录
自动翻译
完成标准：

用户从开始录音到得到转录/翻译结果可以完整跑通
Milestone 6：导出和错误优化
目标：

实现 TXT 导出
优化错误提示
避免 UI 卡死
完成标准：

MVP 可日常使用
17. 后续版本规划
V0.2
增加选择本地音频文件转录
增加选择输出目录
增加录音时长显示
增加音频压缩为 mp3/m4a
增加手动选择是否翻译
V0.3
增加 PyAudioWPatch Windows 录音后端
提升 Windows 系统声音录制稳定性
增加麦克风设备下拉选择
增加音量检测和波形显示
V0.4
增加 SRT/VTT 导出
增加语言选择
增加 prompt 提示词
增加历史记录
V1.0
Windows 打包发布
完整安装包
FFmpeg 内置
UI 美化
自动更新
后续跨平台
macOS
初期支持 BlackHole + FFmpeg
后续考虑 ScreenCaptureKit helper
Linux
支持 PulseAudio / PipeWire monitor source
支持 FFmpeg pulse 输入
18. Vibe Coding 提示词
可以将以下提示词交给 AI 编码工具：

Text
请根据 PRD.md 实现 EchoScribe 的 MVP。
技术栈：
- Python 3.10+
- PySide6
- requests
- PyAudioWPatch + sounddevice + numpy + scipy + soundfile
要求：
1. 按以下项目结构创建代码：
   echoscribe/
     main.py
     requirements.txt
     app/
       __init__.py
       main_window.py
       recorder.py
       transcriber.py
       translator.py
       settings.py
       workers.py
       audio_tools.py
     recordings/
2. 主窗口包含：
   - API Key 输入框
   - 麦克风设备名输入框
   - 系统声音设备输入框
   - 保存设置按钮
   - 列出麦克风设备按钮
   - 列出系统音频设备按钮
   - 开始录制按钮
   - 停止录制并转录按钮
   - 转录结果 QTextEdit
   - 翻译结果 QTextEdit
   - 导出 TXT 按钮
   - 状态栏（显示录制时间）
3. 实现 config.json 读写。
4. 实现 AudioRecorder（使用 PyAudioWPatch + sounddevice）：
   - start() 同时启动两个录音线程：
     a. PyAudioWPatch WASAPI loopback 录制系统音频
     b. sounddevice 录制麦克风
   - stop() 停止录音并保存 WAV 文件
5. 实现 Transcriber：
   - POST https://aihubmix.com/v1/audio/transcriptions
   - Authorization: Bearer API_KEY
   - multipart/form-data
   - model=whisper-1
   - response_format=json
   - 返回 text 字段
6. 实现 Translator：
   - POST https://aihubmix.com/v1/chat/completions
   - 使用 gpt-4o-mini
   - 将转录文本翻译成中文
7. 所有耗时任务使用 QThread，不能阻塞 UI。
8. 实现错误提示：
   - API Key 为空
   - 麦克风设备名为空
   - 录音失败
   - 混音失败
   - 转录失败
   - 翻译失败
9. 实现 TXT 导出功能。
请先实现可运行 MVP，代码要清晰、模块化，并在 README 中说明运行方式。
10. MVP 成功定义
当用户可以完成以下流程时，MVP 视为成功：

Text
打开 EchoScribe
输入 API Key 和麦克风设备名
点击开始录制
播放电脑声音并对麦克风说话
点击停止录制并转录
等待处理
看到转录文本
看到中文翻译
点击导出 TXT
成功保存结果
20. 备注
MVP 中 Windows 系统声音录制依赖 FFmpeg WASAPI 能力。若用户环境中 FFmpeg 不支持该功能，需在后续版本加入 PyAudioWPatch 或虚拟声卡方案作为备用录音后端。