"""
按 Mousecape v2.0 cape 文件规范生成 .cape。

规范来源:
  - /tmp/Mousecape/Mousecape/Mousecape/src/models/MCCursorLibrary.m
  - /tmp/Mousecape/Mousecape/Mousecape/src/models/MCCursor.m
  - /tmp/Mousecape/Mousecape/mousecloak/MCDefs.m
  - /tmp/Mousecape/Mousecape/mousecloak/NSBitmapImageRep+ColorSpace.m

⚠️ 重要发现 (经过读源码验证):
  MCCursorLibrary.m L83 用 [NSDictionary dictionaryWithContentsOfURL:] 读 plist,
  这是 Foundation 的老 API, **只支持 XML plist**, binary plist 一律返回 nil。
  所以 .cape 必须是 XML plist,不能是 binary。
  (我之前改成 binary 反而让所有 cape 都无法导入, 此次回退为 XML)

顶层包含 9 个字段:
  MinimumVersion / Version / CapeName / CapeVersion / Cloud / Author /
  HiDPI / Identifier / Cursors

Cursors 是 dict, key = mousecape cursor identifier (如
"com.apple.coregraphics.Arrow"), value 是另一个 dict 含 7 个字段:
  FrameCount (int)         动画帧数; 静态为 1
  FrameDuration (real)     单帧持续时间(秒)
  HotSpotX / HotSpotY (real) 热点坐标(PointsWide/High 同坐标空间)
  PointsWide / PointsHigh (real) @1x 逻辑尺寸(点)
  Representations (array<data>) 嵌入的 PNG 字节, 每张 = 一组动画帧垂直堆叠
"""

import getpass
import io
import plistlib
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from PIL import Image

from core.validator import CapeValidator


# Mousecape 支持的标准 scale 倍数 (@1x/@2x/@5x)
_STANDARD_SCALES: tuple[float, ...] = (1.0, 2.0, 5.0)

# 用户要求的 @1x 目标尺寸
_DEFAULT_TARGET_SIZE = 48


def _select_base_size(frames, target: int = _DEFAULT_TARGET_SIZE) -> tuple[int, int]:
    """
    选 @1x 逻辑点尺寸。

    策略:
      1. 优先精确匹配 target (如 48)
      2. 否则用 largest <= target
      3. 否则 (主题里所有图都 > target) 用最小可用尺寸
    """
    sizes = sorted({(f.width, f.height) for f in frames})
    if not sizes:
        return target, target
    # 1) exact
    if (target, target) in sizes:
        return target, target
    # 2) largest <= target
    below = [s for s in sizes if s[0] <= target and s[1] <= target]
    if below:
        return below[-1]
    # 3) smallest
    return sizes[0]


def _build_representations(frames, points_w: int, points_h: int) -> list[bytes]:
    """
    把每个 size 下的多帧垂直堆叠成一张大图, 再为每个 scale (@1x/@2x/@5x)
    选最接近该 scale 的 size, 编码成 PNG 字节塞进 Representations。

    关键约束(必须满足, 否则 MCCursor 渲染异常):
      rep.pixelsHigh == pointsHigh * frameCount
      rep.pixelsWide == pointsWide * scale
      且 scale 必须是整数 (1.0, 2.0, 5.0 等 MCCursorScale100/200/500 才有意义)
    """
    by_size: dict[tuple[int, int], list] = defaultdict(list)
    for f in frames:
        by_size[(f.width, f.height)].append(f)
    for key in by_size:
        by_size[key].sort(key=lambda f: f.frame_index)

    sizes_sorted = sorted(by_size.keys())
    representations: list[bytes] = []
    seen: set[bytes] = set()
    for scale in _STANDARD_SCALES:
        target_w = points_w * scale
        target_h = points_h * scale
        # 严格约束: 必须选"整数倍"的 size, 否则 mcc_scale=scale*100 截断会冲突
        # (e.g. Vimix 64/48=1.33 → int(1.33)*100=100 与 @1x 冲突)
        # 优先精确匹配, 其次从大到小找能被 target 整除的 size
        best = None
        # 1) 精确匹配
        for s in sizes_sorted:
            if s == (target_w, target_h):
                best = s
                break
        # 2) 整数倍匹配 (s.w % points_w == 0 AND s.h % points_h == 0)
        if best is None:
            candidates = [
                s for s in sizes_sorted
                if s[0] % points_w == 0 and s[1] % points_h == 0
            ]
            if candidates:
                # 选最接近 target 的
                best = min(
                    candidates,
                    key=lambda s: abs(s[0] - target_w) + abs(s[1] - target_h),
                )
        if best is None:
            continue  # 该 scale 没有合适的 size, 跳过
        group = by_size[best]
        if not group:
            continue
        w, h = best
        n = len(group)
        # 垂直堆叠: 第一帧在最上面, 最后一帧在最下面
        stacked = Image.new("RGBA", (w, h * n), (0, 0, 0, 0))
        for i, f in enumerate(group):
            img = Image.open(f.image_path).convert("RGBA")
            if img.size != (w, h):
                # 罕见: 实际像素与声明不一致, 最近邻 resize 兜底
                img = img.resize((w, h), Image.NEAREST)
            stacked.paste(img, (0, i * h))
        buf = io.BytesIO()
        stacked.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        if png_bytes in seen:
            continue  # 去重, 避免 @2x/@5x 落到同一张图时重复
        seen.add(png_bytes)
        representations.append(png_bytes)
    return representations


