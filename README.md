# VisionAim

VisionAim 是一个基于 YOLO 的 Windows 实时目标检测与瞄准控制实验项目。程序使用 PyQt6 提供桌面界面，捕获屏幕画面后进行目标检测，并把检测结果交给独立的瞄准进程处理。

项目当前面向本地调试和技术研究，不是通用发行包。默认配置、模型路径和推理后端都可以在界面中调整，并保存到 `settings.json`。

## 主要功能

- 实时屏幕捕获：支持 `mss` 和 `dxgi` 两种捕获方式。
- YOLO 推理：支持 `cuda`、`directml` 和 `vulkan` 三种后端。
- 模型格式切换：`cuda` / `directml` 使用 `.pt` 权重，`vulkan` 使用 Ultralytics 导出的 NCNN 模型目录。
- 多配置档：可在界面中新建、重命名、删除和切换配置档。
- 瞄准参数调节：水平/垂直灵敏度、检测半径、水平/垂直补偿。
- 卡尔曼滤波：支持轨迹平滑、丢失目标滑行预测和距离阈值重初始化。
- 拟人化移动：支持最大速度、反应距离、EMA 阻尼和抖动参数。
- 热键绑定：支持键盘键和鼠标键，默认 `VK_XBUTTON1`。
- 视频预览：独立窗口显示捕获画面、检测框和 FPS。

## 环境要求

- Windows 10/11
- Python 3.10 或更新版本
- 管理员权限运行程序
- NVIDIA GPU 使用 `cuda` 后端
- AMD / Intel / 其他 Windows GPU 可尝试 `directml` 或 `vulkan` 后端

`dxgi` 捕获依赖 Windows Desktop Duplication API。部分系统、驱动或全屏模式下可能不可用，此时可以切回 `mss`。

## 安装

```powershell
git clone https://github.com/CodeTricycle/overwatch-yolo.git
cd overwatch-yolo

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt
```

如果 `cuda` 后端无法使用 GPU，先确认当前环境中的 PyTorch 是否安装了匹配显卡驱动的 CUDA 版本。`directml` 后端依赖 `torch-directml`，安装 `requirements.txt` 时会一并安装。

## 模型准备

默认模型路径是：

```text
model/ow.pt
```

也可以在界面中点击“选择模型文件”选择其他 `.pt` 模型。

### ONNX 导出

如果需要 ONNX 模型，可以使用导出脚本：

```powershell
python .\scripts\pt2onnx.py .\model\ow.pt --imgsz 320
```

默认会生成同名 `.onnx` 文件，例如 `model/ow.onnx`。

### CUDA 后端

`cuda` 后端会加载基础模型路径对应的 `.pt` 文件。

示例：

```text
model/ow.pt
```

### DirectML 后端

`directml` 后端同样加载 `.pt` 文件，不需要导出 NCNN。它适合在 Windows 上尝试 AMD / Intel / NVIDIA 的 DirectML GPU 加速：

```text
model/ow.pt
```

### Vulkan 后端

`vulkan` 后端会加载同名的 NCNN 导出目录：

```text
model/ow_ncnn_model
```

如果只有 `.pt` 文件，可以先导出：

```powershell
python .\scripts\pt2ncnn.py .\model\ow.pt --imgsz 320
```

导出后在界面中把推理后端切换为 `vulkan`。切换后程序会重新加载模型。

## 启动

推荐双击：

```text
start.bat
```

脚本会请求管理员权限并启动程序。

也可以在管理员 PowerShell 中手动运行：

```powershell
python .\main.py
```

## 使用流程

1. 启动程序。
2. 选择捕获方式：优先尝试 `mss`，需要更低延迟时可尝试 `dxgi`。
3. 选择推理后端：NVIDIA 通常用 `cuda`，其他 Windows GPU 可尝试 `directml`，也可以尝试 `vulkan`。
4. 点击“选择模型文件”确认模型路径。
5. 点击“打开视频显示”启动画面预览。
6. 点击“开启 YOLO”启动检测。
7. 调整置信度、灵敏度、补偿、滤波和拟人化参数。
8. 点击“保存配置”写入 `settings.json`。

配置档下拉框用于管理多套瞄准参数。新建配置档会复制当前配置档的参数，切换配置档后界面会立即应用对应参数。

## 配置文件

`settings.json` 位于项目根目录。首次运行时会自动生成；旧版扁平配置会在读取时自动迁移成多配置档结构。

当前配置分为两类：

- 全局配置：模型路径、置信度、激活键、触发模式、后端、捕获方式、屏幕像素换算等。
- 配置档参数：灵敏度、检测半径、补偿、卡尔曼滤波和拟人化移动参数。

示例结构：

```json
{
    "verbosity": "debug",
    "inference_backend": "cuda",
    "capture_method": "mss",
    "threshold": 0.6,
    "neural_net_path": "model/ow.pt",
    "activation_button": "VK_XBUTTON1",
    "fire_mode": "按下",
    "yaw_pixel_count": 6550,
    "pitch_pixel_count": 3220,
    "active_profile": "Default",
    "profiles": {
        "Default": {
            "detection_radius": 150,
            "h_sensitivity": 2.0,
            "v_sensitivity": 1.8,
            "h_compensation": 0.0,
            "v_compensation": 0.75,
            "kalman_filter_enabled": false,
            "kalman_process_noise": 5.0,
            "kalman_measurement_noise": 2.0,
            "kalman_coast_max_frames": 5,
            "kalman_reinit_distance_threshold": 40.0,
            "humanize_enabled": false,
            "humanize_max_speed": 12.0,
            "humanize_reaction_dist": 80.0,
            "humanize_alpha": 0.55,
            "humanize_jitter": 0.4
        }
    }
}
```

