"""
CursorFX 二进制文件解析器.

解析 Stardock CursorFX 的二进制格式文件 (*.CursorFX).

格式背景:
  - CursorFX 二进制文件是一个压缩的二进制格式,包含:
    1. 文件头 (header): 版本、大小等元数据
    2. 压缩数据: zlib 压缩的光标数据
    3. 主题信息: UTF-16LE 编码的主题名、作者等
    4. 光标数据: 多个光标的图像数据和元数据

二进制格式结构:
  Header:
    - version (uint32): 文件版本
    - header_size (uint32): 头部大小
    - data_size (uint32): 解压后数据大小
    - theme_type (uint32): 主题类型
    - info_size (uint32): 主题信息大小 (位于 header_size - 4 位置)

  Compressed Data:
    - 从 header_size 位置开始, zlib 压缩
    - 解压后长度应等于 data_size

  Theme Info:
    - info_size 长度的 UTF-16LE 字符串
    - 以 '\\0' 分隔的主题信息

  Cursor Data (循环):
    - pointer_type (uint32): 类型 (2 = 指针图像)
    - 各种元数据 (帧数、尺寸、热点等)
    - PNG 图像数据 (BGRA 格式)
    - 可选的脚本数据

参考实现:
  https://github.com/SystemRage/Metamorphosis (Metamorphosis.py, Stardock.convert_FX)
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import BinaryIO

from PIL import Image

from core.cim import Cursor, CursorFrame
from mapper.cursorfx_x11_map import CURSORFX_SECTION_TO_X11


# Mousecape 硬限制: 1 帧 ≤ FrameCount ≤ 24
MAX_MOUSECAPE_FRAMES = 24


# ----- CursorFX 光标名称映射 -----
# Metamorphosis 项目中定义的光标索引到名称的映射
# 参考: Metamorphosis.py cursor_namemap
CURSORFX_INDEX_TO_NAME: dict[int, str] = {
    0: "Arrow",        # 普通箭头
    1: "Help",         # 帮助 (箭头+问号)
    2: "AppStarting",  # 应用启动
    3: "Wait",         # 等待
    4: "Cross",        # 精确选择
    5: "IBeam",        # 文本选择
    6: "Handwriting",  # 手写
    7: "NO",           # 禁止
    8: "SizeNS",       # 南北调整
    9: "SizeS",        # 南调整
    10: "SizeWE",      # 东西调整
    11: "SizeE",       # 东调整
    12: "SizeNWSE",    # 西北-东南调整
    13: "SizeSE",      # 东南调整
    14: "SizeNESW",    # 东北-西南调整
    15: "SizeSW",      # 西南调整
    16: "SizeAll",     # 移动
    17: "UpArrow",     # 上箭头
    18: "Hand",        # 手形
    19: "Button",      # 按钮
}


# ----- 数据结构 -----


class CursorFxHeader:
    """CursorFX 文件头."""

    __slots__ = ("version", "header_size", "data_size", "theme_type", "info_size")

    def __init__(
        self,
        version: int,
        header_size: int,
        data_size: int,
        theme_type: int,
        info_size: int,
    ):
        self.version = version
        self.header_size = header_size
        self.data_size = data_size
        self.theme_type = theme_type
        self.info_size = info_size


class CursorFxImage:
    """CursorFX 光标图像数据."""

    __slots__ = (
        "image_index",
        "cursor_status",
        "frame_count",
        "image_width",
        "image_height",
        "frame_interval",
        "animation_type",
        "hot_x",
        "hot_y",
        "image_data",
    )

    def __init__(
        self,
        image_index: int,
        cursor_status: int,
        frame_count: int,
        image_width: int,
        image_height: int,
        frame_interval: int,
        animation_type: int,
        hot_x: int,
        hot_y: int,
        image_data: bytes,
    ):
        self.image_index = image_index
        self.cursor_status = cursor_status
        self.frame_count = max(1, frame_count)
        self.image_width = image_width
        self.image_height = image_height
        # Interval 单位是毫秒
        self.frame_interval = max(0, frame_interval)
        self.animation_type = animation_type
        self.hot_x = max(0, hot_x)
        self.hot_y = max(0, hot_y)
        self.image_data = image_data


# ----- 解析函数 -----


def _read_uint32(data: bytes, offset: int) -> int:
    """读取小端序 uint32."""
    return struct.unpack_from("<I", data, offset)[0]


def parse_cursorfx_header(data: bytes) -> CursorFxHeader:
    """
    解析 CursorFX 文件头.

    Args:
        data: 文件二进制数据

    Returns:
        CursorFxHeader 对象

    Raises:
        ValueError: 文件格式无效
    """
    if len(data) < 20:
        raise ValueError("文件太小,不是有效的 CursorFX 文件")

    # 读取头部字段
    version = _read_uint32(data, 0)
    header_size = _read_uint32(data, 4)
    data_size = _read_uint32(data, 8)
    theme_type = _read_uint32(data, 12)

    # info_size 位于 header_size - 4 位置
    info_size = _read_uint32(data, header_size - 4)

    return CursorFxHeader(
        version=version,
        header_size=header_size,
        data_size=data_size,
        theme_type=theme_type,
        info_size=info_size,
    )


def decompress_cursorfx_data(data: bytes, header: CursorFxHeader) -> bytes:
    """
    解压 CursorFX 数据.

    Args:
        data: 文件二进制数据
        header: 文件头

    Returns:
        解压后的数据

    Raises:
        ValueError: 解压失败或数据损坏
    """
    # 根据主题类型使用不同的解压策略
    if header.theme_type == 2003:
        # type=2003: 特殊处理
        return _decompress_type_2003(data, header)
    
    # 默认处理 type=2002 和其他类型
    try:
        # 从 header_size 位置开始解压
        compressed = data[header.header_size :]
        decompressed = zlib.decompress(compressed)

        # 验证解压后大小
        if len(decompressed) != header.data_size:
            raise ValueError(
                f"解压后数据大小不匹配: 期望 {header.data_size}, 实际 {len(decompressed)}"
            )

        return decompressed
    except zlib.error as e:
        raise ValueError(f"解压失败: {e}")


def _decompress_type_2003(data: bytes, header: CursorFxHeader) -> bytes:
    """
    处理 type=2003 的 CursorFX 文件.

    type=2003 格式特点:
    - header_size 之后是 UTF-16LE 编码的主题名称（以双零结尾）
    - 主题名称之后是元数据
    - 数据可能未压缩或使用不同的压缩方式

    Args:
        data: 文件二进制数据
        header: 文件头

    Returns:
        解压后的数据（前面填充 info_size 字节，使光标数据从 info_size 位置开始）
    """
    pos = header.header_size

    # 跳过 UTF-16LE 主题名称（以双零结尾）
    while pos + 1 < len(data):
        if data[pos] == 0 and data[pos + 1] == 0:
            pos += 2  # 跳过双零
            break
        pos += 2

    # type=2003 的数据可能是未压缩的
    # 数据大小可能与 header.data_size 略有差异，取较小值
    remaining_size = min(len(data) - pos, header.data_size)
    cursor_data = data[pos:pos + remaining_size]

    # 重要：parse_cursorfx_images 从 info_size 位置开始解析
    # 所以需要在前面填充 info_size 字节，使光标数据从 info_size 位置开始
    padding = b'\x00' * header.info_size
    result = padding + cursor_data

    return result


def parse_theme_info(data: bytes, info_size: int) -> tuple[str, list[str]]:
    """
    解析主题信息.

    Args:
        data: 解压后的数据
        info_size: 主题信息大小

    Returns:
        (theme_name, info_list)
        - theme_name: 主题名称
        - info_list: 完整信息列表 [主题名, 作者, ...]
    """
    if info_size == 0:
        return "Unknown", []

    try:
        # UTF-16LE 编码, 以 '\0' 分隔
        info_data = data[:info_size]
        info_text = info_data.decode("utf-16le")

        # 分割信息字段
        info_list = [s.strip() for s in info_text.split("\0") if s.strip()]

        # 主题名通常是第一个字段
        theme_name = info_list[0] if info_list else "Unknown"

        return theme_name, info_list
    except (UnicodeDecodeError, IndexError):
        return "Unknown", []


def parse_cursorfx_images(data: bytes, info_size: int) -> list[CursorFxImage]:
    """
    解析所有光标图像.

    Args:
        data: 解压后的数据
        info_size: 主题信息大小

    Returns:
        CursorFxImage 列表

    Raises:
        ValueError: 数据损坏
    """
    images: list[CursorFxImage] = []
    cur_pos = info_size

    while cur_pos < len(data):
        # 读取指针类型和大小
        pointer_type = _read_uint32(data, cur_pos)
        size_of_header_without_script_1 = _read_uint32(data, cur_pos + 4)
        size_of_header_and_image = _read_uint32(data, cur_pos + 8)

        # 跳过非指针类型
        if pointer_type != 2:
            cur_pos += size_of_header_and_image
            continue

        # 读取光标元数据 (16 个 uint32, 从 cur_pos + 12 开始)
        offset = cur_pos + 12  # 3 * 4 bytes (前面的 3 个字段)

        # 解包 16 个 uint32
        (
            unknown_1,
            image_index,
            cursor_status,
            unknown_2,
            frame_count,
            image_width,
            image_height,
            frame_interval,
            animation_type,
            unknown_3,
            mouse_x,
            mouse_y,
            size_of_header_with_script,
            size_of_image,
            size_of_header_without_script_2,
            size_of_script,
        ) = struct.unpack_from("<16I", data, offset)

        # 验证大小一致性
        if (
            size_of_header_without_script_1 != size_of_header_without_script_2
            or size_of_header_with_script != size_of_header_without_script_1 + size_of_script
            or size_of_header_and_image != size_of_header_with_script + size_of_image
            or size_of_image != image_width * image_height * 4
        ):
            # 数据不一致,跳过此图像
            cur_pos += size_of_header_and_image
            continue

        # 提取图像数据 (BGRA 格式)
        image_start = cur_pos + size_of_header_with_script
        image_end = cur_pos + size_of_header_and_image
        image_data = data[image_start:image_end]

        # 创建图像对象
        img = CursorFxImage(
            image_index=image_index,
            cursor_status=cursor_status,
            frame_count=frame_count,
            image_width=image_width,
            image_height=image_height,
            frame_interval=frame_interval,
            animation_type=animation_type,
            hot_x=mouse_x,
            hot_y=mouse_y,
            image_data=image_data,
        )

        images.append(img)

        # 移动到下一个图像
        cur_pos += size_of_header_and_image

    return images


def bgra_to_rgba(bgra_data: bytes, width: int, height: int) -> Image.Image:
    """
    将 BGRA 数据转换为 PIL RGBA 图像.

    Args:
        bgra_data: BGRA 格式的原始数据
        width: 图像宽度
        height: 图像高度

    Returns:
        PIL Image 对象 (RGBA 模式)
    """
    # 尝试两种解析方式:
    # 1. 自下而上 (bottom-up, direction=-1): Windows BMP 格式
    # 2. 自上而下 (top-down, direction=1): 标准格式
    
    # 方式 1: 自下而上
    try:
        img_bottom_up = Image.frombytes("RGBA", (width, height), bgra_data, "raw", "BGRA", 0, -1)
        # 统计颜色数量
        pixels_bu = list(img_bottom_up.getdata())
        colors_bu = len(set(pixels_bu))
    except Exception:
        img_bottom_up = None
        colors_bu = 0
    
    # 方式 2: 自上而下
    try:
        img_top_down = Image.frombytes("RGBA", (width, height), bgra_data, "raw", "BGRA", 0, 1)
        # 统计颜色数量
        pixels_td = list(img_top_down.getdata())
        colors_td = len(set(pixels_td))
    except Exception:
        img_top_down = None
        colors_td = 0
    
    # 选择颜色数量更多的图像（说明解析更正确）
    if colors_bu >= colors_td and img_bottom_up is not None:
        return img_bottom_up
    elif img_top_down is not None:
        return img_top_down
    elif img_bottom_up is not None:
        return img_bottom_up
    else:
        # 两种方式都失败，使用默认方式
        return Image.frombytes("RGBA", (width, height), bgra_data, "raw", "BGRA", 0, -1)


def split_strip_png(
    image: Image.Image,
    frames_count: int,
) -> list[Image.Image]:
    """
    将横向拼接的 PNG 切分成单帧.

    Args:
        image: PIL 图像 (横向拼接的多帧)
        frames_count: 帧数

    Returns:
        单帧图像列表
    """
    if frames_count <= 1:
        return [image]

    total_w, total_h = image.size

    # 检查宽度是否整除
    if total_w % frames_count != 0:
        # 宽度不整除,退化为单帧
        return [image]

    frame_w = total_w // frames_count
    frames: list[Image.Image] = []

    for i in range(frames_count):
        crop = image.crop((i * frame_w, 0, (i + 1) * frame_w, total_h))
        frames.append(crop)

    return frames


def _subsample_indices(n: int, k: int) -> list[int]:
    """
    均匀下采样: n 个原始帧 → k 个采样帧.

    公式: indices = { round(i * (n-1) / (k-1)) | i in [0, k-1] }
    - 保留首尾两帧
    - 中间帧等距分布
    - 去重 + 排序
    """
    if n <= 0 or k <= 0:
        return []
    if k >= n:
        return list(range(n))
    return sorted({int(round(i * (n - 1) / (k - 1))) for i in range(k)})


# ----- 主入口函数 -----


def is_cursorfx_binary(path: Path) -> bool:
    """
    判断文件是否为 CursorFX 二进制文件.

    判定规则:
      - 文件存在且是文件
      - 文件扩展名为 .CursorFX (不区分大小写)
      - 文件大小至少 20 字节 (最小头部大小)

    Args:
        path: 文件路径

    Returns:
        True 如果是 CursorFX 二进制文件
    """
    if not path or not path.is_file():
        return False

    # 检查扩展名
    if path.suffix.lower() != ".cursorfx":
        return False

    # 检查文件大小
    try:
        return path.stat().st_size >= 20
    except OSError:
        return False


def read_cursorfx_binary(
    file_path: Path,
    decoded_root: Path | None = None,
) -> tuple[str, list[Cursor]]:
    """
    读取 CursorFX 二进制文件,返回 (theme_name, [Cursor 列表]).

    行为:
      1. 解析文件头
      2. 解压数据
      3. 提取主题信息
      4. 解析所有光标图像
      5. 转换为 Cursor 对象

    Args:
        file_path: CursorFX 二进制文件路径
        decoded_root: 解码后 PNG 的保存目录 (可选)

    Returns:
        (theme_name, [Cursor 列表])
        - theme_name: 主题名称
        - Cursor 列表: 每个 X11 alias 一个 Cursor

    Raises:
        ValueError: 文件格式无效或数据损坏
        FileNotFoundError: 文件不存在
    """
    # 读取文件
    with open(file_path, "rb") as f:
        data = f.read()

    # 解析文件头
    header = parse_cursorfx_header(data)

    # 解压数据
    decompressed = decompress_cursorfx_data(data, header)

    # 解析主题信息
    theme_name, info_list = parse_theme_info(decompressed, header.info_size)

    # 解析光标图像
    images = parse_cursorfx_images(decompressed, header.info_size)

    # 创建 decoded 目录
    if decoded_root is None:
        decoded_root = file_path.parent / "decoded"
    decoded_root.mkdir(parents=True, exist_ok=True)

    # 转换为 Cursor 对象
    cursors: list[Cursor] = []

    for img in images:
        # 获取光标名称
        cursor_name = CURSORFX_INDEX_TO_NAME.get(img.image_index, f"Cursor_{img.image_index}")

        # 将 BGRA 转换为 RGBA
        try:
            rgba_image = bgra_to_rgba(img.image_data, img.image_width, img.image_height)
        except Exception as e:
            print(f"  [warn] 无法转换图像 {cursor_name}: {e}")
            continue

        # 切分帧
        frames = split_strip_png(rgba_image, img.frame_count)
        n_original = len(frames)

        if n_original == 0:
            continue

        # FrameCount ≤ 24 硬限制
        if n_original > MAX_MOUSECAPE_FRAMES:
            indices = _subsample_indices(n_original, MAX_MOUSECAPE_FRAMES)
            frames = [frames[i] for i in indices]
            scale = n_original / MAX_MOUSECAPE_FRAMES
            sampled_interval = (
                max(1, int(round(img.frame_interval * scale))) if img.frame_interval > 0 else 0
            )
            print(
                f"  [info] CursorFX {cursor_name}: {n_original} frames > 24, "
                f"subsampled to {len(frames)} (interval {img.frame_interval}ms → {sampled_interval}ms)"
            )
            interval = sampled_interval
        else:
            interval = img.frame_interval

        # 保存帧到文件
        frame_w, frame_h = frames[0].size
        nominal = max(frame_w, frame_h)

        out_dir = decoded_root / cursor_name
        out_dir.mkdir(parents=True, exist_ok=True)

        cursor_frames: list[CursorFrame] = []
        for idx, frame in enumerate(frames):
            out_path = out_dir / f"{nominal}_{idx}.png"
            frame.save(out_path, format="PNG")

            cursor_frames.append(
                CursorFrame(
                    image_path=str(out_path),
                    hotspot=(img.hot_x, img.hot_y),
                    delay=float(interval),
                    width=frame_w,
                    height=frame_h,
                    frame_index=idx,
                    nominal_size=nominal,
                )
            )

        # 查 X11 alias 列表, 每个 alias 生成一个 Cursor
        aliases = CURSORFX_SECTION_TO_X11.get(cursor_name, [cursor_name])

        for alias in aliases:
            cursors.append(
                Cursor(
                    name=alias,
                    frames=cursor_frames,
                    path=str(file_path),
                )
            )

    return theme_name, cursors