def _frame_count(frames) -> int:
    """动画帧数 = 任何 size 桶里最多的条目数 (静态光标每桶 1 帧)"""
    by_size: dict[tuple[int, int], int] = defaultdict(int)
    for f in frames:
        by_size[(f.width, f.height)] += 1
    return max(by_size.values()) if by_size else 1


def _frame_duration_seconds(frames) -> float:
    """单帧持续时间(秒)。

    静态光标 (FrameCount=1) 按真实 .cape 的做法给 1.0。
    动画光标取首个 delay > 0 的值换算成秒 (xcursor 是毫秒)。
    """
    if _frame_count(frames) <= 1:
        return 1.0
    for f in frames:
        if f.delay > 0:
            return float(f.delay) / 1000.0
    return 1.0


def _hotspot_for_points(frames, points_w: int, points_h: int) -> tuple[float, float]:
    """选与 PointsWide/High 同坐标空间的 hotspot。

    背景: xcursor image header 的 xhot/yhot 是该 PNG 的像素坐标,
    不同 size 报出来的数字不同(16x16 箭头 hotspot=(8,8), 96x96 的是(48,48))。
    若 PointsWide=96 但 hotspot 取自 16x16 那帧, 实际点击点会偏到左上角。
    """
    # 1) 优先匹配完全相同 size 的 frame
    for f in frames:
        if f.width == points_w and f.height == points_h:
            return float(f.hotspot[0]), float(f.hotspot[1])
    # 2) fallback: 用最小 frame 的 hotspot 按比例缩放
    ref = min(frames, key=lambda f: f.width * f.height)
    if ref.width <= 0 or ref.height <= 0:
        return 0.0, 0.0
    sx = points_w / ref.width
    sy = points_h / ref.height
    return float(ref.hotspot[0]) * sx, float(ref.hotspot[1]) * sy


