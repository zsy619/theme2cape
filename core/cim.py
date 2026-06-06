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


@dataclass
class CursorSet:
    theme: str
    cursors: dict
