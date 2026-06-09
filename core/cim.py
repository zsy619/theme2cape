from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class CursorFrame:
    # 路径(由 kxcursor_reader 写入 decoded/ 目录) - 仍保留方便调试
    image_path: str
    # XCursor image header 里的 xhot/yhot (像素坐标)
    hotspot: Tuple[int, int]
    # XCursor image header 里的 delay (毫秒)。0 表示静态。
    delay: float = 0.0
    # 像素宽高 (来自 image header 的 width/height)
    width: int = 0
    height: int = 0
    # 在同尺寸下的帧序号 (0..N-1)。0 表示该尺寸下唯一一帧或第一帧
    frame_index: int = 0
    # XCursor TOC subtype 字段 (16/20/22/24/28/...) 反映"标称尺寸"
    nominal_size: int = 0


@dataclass
class Cursor:
    name: str
    frames: List[CursorFrame]
    # 真实磁盘路径(由 kxcursor_reader.read_xcursor 写入), 用于 normalizer
    # 在 MACOS_CURSOR_MAP 找不到时通过 os.path.realpath() 解析 symlink
    # 把 X11 1.20+ 32 位 hex 哈希名映射到标准 cursor 名
    path: str = ""

