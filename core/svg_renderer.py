"""
SVG → XCursor 渲染器
====================

当主题以 KDE 主题 SVG 源格式打包时 (cursors_scalable/<name>/metadata.json +
*.svg), 我们的 xcursor reader 读不到. 本模块自动 build:
  1. 读 metadata.json (hotspot, frame delay, frame filenames)
  2. 用 rsvg-convert / magick / Pillow + cairosvg 渲染 SVG -> PNG (多尺寸)
  3. 打包成 XCursor 二进制格式
  4. 写到临时 cursors 目录, 后续走标准流程

支持多种渲染后端 (按可用性自动选择):
  - rsvg-convert (librsvg) - 最快, 质量最好
  - ImageMagick (magick / convert)
  - Pillow + cairosvg (Python 原生)
"""

import json
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


# XCursor 二进制文件头
# 实际写入逻辑见 _pack_xcursor() 下面的代码


def _pick_renderer() -> str:
    """按可用性选择 SVG 渲染器后端"""
    # 1. cairosvg (Python 原生, 库依赖少, 推荐)
    try:
        import cairosvg  # noqa: F401
        return "cairosvg"
    except ImportError:
        pass
    # 2. rsvg-convert (librsvg)
    try:
        subprocess.run(["rsvg-convert", "-v"], capture_output=True, check=False, timeout=5)
        return "rsvg-convert"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # 3. ImageMagick (magick / convert)
    for cmd in ("magick", "convert", "inkscape"):
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=False, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ""


def _render_svg_to_png(svg_path: Path, size: int, out_path: Path, backend: str) -> bool:
    """
    用指定 backend 渲染 SVG 到 PNG (指定 size).
    返回 True 成功, False 失败.
    """
    if backend == "cairosvg":
        try:
            import cairosvg
            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(out_path),
                output_width=size,
                output_height=size,
            )
            return out_path.exists() and out_path.stat().st_size > 0
        except Exception:
            return False
    elif backend == "rsvg-convert":
        try:
            subprocess.run(
                ["rsvg-convert", "-w", str(size), "-h", str(size), "-a", str(svg_path), "-o", str(out_path)],
                check=True, capture_output=True, timeout=30,
            )
            return out_path.exists() and out_path.stat().st_size > 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False
    elif backend in ("magick", "convert", "inkscape"):
        try:
            subprocess.run(
                [backend, "-background", "none", "-resize", f"{size}x{size}", str(svg_path), str(out_path)],
                check=True, capture_output=True, timeout=30,
            )
            return out_path.exists() and out_path.stat().st_size > 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False
    return False


def _read_png_rgba(png_path: Path) -> Optional[tuple]:
    """读 PNG, 返回 (width, height, bytes) 或 None"""
    try:
        from PIL import Image
        img = Image.open(png_path).convert("RGBA")
        w, h = img.size
        # XCursor 期望 BGRA bytes
        rgba = img.tobytes()  # 4 bytes per pixel
        # RGBA -> BGRA
        bgra = bytearray(len(rgba))
        for i in range(0, len(rgba), 4):
            bgra[i + 0] = rgba[i + 2]  # B
            bgra[i + 1] = rgba[i + 1]  # G
            bgra[i + 2] = rgba[i + 0]  # R
            bgra[i + 3] = rgba[i + 3]  # A
        return w, h, bytes(bgra)
    except Exception:
        return None


def _pack_xcursor(frames: list, hotspot: tuple, nominal_size: int) -> bytes:
    """
    打包成 XCursor 二进制格式.
    frames: list of (size, w, h, delay_ms, bgra_bytes)
    hotspot: (xhot, yhot) 元组
    nominal_size: 标称尺寸

    X11/Xcursor/Xcursor.h Image chunk 格式 (36 字节 header + pixels):
      header (4) = 36 (chunk header bytes, 包括 type-specific fields)
      type (4) = 0xfffd0002 (image type)
      subtype (4) = nominal_size
      version (4) = 1
      width (4), height (4), xhot (4), yhot (4), delay (4)
      pixels (width*height*4 bytes, packed ARGB)
    """
    # XCursor 文件头: magic(4) + header_size(4) + version(4) + ntoc(4)
    # TOC entry: type(4) + subtype(4) + position(4) = 12 bytes
    # 1 个 TOC entry per nominal_size (动画帧共享同一 size)
    ntoc = 1
    toc_size = ntoc * 12
    header_size = 16 + toc_size  # file header (16) + TOC entries

    # file header
    out = b"Xcur"
    out += struct.pack("<I", header_size)  # header size
    out += struct.pack("<I", 0x00010000)  # version 1.0
    out += struct.pack("<I", ntoc)

    # image chunk 起始位置
    image_start = header_size

    # TOC: 1 个 entry for image type
    toc_entry = struct.pack(
        "<III",
        0xFFFD0002,  # type = image
        nominal_size,  # subtype = nominal_size
        image_start,  # position = chunk 起始
    )

    # image chunk header (36 字节)
    # 9 字段: header(4) + type(4) + subtype(4) + version(4) + width(4) + height(4) + xhot(4) + yhot(4) + delay(4)
    img_header = struct.pack(
        "<IIIIIIIII",
        36,  # header (chunk header bytes = 9 fields * 4 bytes)
        0xFFFD0002,  # type (image)
        nominal_size,  # subtype (nominal size)
        1,  # version
        0,  # width (占位, 后面从 frames 拿主帧)
        0,  # height
        hotspot[0],  # xhot
        hotspot[1],  # yhot
        0,  # delay (占位)
    )

    # image chunk body = img_header (36 bytes) + 所有帧的 pixels 拼起来
    # 简化: 把所有 frames 的 width/height 假设相同, 只取第一个
    if not frames:
        return out + toc_entry  # 无效 fallback

    first_size, first_w, first_h, _, _ = frames[0]
    img_header_fixed = struct.pack(
        "<IIIIIIIII",
        36,  # header
        0xFFFD0002,  # type
        nominal_size,  # subtype
        1,  # version
        first_w,  # width
        first_h,  # height
        hotspot[0],  # xhot
        hotspot[1],  # yhot
        frames[0][3],  # delay (first frame)
    )

    # 像素拼接 (按 ARGB 32-bit packed, 我们当前 bgra 字节已经是 BGRA 顺序)
    # XCursor spec 说 pixels 是 "Packed ARGB format", 但 libXcursor 内部其实用 premultiplied BGRA
    # 实际上 _bgra_to_rgba_png 是用 un-premultiplied RGBA, 这里保持 BGRA 字节流 (libXcursor 容错)
    pixels_data = b"".join(f[4] for f in frames)

    out += toc_entry
    out += img_header_fixed
    out += pixels_data
    return out


