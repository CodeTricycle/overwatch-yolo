# VisionAim

基于 YOLOv11 的实时目标检测与辅助瞄准系统，适用于 Overwatch 等第一人称射击游戏。采用多进程架构，通过共享内存进行高速进程间通信，支持 CUDA GPU 加速推理和卡尔曼滤波预测。

## 功能特性

- **实时目标检测** — 基于 Ultralytics YOLOv11，支持 `.pt` / `.onnx` / `.engine` 模型格式
- **GPU 加速推理** — 支持 NVIDIA CUDA 与 AMD ROCm，自动使用 GPU (FP16) 进行推理，低延迟高帧率
- **辅助瞄准** — 可配置灵敏度、检测半径、偏移补偿，支持按住/切换两种触发模式
- **卡尔曼滤波** — 可选的卡尔曼滤波器平滑目标轨迹，支持滑行预测与自动重初始化
- **屏幕捕获** — 基于 mss DirectX 后端的高帧率屏幕截取
- **视频预览** — 独立窗口实时显示检测结果与 FPS
- **热键绑定** — 支持键盘与鼠标按键自定义绑定
- **配置持久化** — 所有参数保存至 `settings.json`，启动时自动加载

## 系统要求

- **操作系统**: Windows 10/11（依赖 Win32 API）
- **Python**: 3.10+
- **GPU**: NVIDIA CUDA 显卡 或 AMD ROCm 显卡（推理需要 GPU 加速）
- **显示器**: 单显示器，游戏以独占全屏模式运行

## 安装

### NVIDIA GPU (CUDA)

```bash
# 克隆仓库
git clone https://github.com/CodeTricycle/overwatch-yolo.git
cd overwatch-yolo

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### AMD GPU (ROCm)

AMD 显卡用户请参考 [ROCm PyTorch 安装指南](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/install/installrad/windows/install-pytorch.html) 配置环境，安装完成后其余步骤与 NVIDIA 一致。

将训练好的 YOLOv11 模型文件放置到 `model/` 目录下（默认路径 `model/ow.pt`）。

## 使用方法

### 方式一：启动脚本（推荐，自动请求管理员权限）

双击 `start.bat`，脚本会自动以管理员身份运行并启动程序。

### 方式二：手动启动

```bash
# 需要管理员权限
python main.py
```

### 操作流程

1. 启动程序后，在 UI 界面中点击 **"选择模型文件"** 加载 YOLO 模型
2. 调整置信度阈值、灵敏度、检测半径等参数
3. 点击 **"打开视频预览"** 开始屏幕捕获
4. 点击 **"开启 YOLO"** 启用目标检测
5. 按住绑定的激活键（默认鼠标侧键1）即可激活辅助瞄准
6. 点击 **"保存配置"** 将当前参数持久化

## 配置说明

配置文件为 `settings.json`，首次运行自动生成。各参数说明如下：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `verbosity` | string | `"debug"` | 日志级别 (trace/debug/info/success/warning/error/critical) |
| `detection_radius` | int | `150` | 检测半径（像素），目标中心距屏幕中心小于此值时触发瞄准 |
| `threshold` | float | `0.6` | YOLO 置信度阈值 (0.0 ~ 1.0) |
| `h_sensitivity` | float | `2.0` | 水平灵敏度 |
| `v_sensitivity` | float | `1.8` | 垂直灵敏度 |
| `neural_net_path` | string | `"model/ow.pt"` | 模型文件路径 |
| `activation_button` | string | `"VK_XBUTTON1"` | 激活按键（VK 码名称） |
| `fire_mode` | string | `"按下"` | 触发模式：`"按下"` (按住激活) / `"切换"` (开关切换) |
| `v_compensation` | float | `0.75` | 垂直偏移补偿（用于瞄准头部等位置） |
| `h_compensation` | float | `0.0` | 水平偏移补偿 |
| `yaw_pixel_count` | int | `6550` | 水平 360° 对应像素数（用于灵敏度换算） |
| `pitch_pixel_count` | int | `3220` | 垂直 180° 对应像素数（用于灵敏度换算） |
| `kalman_filter_enabled` | bool | `false` | 是否启用卡尔曼滤波 |
| `kalman_process_noise` | float | `5.0` | 卡尔曼滤波过程噪声 |
| `kalman_measurement_noise` | float | `2.0` | 卡尔曼滤波测量噪声 |
| `kalman_coast_max_frames` | int | `5` | 卡尔曼滤波最大滑行帧数（丢失目标后预测帧数） |
| `kalman_reinit_distance_threshold` | float | `40.0` | 卡尔曼滤波重初始化距离阈值（像素） |

## 项目结构

```
overwatch-yolo/
├── main.py                  # 程序入口，包含 App / CaptureWorker / AimWorker 等核心类
├── settings.json            # 运行时配置文件（自动生成，已 gitignore）
├── requirements.txt         # Python 依赖
├── start.bat                # Windows 启动脚本（自动请求管理员权限）
├── core/
│   ├── __init__.py          # 模块导出
│   ├── constants.py         # IPC 指令常量与事件类型定义
│   ├── hotkey.py            # 热键捕获与 VK 码映射
│   ├── input_handler.py     # 鼠标移动（Win32 API）
│   ├── kalman.py            # 卡尔曼滤波器实现
│   ├── log.py               # 彩色日志系统（基于 colorama）
│   ├── overlay.py           # GDI 屏幕叠加绘制
│   └── settings.py          # 配置文件读写与缓存
├── model/
│   └── ow.pt                # YOLOv11 模型文件（需自行提供）
└── ui/
    └── VisionAimWindow.ui   # PyQt6 界面布局文件
```

## 架构概览

程序采用多进程架构，各进程通过 `multiprocessing.Queue` 和共享内存 (`SharedBox`) 通信：

```
┌──────────┐    Pipe    ┌───────────────┐
│   App    │◄──────────►│ SignalRouter  │
│  (UI进程) │            │  (信号路由进程) │
└────┬─────┘            └───────┬───────┘
     │                          │
     │ Queue                    │ Queue
     ▼                          ▼
┌───────────────┐      ┌───────────────┐
│ CaptureWorker │ SHM  │  AimWorker    │
│ (捕获+推理进程) │◄────►│ (瞄准工作进程)  │
└───────────────┘      └───────────────┘
```

- **App (UI 进程)** — PyQt6 主界面，参数调节，视频预览渲染
- **SignalRouter (信号路由进程)** — 接收 UI 指令，分发到对应工作进程
- **CaptureWorker (捕获进程)** — mss 屏幕截取 + YOLO 推理，结果写入共享内存
- **AimWorker (瞄准进程)** — 读取共享内存检测结果，计算偏移并执行鼠标移动

## 依赖

| 包 | 用途 |
|----|------|
| ultralytics | YOLOv11 推理框架 |
| opencv-python | 图像处理 |
| numpy | 数值计算 |
| PyQt6 | GUI 界面 |
| mss | DirectX 屏幕捕获 |
| pywin32 | Win32 API（鼠标移动、按键状态） |
| pynput | 键盘/鼠标监听（热键捕获） |
| pyautogui | 获取屏幕分辨率 |
| colorama | 终端彩色输出 |

## 许可证

本项目仅供学习与技术研究使用。
