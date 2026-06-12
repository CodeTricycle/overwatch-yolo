"""将 YOLO .pt 模型导出为 ONNX。

用法:
    python scripts/pt2onnx.py [模型路径] [--imgsz 640] [--opset 12] [--half] [--dynamic]

默认导出 model/ow.pt -> model/ow.onnx。
ONNX 可用于 onnxruntime、TensorRT 或其他支持 ONNX 的推理后端。
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description="pt -> onnx 导出")
    ap.add_argument(
        "model",
        nargs="?",
        default=str(ROOT / "model" / "ow.pt"),
        help="输入 .pt 模型路径",
    )
    ap.add_argument("--imgsz", type=int, default=320, help="导出输入尺寸")
    ap.add_argument("--opset", type=int, default=12, help="ONNX opset 版本")
    ap.add_argument("--half", action="store_true", help="导出 FP16 半精度")
    ap.add_argument("--dynamic", action="store_true", help="启用动态输入尺寸")
    ap.add_argument("--simplify", action="store_true", help="简化 ONNX 图")
    args = ap.parse_args()

    out = YOLO(args.model).export(
        format="onnx",
        imgsz=args.imgsz,
        opset=args.opset,
        half=args.half,
        dynamic=args.dynamic,
        simplify=args.simplify,
    )
    print(f"ONNX 导出完成 -> {out}")


if __name__ == "__main__":
    main()