## 配置项说明

| 配置项 | 作用 |
| --- | --- |
| `inference_backend` | 推理后端，支持 `cuda` / `directml` / `vulkan` |
| `capture_method` | 截图方式，支持 `mss` / `dxgi` |
| `threshold` | YOLO 置信度阈值 |
| `neural_net_path` | 模型路径，通常选择 `.pt` 文件或同名 NCNN 模型目录 |
| `activation_button` | 激活按键名称，例如 `VK_XBUTTON1` |
| `fire_mode` | 触发模式，支持 `按下` / `切换` |
| `yaw_pixel_count` | 游戏内水平 360 度对应的鼠标像素数 |
| `pitch_pixel_count` | 游戏内垂直 180 度对应的鼠标像素数 |
| `active_profile` | 当前生效的配置档名称 |
| `profiles` | 多配置档数据 |
| `detection_radius` | 目标中心距离屏幕中心多少像素内才触发 |
| `h_sensitivity` / `v_sensitivity` | 水平和垂直灵敏度 |
| `h_compensation` / `v_compensation` | 水平和垂直瞄准补偿 |
| `kalman_filter_enabled` | 是否启用卡尔曼滤波 |
| `kalman_process_noise` | 卡尔曼过程噪声 |
| `kalman_measurement_noise` | 卡尔曼测量噪声 |
| `kalman_coast_max_frames` | 目标丢失后继续预测的最大帧数 |
| `kalman_reinit_distance_threshold` | 检测点和预测点距离超过该值时重置滤波器 |
| `humanize_enabled` | 是否启用拟人化移动 |
| `humanize_max_speed` | 单帧最大移动速度 |
| `humanize_reaction_dist` | 速度趋近最大值的距离尺度 |
| `humanize_alpha` | EMA 平滑权重 |
| `humanize_jitter` | 移动抖动强度 |

## 项目结构

```text
overwatch-yolo/
├── main.py                  # 程序入口、UI 绑定、多进程调度、捕获和推理流程
├── settings.json            # 运行时配置，首次运行自动生成
├── requirements.txt         # Python 依赖
├── start.bat                # Windows 管理员启动脚本
├── core/
│   ├── constants.py         # 进程通信命令和事件常量
│   ├── dxgi_capture.py      # DXGI Desktop Duplication 捕获
│   ├── hotkey.py            # 热键捕获和 VK 名称转换
│   ├── humanize.py          # 拟人化移动曲线
│   ├── input_handler.py     # Win32 鼠标移动
│   ├── kalman.py            # 卡尔曼追踪器
│   ├── log.py               # 控制台和界面日志
│   ├── overlay.py           # GDI 绘制工具
│   └── settings.py          # 配置读写、多配置档和旧配置迁移
├── model/
│   ├── ow.pt                # 示例/本地模型文件
│   └── ow_ncnn_model/       # Vulkan 后端使用的 NCNN 模型目录
├── scripts/
│   └── pt2ncnn.py           # .pt 到 NCNN 的导出脚本
└── ui/
    └── VisionAimWindow.ui   # PyQt6 界面布局
```

## 运行架构

程序使用多进程隔离 UI、检测和瞄准逻辑：

```text
App / UI
  ├─ SignalRouter：转发 UI 命令
  ├─ CaptureWorker：屏幕捕获、YOLO 推理、预览帧输出
  └─ AimWorker：读取检测结果、计算偏移、执行鼠标移动
```

检测结果通过共享内存结构传递，控制命令通过 `multiprocessing.Queue` 和 `Pipe` 分发。

## 常见问题

### 切换到 vulkan 后模型加载失败

确认同名 NCNN 模型目录存在。例如基础模型是 `model/ow.pt`，则需要存在：

```text
model/ow_ncnn_model/
```

可以用 `scripts/pt2ncnn.py` 重新导出。

### cuda 后端没有使用 GPU

检查 PyTorch 是否识别 CUDA：

```powershell
python -c "import torch; print(torch.cuda.is_available())"
```

如果输出 `False`，需要安装匹配本机驱动的 CUDA 版 PyTorch。

### directml 后端无法启动

确认已安装 DirectML 依赖：

```powershell
python -c "import torch_directml; print(torch_directml.device())"
```

如果导入失败，重新安装依赖：

```powershell
pip install torch-directml
```

### dxgi 没有画面或报错

先切回 `mss`。`dxgi` 对系统版本、显卡驱动、显示模式和占用状态更敏感。

### 配置文件删掉后能否恢复

可以。删除 `settings.json` 后再次启动会自动生成新的多配置档配置。

## 说明

本项目仅用于本地学习、计算机视觉实验和输入控制研究。使用者需要自行承担运行环境、账号规则和软件兼容性风险。