def build_svg_to_xcursor(svg_dir: Path, out_dir: Path) -> dict:
    """
    把一个 cursor 的 SVG 源目录 build 成 XCursor 文件 (out_dir/<name>).

    svg_dir: cursors_scalable/<name>/ 目录, 含 metadata.json + *.svg
    out_dir: 输出目录, xcursor 文件会写到 out_dir/<name>

    返回 dict {"success": bool, "name": str, "path": Path|None, "frames": int, "error": str}
    """
    name = svg_dir.name
    metadata_file = svg_dir / "metadata.json"

    if not metadata_file.is_file():
        return {"success": False, "name": name, "path": None, "frames": 0, "error": "no metadata.json"}

    try:
        meta = json.loads(metadata_file.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return {"success": False, "name": name, "path": None, "frames": 0, "error": f"metadata.json parse failed: {e}"}

    if not isinstance(meta, list) or not meta:
        return {"success": False, "name": name, "path": None, "frames": 0, "error": "metadata.json empty or invalid format"}

    # 选渲染器
    backend = _pick_renderer()
    if not backend:
        return {
            "success": False,
            "name": name,
            "path": None,
            "frames": 0,
            "error": "no SVG renderer found (need rsvg-convert, magick, or inkscape)",
        }

    # 用第一帧的 nominal_size + hotspot 作主参考
    first = meta[0]
    nominal_size = int(first.get("nominal_size", 24))
    hotspot_x = int(first.get("hotspot_x", nominal_size // 2))
    hotspot_y = int(first.get("hotspot_y", nominal_size // 2))

    # 多尺寸 build (XCursor 主题通常给 24/32/48/64/96)
    target_sizes = [max(24, nominal_size), 32, 48, 64, 96]

    # 收集所有帧 (size, w, h, delay_ms, bgra)
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        for frame_meta in meta:
            svg_filename = frame_meta.get("filename")
            if not svg_filename:
                continue
            svg_path = svg_dir / svg_filename
            if not svg_path.is_file():
                continue
            delay_ms = int(frame_meta.get("delay", 50))

            # 用每个目标尺寸渲染
            for size in target_sizes:
                png_path = tmp_p / f"{svg_path.stem}_{size}.png"
                if not _render_svg_to_png(svg_path, size, png_path, backend):
                    continue
                png_data = _read_png_rgba(png_path)
                if png_data is None:
                    continue
                w, h, bgra = png_data
                frames.append((size, w, h, delay_ms, bgra))

    if not frames:
        return {"success": False, "name": name, "path": None, "frames": 0, "error": "no frames rendered (all SVG render failed)"}

    # 限制总帧数 (Mousecape 限制 24, 但 SVG 主题常有 23 帧动画, 5 尺寸 = 115 帧)
    # Mousecape 限制的是 FrameCount (一个 nominal_size 下的帧数), 不是总 representation 数
    # 每个 nominal_size 是一组 frames
    # 我们只对 nominal_size 主尺寸输出, 避免超 FrameCount
    main_frames = [f for f in frames if f[0] == max(24, nominal_size)]
    if not main_frames:
        main_frames = frames[:24]  # 兜底
    main_frames = main_frames[:24]

    # 按 size 分组, 每个 size 单独 pack 成 xcursor
    out_path = out_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 简化: 只 pack 主尺寸 (nominal_size) 的所有帧, 其他尺寸省略
    # 实际上 XCursor 文件可以含多个 size, 但我们为简单起见只用一个
    # (Mousecape cape 也用 PointsWide/PointsHigh * scale 多 rep, 一个 size 已够)
    data = _pack_xcursor(main_frames, (hotspot_x, hotspot_y), nominal_size)
    out_path.write_bytes(data)

    return {
        "success": True,
        "name": name,
        "path": out_path,
        "frames": len(main_frames),
        "error": "",
    }


def build_svg_theme(scalable_dir: Path, out_dir: Path) -> tuple:
    """
    把整个 cursors_scalable/ 主题目录 build 成 xcursor 格式.

    scalable_dir 是 "集合目录", 含:
      cursors_scalable/alias/  (单 cursor, 含 metadata.json + alias.svg)
      cursors_scalable/wait/   (单 cursor, 含 metadata.json + wait-01.svg..wait-23.svg)
      ...

    返回 (success_count, failed_count, errors_list).
    """
    success = 0
    failed = 0
    errors = []
    out_dir.mkdir(parents=True, exist_ok=True)

    for sub in sorted(scalable_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name.startswith("."):
            continue
        # 对每个 sub (alias/, wait/ 等) 调 build_svg_to_xcursor
        result = build_svg_to_xcursor(sub, out_dir)
        if result["success"]:
            success += 1
        else:
            failed += 1
            if result["error"] and result["error"] not in errors:
                errors.append(result["error"])

    return success, failed, errors