def build_cape(
    theme_name: str,
    cursor_set: Iterable[dict],
    out_dir,
    author: str | None = None,
    target_size: int = _DEFAULT_TARGET_SIZE,
    self_validate: bool = True,
    display_name: str | None = None,
):
    """
    把归一化后的 cursor 列表序列化成 .cape。

    cursor_set: 每个元素形如
        {"mac_name": <identifier>, "frames": [CursorFrame, ...]}
    target_size: @1x 目标点尺寸 (默认 48)。若主题里没有该尺寸,
        会用"不超过 target_size 的最大尺寸"作为兜底
    self_validate: 写完后是否跑一遍 Mousecape 解析模拟, 不通过则抛异常
    display_name: 用作 CapeName 显示给用户看, 默认等于 theme_name
        (用于文件名和 CapeName 不同的场景, e.g. 文件名 sanitize 后 vs 原始可读名)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if display_name is None:
        display_name = theme_name

    if author is None:
        try:
            author = getpass.getuser()
        except Exception:
            author = "xcursor2cape"

    # 按 v2.0 规范构建顶层 dict
    cape: dict = {
        "MinimumVersion": 2.0,
        "Version": 2.0,
        "CapeName": display_name,
        "CapeVersion": 1.0,
        "Cloud": False,
        "Author": author,
        "HiDPI": True,
        "Identifier": f"local.{author}.{theme_name}.{int(time.time())}",
        "Cursors": {},
    }

    # 处理去重: 多个 X11 cursor 名可能映射到同一个 macOS identifier
    # (e.g. Vimix 109 个 X11 名 → 29 个 mac identifier, 80 个会冲突)
    #
    # 策略:
    #   1) 第一个用 mac identifier, 后续冲突的合并并打印 warning
    #   2) **Fallback 补齐 (两层)**:
    #      a) 同 identifier 内: 主题里 X11 cursor 文件 0 字节 → 用同 identifier 其他 X11 帧
    #         例: Quintom 主题里 `alias` (→ Alias) 是 0 字节, 但 `link` (→ Link, 不同 id) 没用
    #             → 没有同 identifier 的 sibling 可用, 进入 (b)
    #      b) 跨 identifier fallback: 主题完全没提供某个 mac identifier 的 cursor
    #         (e.g. Quintom 没 Alias / Open / Counting Down) → 用语义相邻的 identifier 帧
    #         (e.g. Alias → Link, Open → Closed, Counting Down → Wait)
    from collections import defaultdict

    # macOS 全部 cursor identifier (严格按 mapper/macos_full.md 文档)
    #
    # 来源 (md 文档三段):
    #   一、com.apple.coregraphics.* (11 个, 9 经典 + 2 macOS 26 新增)
    #   二、com.apple.cursor.N       (41 个, N ∈ {2,3,4,5,7..43}, 6 故意空缺)
    # 合计 52 个 identifier.
    #
    # ⚠️ 关键点:
    #   1) `_ALL_MAC_IDENTIFIERS` 是 "spare 槽位候选池", 用于 `_find_spare_identifier`
    #      给帧数据不同的同名 X11 cursor 分配独立槽位. 它**不是** cape 文件硬上限.
    #   2) Mousecape cursorMap 实际容量 = 这个集合的 size = 52. 我们用
    #      `_ALL_MAC_CAPACITY` 跟踪, Summary 报告里直接用, 不要硬编码 50.
    #
    # Window 系列编号说明 (来自 md 文档, **必须严格按此编号**):
    #   com.apple.cursor.27  Window E       (东向窗口边)
    #   com.apple.cursor.28  Window E-W     (东西向窗口边)
    #   com.apple.cursor.29  Window NE      (东北向窗口角)
    #   com.apple.cursor.30  Window NE-SW   (东北-西南对角线)
    #   com.apple.cursor.31  Window N       (北向窗口边)
    #   com.apple.cursor.32  Window N-S     (南北向窗口边)
    #   com.apple.cursor.33  Window NW      (西北向窗口角)
    #   com.apple.cursor.34  Window NW-SE   (西北-东南对角线)
    #   com.apple.cursor.35  Window SE      (东南向窗口角)
    #   com.apple.cursor.36  Window S       (南向窗口边)
    #   com.apple.cursor.37  Window SW      (西南向窗口角)
    #   com.apple.cursor.38  Window W       (西向窗口边)
    _ALL_MAC_IDENTIFIERS = {
        # ===== com.apple.coregraphics.* (11 个) =====
        "com.apple.coregraphics.Arrow",
        "com.apple.coregraphics.IBeam",
        "com.apple.coregraphics.IBeamXOR",
        "com.apple.coregraphics.Alias",
        "com.apple.coregraphics.Copy",
        "com.apple.coregraphics.Move",
        "com.apple.coregraphics.ArrowCtx",
        "com.apple.coregraphics.Wait",
        "com.apple.coregraphics.Empty",
        "com.apple.coregraphics.ArrowS",     # macOS 26 新增: 小尺寸箭头
        "com.apple.coregraphics.IBeamS",     # macOS 26 新增: 小尺寸 I 型

        # ===== com.apple.cursor.2..5 (4 个) =====
        "com.apple.cursor.2",   # Link
        "com.apple.cursor.3",   # Forbidden
        "com.apple.cursor.4",   # Busy
        "com.apple.cursor.5",   # Copy Drag
        # ⚠️ com.apple.cursor.6 故意空缺 (Mousecape cursorMap 没有 N=6)

        # ===== com.apple.cursor.7..16 (10 个) =====
        "com.apple.cursor.7",   # Crosshair
        "com.apple.cursor.8",   # Crosshair 2
        "com.apple.cursor.9",   # Camera 2
        "com.apple.cursor.10",  # Camera
        "com.apple.cursor.11",  # Closed (握紧手)
        "com.apple.cursor.12",  # Open (张开手)
        "com.apple.cursor.13",  # Pointing (手指指针)
        "com.apple.cursor.14",  # Counting Up
        "com.apple.cursor.15",  # Counting Down
        "com.apple.cursor.16",  # Counting Up/Down

        # ===== com.apple.cursor.17..26 (10 个) =====
        "com.apple.cursor.17",  # Resize W
        "com.apple.cursor.18",  # Resize E
        "com.apple.cursor.19",  # Resize W-E
        "com.apple.cursor.20",  # Cell XOR
        "com.apple.cursor.21",  # Resize N
        "com.apple.cursor.22",  # Resize S
        "com.apple.cursor.23",  # Resize N-S
        "com.apple.cursor.24",  # Ctx Menu
        "com.apple.cursor.25",  # Poof
        "com.apple.cursor.26",  # IBeam H.

        # ===== com.apple.cursor.27..38 (12 个, Window 系列) =====
        "com.apple.cursor.27",  # Window E
        "com.apple.cursor.28",  # Window E-W
        "com.apple.cursor.29",  # Window NE
        "com.apple.cursor.30",  # Window NE-SW
        "com.apple.cursor.31",  # Window N
        "com.apple.cursor.32",  # Window N-S
        "com.apple.cursor.33",  # Window NW
        "com.apple.cursor.34",  # Window NW-SE
        "com.apple.cursor.35",  # Window SE
        "com.apple.cursor.36",  # Window S
        "com.apple.cursor.37",  # Window SW
        "com.apple.cursor.38",  # Window W

        # ===== com.apple.cursor.39..43 (5 个) =====
        "com.apple.cursor.39",  # Resize Square
        "com.apple.cursor.40",  # Help
        "com.apple.cursor.41",  # Cell
        "com.apple.cursor.42",  # Zoom In
        "com.apple.cursor.43",  # Zoom Out
    }
    # cape 容量 = 集合大小 (9 coregraphics 经典 + 2 macOS 26 新增 + 41 cursor.N = 52)
    _ALL_MAC_CAPACITY = len(_ALL_MAC_IDENTIFIERS)

    def _find_spare_identifier(used: set, needed: set) -> str | None:
        """找一个未使用的 macOS identifier 作为 redistributed 的备用槽位

        策略 (按优先级):
          1. 优先选 Window 系列 (cursor.27~38), X11 主题永远不会直接提供这些
          2. 选不在 needed 中且未被 used 的 identifier
          3. ⚠️ 不抢 needed 中的 identifier (那是主 cursor 的"领地")
          4. 实在没有返回 None
        """
        WINDOW_AND_PRIVATE_PREFERRED = [
            "com.apple.cursor.27", "com.apple.cursor.28", "com.apple.cursor.29",
            "com.apple.cursor.31", "com.apple.cursor.32", "com.apple.cursor.33",
            "com.apple.cursor.35", "com.apple.cursor.36", "com.apple.cursor.37",
            "com.apple.cursor.38",
        ]
        for mac in WINDOW_AND_PRIVATE_PREFERRED:
            if mac not in used and mac not in needed:
                return mac
        for mac in sorted(_ALL_MAC_IDENTIFIERS):
            if mac not in used and mac not in needed:
                return mac
        return None

    # 跨 identifier fallback 表: 缺哪个 mac id → 复用哪个 mac id 的帧
    # 基于 macOS 自身默认行为 (System Preferences 找相邻 cursor 兜底)
    CROSS_FALLBACK = {
        "com.apple.coregraphics.Alias": "com.apple.cursor.2",   # Alias → Link
        "com.apple.cursor.12": "com.apple.cursor.11",          # Open → Closed (相同 grab 风格)
        "com.apple.cursor.15": "com.apple.coregraphics.Wait",   # Counting Down → Wait (都是动画)
        "com.apple.cursor.16": "com.apple.cursor.15",          # Counting Up/Down → Counting Down
        "com.apple.cursor.9": "com.apple.coregraphics.Alias",   # Camera 2 → Alias (罕见主题无此 cursor)
        "com.apple.cursor.14": "com.apple.cursor.15",          # Counting Up → Counting Down
        "com.apple.cursor.5": "com.apple.coregraphics.Copy",   # Copy Drag → Copy
        "com.apple.cursor.25": "com.apple.coregraphics.Wait",  # Poof → Wait (动画结尾效果)
    }

    # 先按 mac_name 分组, 找出每个 identifier 实际有效的 X11 帧
    frames_by_mac: dict[str, list[dict]] = defaultdict(list)
    for c in cursor_set:
        mac = c["mac_name"]
        x11 = c.get("x11_name", mac)
        if c.get("frames"):
            frames_by_mac[mac].append({"x11": x11, "frames": c["frames"]})

    seen_identifiers: set[str] = set()
    skipped_aliases: list[tuple[str, str]] = []
    fallback_used: list[tuple[str, str, str]] = []  # (src_x11_or_mac, target_x11, kind)
    redistributed: list[tuple[str, str, str]] = []  # (x11_name, from_mac, to_mac)

    # 同 identifier 内 X11 帧数据指纹分组 (用于判断要不要分到备用槽位)
    import hashlib

    def _frame_fingerprint(frames_list) -> str:
        h = hashlib.md5()
        for f in sorted(frames_list, key=lambda f: (f.width, f.height, f.frame_index)):
            h.update(f.image_path.encode())
            h.update(f"{f.width},{f.height},{f.frame_index}".encode())
        return h.hexdigest()

    # X11 名 → 备用 mac identifier 映射 (按语义相关性分配)
    SPARE_IDENTIFIER_MAP = {
        "arrow": "com.apple.cursor.42",
        "top_left_arrow": "com.apple.cursor.43",
        "right_ptr": "com.apple.cursor.18",
        "top_right_arrow": "com.apple.cursor.18",
        "op_left_arrow": "com.apple.cursor.17",
        "default": "com.apple.cursor.42",
        "text": "com.apple.cursor.26",
        "horizontal-text": "com.apple.cursor.26",
        "@xterm": "com.apple.cursor.26",
        "ib": "com.apple.cursor.26",
        "IBeamXOR": "com.apple.cursor.26",
        "handwriting": "com.apple.cursor.26",
        "pencil": "com.apple.cursor.8",
        "fleur": "com.apple.cursor.39",
        "all-scroll": "com.apple.cursor.39",
        "size_all": "com.apple.cursor.39",
        "scroll-all": "com.apple.cursor.39",
        "pointer-move": "com.apple.cursor.39",
        "pointer_move": "com.apple.cursor.39",
        "sizing": "com.apple.cursor.39",
        "move": "com.apple.cursor.39",
        "watch": "com.apple.cursor.4",
        "left_ptr_watch": "com.apple.cursor.4",
        "wait": "com.apple.cursor.4",
        "clock": "com.apple.cursor.4",
        "dnd-ask": "com.apple.cursor.9",
        "color-picker": "com.apple.cursor.8",
        "dnd-copy": "com.apple.cursor.31",
        "context-menu": "com.apple.cursor.29",
        "plus": "com.apple.cursor.39",
    }

    # X11 cursor 优先级 (同一 mac identifier 内, 优先级最高的占主槽位)
    X11_PRIORITY = {
        "com.apple.coregraphics.Arrow": ["left_ptr", "arrow", "default", "top_left_arrow", "right_ptr", "top_right_arrow", "op_left_arrow"],
        "com.apple.coregraphics.IBeam": ["xterm", "ibeam", "text", "horizontal-text", "IBeamXOR", "@xterm", "ib", "handwriting"],
        "com.apple.coregraphics.Alias": ["alias"],
        "com.apple.coregraphics.Copy": ["copy"],
        "com.apple.coregraphics.Move": ["move", "fleur", "all-scroll", "size_all", "scroll-all", "pointer-move", "pointer_move", "sizing"],
        "com.apple.coregraphics.Wait": ["watch", "wait", "left_ptr_watch", "clock"],
        "com.apple.cursor.2": ["link", "dnd-link"],
        "com.apple.cursor.3": ["forbidden", "not-allowed", "crossed_circle", "crossed-circle", "circle", "no-drop", "dnd_no_drop", "dnd-no-drop", "dnd-ask", "pirate", "kill"],
        "com.apple.cursor.5": ["dnd-copy"],
        "com.apple.cursor.7": ["crosshair", "cross", "tcross", "center_ptr", "centre_ptr", "cross_reverse", "diamond_cross", "plus", "color-picker", "pencil", "draft", "draft_large", "draft_small", "center_main"],
        "com.apple.cursor.11": ["grabbing", "closedhand", "dnd-move", "dnd-none", "dragging", "HandSqueezed"],
        "com.apple.cursor.12": ["grab", "openhand", "dnd-grab", "HandGrab"],
        "com.apple.cursor.13": ["hand2", "pointer", "pointing_hand", "hand1", "hand", "pointer2", "button"],
        "com.apple.cursor.15": ["progress"],
        "com.apple.cursor.16": ["half-busy", "half_busy"],
        "com.apple.cursor.17": ["w-resize", "left_side", "left-side", "left_tee", "sb_left_arrow", "left-arrow", "left_arrow"],
        "com.apple.cursor.18": ["e-resize", "right_side", "right-side", "right_tee", "sb_right_arrow", "right-arrow", "right_arrow"],
        "com.apple.cursor.19": ["sb_h_double_arrow", "size_hor", "size-hor", "ew-resize", "h_double_arrow", "split_h", "h_double", "double-arrow", "double_arrow", "HDoubleArrow", "col-resize"],
        "com.apple.cursor.21": ["n-resize", "top_side", "top-side", "top_tee", "sb_up_arrow", "up-arrow", "up_arrow", "based_arrow_up", "base_arrow_up"],
        "com.apple.cursor.22": ["s-resize", "bottom_side", "bottom-side", "bottom_tee", "sb_down_arrow", "down-arrow", "down_arrow", "based_arrow_down", "base_arrow_down"],
        "com.apple.cursor.23": ["sb_v_double_arrow", "size_ver", "size-ver", "ns-resize", "v_double_arrow", "split_v", "v_double", "VDoubleArrow", "row-resize"],
        "com.apple.cursor.24": ["context-menu"],
        "com.apple.cursor.26": ["vertical-text", "text_vertical"],
        "com.apple.cursor.30": ["fd_double_arrow", "size_bdiag", "size-bdiag", "nesw-resize", "ne-resize", "se-resize", "bottom_left_corner", "top_right_corner", "ur_angle", "ll_angle", "SizeNESW_Down"],
        "com.apple.cursor.34": ["bd_double_arrow", "size_fdiag", "size-fdiag", "nwse-resize", "nw-resize", "sw-resize", "top_left_corner", "bottom_right_corner", "ul_angle", "lr_angle"],
        "com.apple.cursor.40": ["question_arrow", "question-arrow", "help", "whats_this", "left_ptr_help"],
        "com.apple.cursor.41": ["cell", "dotbox", "dot_box", "dot_box_mask", "icon", "target", "draped_box", "dot", "person"],
        "com.apple.cursor.42": ["zoom-in", "zoom_in", "zoomIn"],
        "com.apple.cursor.43": ["zoom-out", "zoom_out", "zoomOut"],
    }


    # 先收集所有"应有"的 mac identifier (从 cursor_set 的 mac_name + cross fallback 反推)
    all_needed_macs = set()
    for c in cursor_set:
        all_needed_macs.add(c["mac_name"])
    for target_mac, src_mac in CROSS_FALLBACK.items():
        all_needed_macs.add(target_mac)

    # 处理主 cursor_set 中的 cursor
    for c in cursor_set:
        x11_name = c.get("x11_name", c["mac_name"])
        identifier = c["mac_name"]
        frames = c.get("frames", [])

        if identifier in seen_identifiers:
            # 帧数据不同 → 尝试分配到备用 identifier (redistributed)
            if frames:
                current_fp = _frame_fingerprint(frames)
                # 检查这个 identifier 下, 已存在的帧指纹 (按优先级最高的)
                priority_list = X11_PRIORITY.get(identifier, [])
                best_fp = None
                for pname in priority_list:
                    for src in frames_by_mac.get(identifier, []):
                        if src["x11"] == pname and src["frames"]:
                            best_fp = _frame_fingerprint(src["frames"])
                            break
                    if best_fp:
                        break
                if best_fp is None:
                    for src in frames_by_mac.get(identifier, []):
                        if src["frames"]:
                            best_fp = _frame_fingerprint(src["frames"])
                            break
                # 帧数据不同 → 尝试备用槽位
                if best_fp and current_fp != best_fp:
                    spare_mac = SPARE_IDENTIFIER_MAP.get(x11_name)
                    if spare_mac and spare_mac not in seen_identifiers:
                        identifier = spare_mac
                        redistributed.append((x11_name, c["mac_name"], spare_mac))
                    else:
                        auto_spare = _find_spare_identifier(seen_identifiers, all_needed_macs)
                        if auto_spare:
                            identifier = auto_spare
                            redistributed.append((x11_name, c["mac_name"], auto_spare))
                        else:
                            skipped_aliases.append((x11_name, c["mac_name"]))
                            continue
                else:
                    skipped_aliases.append((x11_name, c["mac_name"]))
                    continue
            else:
                skipped_aliases.append((x11_name, c["mac_name"]))
                continue
        seen_identifiers.add(identifier)

        # Fallback a): 同 identifier 内找其他 X11 帧
        if not frames and identifier in frames_by_mac:
            for src in frames_by_mac[identifier]:
                if src["x11"] != x11_name and src["frames"]:
                    frames = src["frames"]
                    fallback_used.append((src["x11"], x11_name, "sibling"))
                    break
        if not frames:
            continue
        try:
            points_w, points_h = _select_base_size(frames, target=target_size)
            representations = _build_representations(frames, points_w, points_h)
            if not representations:
                continue
            hot_x, hot_y = _hotspot_for_points(frames, points_w, points_h)
            cursor_dict = {
                "FrameCount": int(_frame_count(frames)),
                "FrameDuration": float(_frame_duration_seconds(frames)),
                "HotSpotX": float(hot_x),
                "HotSpotY": float(hot_y),
                "PointsWide": float(points_w),
                "PointsHigh": float(points_h),
                "Representations": representations,
            }
            cape["Cursors"][identifier] = cursor_dict
        except Exception as e:
            print(f"  [skip] {identifier}: {e}")
            continue

    # Fallback b): 处理 cross-fallback 的 mac identifier (主题里完全没有)
    for target_mac, src_mac in CROSS_FALLBACK.items():
        if target_mac in seen_identifiers:
            continue  # 已经有真实图了
        if src_mac not in cape["Cursors"]:
            continue  # 源 identifier 也没有
        # 复用 src_mac 的 cursor dict, 但改 identifier
        src_dict = cape["Cursors"][src_mac]
        cape["Cursors"][target_mac] = dict(src_dict)  # 浅拷贝
        fallback_used.append((src_mac, target_mac, "cross"))
        seen_identifiers.add(target_mac)

    if redistributed:
        print(f"  [info] redistributed {len(redistributed)} X11 cursor(s) to spare identifiers (帧数据不同, 避免丢失):")
        # 按目标 identifier 分组显示
        grouped_to: dict[str, list[tuple[str, str]]] = {}
        for x11, from_mac, to_mac in redistributed:
            grouped_to.setdefault(to_mac, []).append((x11, from_mac))
        for to_mac in sorted(grouped_to):
            items = grouped_to[to_mac]
            x11s = ', '.join(x for x, _ in items[:5])
            more = '' if len(items) <= 5 else f' (+{len(items) - 5} more)'
            from_macs = ', '.join(sorted(set(f for _, f in items)))
            print(f"    {to_mac}: [{x11s}{more}]  ← from {from_macs}")

    if skipped_aliases:
        grouped: dict[str, list[str]] = defaultdict(list)
        for x11, mac in skipped_aliases:
            grouped[mac].append(x11)
        print(f"  [info] merged {len(skipped_aliases)} X11 alias(es) into existing mac identifiers:")
        for mac, names in sorted(grouped.items()):
            sample = sorted(set(names))[:5]
            more = '' if len(names) <= 5 else f' (+{len(names) - 5} more)'
            print(f"    {mac}: {', '.join(sample)}{more}")

    if fallback_used:
        siblings = [f for f in fallback_used if f[2] == "sibling"]
        cross = [f for f in fallback_used if f[2] == "cross"]
        if siblings:
            print(f"  [info] reused frames from siblings for {len(siblings)} zero-byte X11 cursor file(s):")
            for src, target, _ in siblings:
                print(f"    {target} (empty) ← reused from {src}")
        if cross:
            print(f"  [info] cross-identifier fallback for {len(cross)} mac identifier(s) (主题完全没提供):")
            for src, target, _ in cross:
                print(f"    {target} ← reused frames from {src}")

    out = out_dir / f"{theme_name}.cape"
    # ⚠️ 必须是 XML plist -- Mousecape 用 NSDictionary dictionaryWithContentsOfURL:
    # 读, 这个 API 不支持 binary plist, 改 binary 整个 cape 直接返回 nil
    with open(out, "wb") as f:
        plistlib.dump(cape, f, fmt=plistlib.FMT_XML)

    # Self-validation: 模拟 Mousecape 解析整条路径, 不通过就报错
    if self_validate:
        validator = CapeValidator(out)
        ok = validator.validate()
        print(validator.report())
        if not ok:
            raise RuntimeError(
                f"Cape validation failed ({len(validator.errors)} error(s)). "
                f"Mousecape will refuse to import this file."
            )

    # ===== 最终摘要 =====
    # 让用户清楚看到 cape 的实际状况: 输入 X11 cursor 数、槽位占用、合并/重定向明细
    total_x11_in = len(cursor_set)
    total_in_cape = len(cape["Cursors"])
    total_redistributed = len(redistributed)
    total_merged = len(skipped_aliases)
    total_cross = len([f for f in fallback_used if f[2] == "cross"])
    # 主 cursor 槽位占用 (= cape slots - 备用分配 - cross 复制)
    main_uses_x11 = total_in_cape - total_redistributed - total_cross
    # X11 cursor 已处理总数 = 主槽位 + 重定向 + 合并
    x11_accounted = main_uses_x11 + total_redistributed + total_merged
    print()
    print(f"  ====== Summary ======")
    print(f"  CapeName             : {cape.get('CapeName', theme_name)}")
    print(f"  CapeFile             : {out_dir / (theme_name + '.cape')}")
    print(f"  X11 cursor input     : {total_x11_in}")
    print(f"  mac identifiers used : {total_in_cape} / {_ALL_MAC_CAPACITY}  (硬上限, 来自 macos_full.md)")
    print(f"    - main (主 cursor, X11 直接映射):    {main_uses_x11}")
    print(f"    - redistributed (重定向到备用槽位):  {total_redistributed}")
    print(f"    - cross-fallback (复制其他 identifier): {total_cross}")
    print()
    print(f"  X11 cursors 处理明细:")
    print(f"    - 用自己的帧保留到独立槽位 (鼠标实际会用这些): {main_uses_x11 + total_redistributed}")
    print(f"    - merged (别名复用主 cursor 帧, 数据相同):     {total_merged}")
    print()
    print(f"  说明:")
    print(f"    main = 主题里某个 mac identifier 的'主' X11 cursor (优先级最高)")
    print(f"    redistributed = 帧数据不同但同 mac identifier 的其他 X11 cursor")
    print(f"                  被分配到备用槽位 (cursor.27~38 等 Window 系列)")
    print(f"    merged = 帧数据完全相同 (symlink alias / 真正的字节相同文件)")
    print(f"            → 复用主 cursor 帧, 不丢失语义 (Mousecape 鼠标实际外观不变)")
    print(f"    cross-fallback = 主题完全没提供, 复用相邻 identifier 帧 (兜底)")
    if x11_accounted == total_x11_in:
        print()
        print(f"  [OK] 所有 {total_x11_in} 个 X11 cursor 都已处理 (无遗漏, 无丢失)")
    else:
        diff = total_x11_in - x11_accounted
        print()
        print(f"  [WARN] 数量不平: 输入 {total_x11_in} vs 已处理 {x11_accounted} (差 {diff})")

    return out
