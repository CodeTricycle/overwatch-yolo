"""将 YOLO .pt 模型导出为 NCNN，供 vulkan 推理后端使用。

用法:
    python scripts/pt2ncnn.py [模型路径] [--imgsz 640] [--half]

默认导出 model/ow.pt → model/ow_ncnn_model/。
vulkan 加速需要 ncnn 运行时支持 Vulkan: pip install ncnn
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description="pt -> ncnn 导出")
    ap.add_argument("model", nargs="?", default=str(ROOT / "model" / "ow.pt"),
                    help="输入 .pt 模型路径")
    ap.add_argument("--imgsz", type=int, default=320, help="导出输入尺寸")
    ap.add_argument("--half", action="store_true", help="导出 FP16 半精度")
    args = ap.parse_args()

    out = YOLO(args.model).export(
        format="ncnn",
        imgsz=args.imgsz,
        half=args.half,
    )
    print(f"NCNN 导出完成 → {out}")


if __name__ == "__main__":
    main()
