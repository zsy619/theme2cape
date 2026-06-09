# xcursor 名称 → Mousecape cursor identifier 映射
#
# identifier 是 macOS CGS / CoreCursor 内部使用的反向 DNS 字符串 (如
# "com.apple.coregraphics.Arrow"),不是给人看的"名称"。Mousecape cape 文件
# 的 Cursors 字典必须用 identifier 作为 key,系统加载 cape 时按 identifier
# 找到对应替换光标。
#
# 完整 identifier ↔ 名称对照表见 Mousecape 源码 MCDefs.m 的 cursorMap():
#   https://github.com/sdmj76-team/Mousecape-swiftUI/blob/main/Mousecape/mousecloak/MCDefs.m
#
# 单一真相源: 任何映射目标都必须来自源码 cursorNameMap (50 个 identifier)
from core.mousecape_defs import CURSOR_MAP as _CURSOR_MAP_FOR_ASSERT

MACOS_CURSOR_MAP = {
    # ===== BASIC POINTER =====
    "arrow": "com.apple.coregraphics.Arrow",
    "left_ptr": "com.apple.coregraphics.Arrow",
    "default": "com.apple.coregraphics.Arrow",
    "top_left_arrow": "com.apple.coregraphics.Arrow",
    # ===== TEXT =====
    "ibeam": "com.apple.coregraphics.IBeam",
    "xterm": "com.apple.coregraphics.IBeam",
    "text": "com.apple.coregraphics.IBeam",
    "vertical-text": "com.apple.cursor.26",  # IBeam H. (竖版文本光标)
    "text_vertical": "com.apple.cursor.26",
    "IBeamXOR": "com.apple.coregraphics.IBeam",  # XOR反色版本也用IBeam图标
    # ===== POINTER / LINK =====
    "hand2": "com.apple.cursor.13",  # Pointing
    "pointer": "com.apple.cursor.13",  # Pointing
    "hand1": "com.apple.cursor.13",
    "hand": "com.apple.cursor.13",
    "pointing_hand": "com.apple.cursor.13",
    "link": "com.apple.cursor.2",  # Link
    # ===== COPY / DRAG =====
    "copy": "com.apple.coregraphics.Copy",
    "dnd-copy": "com.apple.cursor.5",  # Copy Drag
    "dnd-move": "com.apple.cursor.11",  # dnd-move -> grabbing (拖拽中)
    "dnd-link": "com.apple.cursor.2",  # Link
    "dnd-none": "com.apple.cursor.11",  # dnd-none -> grabbing (Bibata 中是这样)
    "dnd_no_drop": "com.apple.cursor.3",  # 禁止放置
    "dnd-ask": "com.apple.cursor.3",
    "not-allowed": "com.apple.cursor.3",  # Forbidden
    "forbidden": "com.apple.cursor.3",
    "circle": "com.apple.cursor.3",  # 透明圆(系统视为 forbidden 类)
    "crossed_circle": "com.apple.cursor.3",
    "no-drop": "com.apple.cursor.3",  # no-drop -> dnd_no_drop
    # ===== ALIAS =====
    "alias": "com.apple.coregraphics.Alias",
    # ===== MOVE / RESIZE =====
    "move": "com.apple.coregraphics.Move",
    "fleur": "com.apple.coregraphics.Move",
    "all-scroll": "com.apple.coregraphics.Move",  # 全方向移动
    "pointer-move": "com.apple.coregraphics.Move",  # 拖拽移动
    "size_all": "com.apple.coregraphics.Move",
    "sb_v_double_arrow": "com.apple.cursor.23",  # Resize N-S
    "sb_h_double_arrow": "com.apple.cursor.19",  # Resize W-E
    "top_left_corner": "com.apple.cursor.34",  # Window NW-SE
    "top_right_corner": "com.apple.cursor.30",  # Window NE-SW
    "bottom_left_corner": "com.apple.cursor.30",
    "bottom_right_corner": "com.apple.cursor.34",
    "left_side": "com.apple.cursor.17",  # Resize W
    "right_side": "com.apple.cursor.18",  # Resize E
    "top_side": "com.apple.cursor.21",  # Resize N
    "bottom_side": "com.apple.cursor.22",  # Resize S
    "top_tee": "com.apple.cursor.21",
    "bottom_tee": "com.apple.cursor.22",
    "left_tee": "com.apple.cursor.17",
    "right_tee": "com.apple.cursor.18",
    "ul_angle": "com.apple.cursor.34",
    "ur_angle": "com.apple.cursor.30",
    "ll_angle": "com.apple.cursor.30",
    "lr_angle": "com.apple.cursor.34",
    "sb_up_arrow": "com.apple.cursor.21",
    "sb_down_arrow": "com.apple.cursor.22",
    "sb_left_arrow": "com.apple.cursor.17",
    "sb_right_arrow": "com.apple.cursor.18",
    # 对角线双向箭头
    "bd_double_arrow": "com.apple.cursor.34",  # NW-SE 对角线 (bottom-right/top-left)
    "fd_double_arrow": "com.apple.cursor.30",  # NE-SW 对角线 (top-right/bottom-left)
    "size_fdiag": "com.apple.cursor.34",  # 对角线调整别名
    "size_bdiag": "com.apple.cursor.30",
    "nwse-resize": "com.apple.cursor.34",  # NW-SE resize
    "nesw-resize": "com.apple.cursor.30",  # NE-SW resize (假设)
    # 方向调整别名
    "col-resize": "com.apple.cursor.19",  # 列调整 (水平)
    "row-resize": "com.apple.cursor.23",  # 行调整 (垂直)
    "ew-resize": "com.apple.cursor.19",  # 东-西调整
    "ns-resize": "com.apple.cursor.23",  # 北-南调整
    "split_h": "com.apple.cursor.19",  # 水平分割
    "split_v": "com.apple.cursor.23",  # 垂直分割
    # 单方向调整别名
    "e-resize": "com.apple.cursor.18",  # 东
    "w-resize": "com.apple.cursor.17",  # 西
    "n-resize": "com.apple.cursor.21",  # 北
    "s-resize": "com.apple.cursor.22",  # 南
    # ===== CROSSHAIR / PRECISION =====
    "cross": "com.apple.cursor.7",  # Crosshair
    "crosshair": "com.apple.cursor.7",
    "tcross": "com.apple.cursor.7",
    "plus": "com.apple.cursor.7",
    "center_ptr": "com.apple.cursor.7",
    "draft": "com.apple.cursor.7",
    "pencil": "com.apple.cursor.7",
    "dotbox": "com.apple.cursor.41",  # Cell
    "dot_box": "com.apple.cursor.41",
    "cell": "com.apple.cursor.41",
    "icon": "com.apple.cursor.41",  # icon -> dotbox
    "dot_box_mask": "com.apple.cursor.41",  # dot_box_mask -> dotbox
    "draped_box": "com.apple.cursor.41",  # draped_box -> dotbox
    "target": "com.apple.cursor.41",  # target -> dotbox
    "color-picker": "com.apple.cursor.7",  # color-picker -> tcross
    "diamond_cross": "com.apple.cursor.7",  # diamond_cross -> cross
    "cross_reverse": "com.apple.cursor.7",  # cross_reverse -> cross
    # ===== HELP =====
    "help": "com.apple.cursor.40",
    "question_arrow": "com.apple.cursor.40",
    "whats_this": "com.apple.cursor.40",
    # ===== BUSY / WAIT =====
    "watch": "com.apple.coregraphics.Wait",
    "wait": "com.apple.coregraphics.Wait",
    "left_ptr_watch": "com.apple.coregraphics.Wait",
    "progress": "com.apple.cursor.15",  # Counting Down
    "half-busy": "com.apple.cursor.16",  # Counting Up/Down
    # ===== GRAB =====
    "grab": "com.apple.cursor.12",  # Open
    "grabbing": "com.apple.cursor.11",  # Closed
    "openhand": "com.apple.cursor.12",
    "closedhand": "com.apple.cursor.11",
    # ===== ZOOM =====
    "zoom-in": "com.apple.cursor.42",  # Zoom In
    "zoom-out": "com.apple.cursor.43",  # Zoom Out
    # ===== CONTEXT MENU =====
    "context-menu": "com.apple.cursor.24",  # Ctx Menu
    "right_ptr": "com.apple.cursor.24",
    # ===== DIRECTION ARROWS (Vimix / BreezeX 等 KDE 主题常见) =====
    "up-arrow": "com.apple.cursor.21",  # 北向箭头
    "down-arrow": "com.apple.cursor.22",  # 南向箭头
    "left-arrow": "com.apple.cursor.17",  # 西向箭头
    "right-arrow": "com.apple.cursor.18",  # 东向箭头
    "size_hor": "com.apple.cursor.19",  # 水平双向 (== sb_h_double_arrow)
    "size_ver": "com.apple.cursor.23",  # 垂直双向 (== sb_v_double_arrow)
    "h_double_arrow": "com.apple.cursor.19",  # 水平双向别名
    "v_double_arrow": "com.apple.cursor.23",  # 垂直双向别名
    "h_double": "com.apple.cursor.19",
    "v_double": "com.apple.cursor.23",
    "double-arrow": "com.apple.cursor.19",  # 默认到水平
    # 角向 8 方向 resize (CSS cursor names)
    "ne-resize": "com.apple.cursor.30",  # 东北角 -> NE-SW 对角线
    "nw-resize": "com.apple.cursor.34",  # 西北角 -> NW-SE 对角线
    "se-resize": "com.apple.cursor.30",  # 东南角 -> NE-SW 对角线
    "sw-resize": "com.apple.cursor.34",  # 西南角 -> NW-SE 对角线
    "ne_sizegrip": "com.apple.cursor.30",
    "nw_sizegrip": "com.apple.cursor.34",
    "se_sizegrip": "com.apple.cursor.30",
    "sw_sizegrip": "com.apple.cursor.34",
    # ===== Drag & Drop 扩展 =====
    "dnd-no-drop": "com.apple.cursor.3",  # Vimix: 禁止放置 (与 dnd_no_drop 同义)
    # ===== 杂项 =====
    "pirate": "com.apple.cursor.3",  # 海盗旗 -> forbidden
    "left_ptr_help": "com.apple.cursor.40",  # 箭头+问号 -> help
    # ===== POOF / SPINNING =====
    "poof": "com.apple.cursor.25",
    # ===== 跳过(系统默认/X11 内部光标,无对应 macOS identifier)=====
    "X_cursor": "com.apple.cursor.7",  # X 形光标 -> Crosshair
    "wayland-cursor": None,
    "x-cursor": None,
    # ===== Comix / BibataExtra / Layan 等主题补全 =====
    # 源: out/_extracted_*/<theme>/cursors/decoded 目录扫描结果
    # 这些 cursor 名称是 X11 主题中常见的别名, 没在 MACOS_CURSOR_MAP 上半部分覆盖
    # 全部映射目标都是源码 cursorNameMap (50 个) 内的 identifier
    # ----- 通用别名 (≥12 个主题) -----
    "double_arrow": "com.apple.cursor.19",  # 双向箭头 (默认到水平) = sb_h_double_arrow
    "draft_large": "com.apple.cursor.7",  # 大十字草稿 = crosshair
    "draft_small": "com.apple.cursor.7",  # 小十字草稿 = crosshair
    "up_arrow": "com.apple.cursor.21",  # 上箭头 = sb_up_arrow
    "center-main": "com.apple.cursor.7",  # 中心十字 (CSS) = center_ptr
    "clock": "com.apple.coregraphics.Wait",  # 时钟 = wait (Busy 状态)
    "dot": "com.apple.cursor.41",  # 点框 = dotbox (Cell)
    "dragging": "com.apple.cursor.11",  # 拖拽中 = grabbing
    "horizontal-text": "com.apple.coregraphics.IBeam",  # 水平文本 = IBeam
    "kill": "com.apple.cursor.3",  # 禁止 = forbidden
    "left-main": "com.apple.coregraphics.Arrow",  # 左侧主箭头 = arrow
    "pointer2": "com.apple.cursor.13",  # 指针 2 = hand2
    "right-main": "com.apple.coregraphics.Arrow",  # 右侧主箭头 = arrow
    "top_right_arrow": "com.apple.cursor.30",  # 右上箭头 = ne-resize
    "zoom_in": "com.apple.cursor.42",  # 放大 (无下划线版) = zoom-in
    "zoom_out": "com.apple.cursor.43",  # 缩小 (无下划线版) = zoom-out
    # ----- 8-11 主题 (中频次) -----
    "size-hor": "com.apple.cursor.19",  # 水平调整 (CSS) = ew-resize
    "size-ver": "com.apple.cursor.23",  # 垂直调整 (CSS) = ns-resize
    "center_main": "com.apple.cursor.7",  # 中心十字别名 = crosshair
    "hor-resize": "com.apple.cursor.19",  # 水平调整 = ew-resize
    "ver-resize": "com.apple.cursor.23",  # 垂直调整 = ns-resize
    "scan": "com.apple.cursor.23",  # 扫描 (X11 sb_v_double_arrow 别名) = sb_v_double_arrow
    # ----- 1-2 主题 (低频次) -----
    "base_arrow_down": "com.apple.cursor.22",  # 基本下箭头 (X11 base) = sb_down_arrow
    "base_arrow_up": "com.apple.cursor.21",  # 基本上箭头 (X11 base) = sb_up_arrow
    "based_arrow_down": "com.apple.cursor.22",  # X11 base 双下划线别名
    "based_arrow_up": "com.apple.cursor.21",  # X11 base 双下划线别名
    "centre_ptr": "com.apple.cursor.7",  # 中心指针 (英式拼写) = center_ptr
    "left_ptr_move": "com.apple.cursor.11",  # 左指针移动 (罕见) = grabbing
    "sizenesw_down": "com.apple.cursor.30",  # NE-SW 调整 = ne-resize
    "x_cursor": "com.apple.cursor.7",  # X 形光标 (小写) = X_cursor -> Crosshair
    "X-cursor": "com.apple.cursor.7",  # X 形光标 (大写连字符) = X_cursor -> Crosshair
    # ----- X11 1.20+ 32 位哈希别名已全部移除 -----
    # 原因: 32 位 hex 哈希名不稳定, 同一视觉 cursor 在不同主题包里哈希值不同
    # 且 X11 alias 机制 (X11 1.20+ 引入了 `XcursorFileHash` 算法) 在绝大多数
    # 现代 X11 主题里这些哈希名实际是 symlink 指向标准 cursor, 会被
    # normalizer 通过真实文件读取并解析到对应标准名. **不应** 在 MACOS_CURSOR_MAP
    # 中硬编码哈希名. 以后没有特别说明也不允许出现任何哈希名映射.
}


# ===== 启动时自检: 确保所有 cursor 名称的映射目标都在源码 cursorNameMap 内 =====
# 任何遗漏或漂移都会导致 X11 cursor 数据被丢弃, 生成的 cape 残缺
_MISSING_TARGETS = {
    src: tgt
    for src, tgt in MACOS_CURSOR_MAP.items()
    if tgt is not None and tgt not in _CURSOR_MAP_FOR_ASSERT
}
assert not _MISSING_TARGETS, (
    f"MACOS_CURSOR_MAP 中 {len(_MISSING_TARGETS)} 个映射目标不在源码 cursorNameMap 中:\n"
    + "\n".join(f"  {src} -> {tgt}" for src, tgt in _MISSING_TARGETS.items())
)

# ===== 启动时自检: 禁止任何 X11 1.20+ 32 位 hex 哈希名映射 =====
# 32 位 hex 哈希名不稳定, 同一视觉 cursor 在不同主题包里哈希值不同, 不应硬编码.
# 这些哈希名 cursor 在 X11 主题包内是 symlink 指向标准 cursor, 应由 normalizer
# 通过解析真实文件/symlink 来找到对应标准名, 而不是在 MACOS_CURSOR_MAP 中硬编码.
import re

_HASH_PATTERN = re.compile(
    r"^[0-9a-f]{16,32}$" r"|^[0-9a-f]{8}_[0-9a-f]{8}_[0-9a-f]{8}_[0-9a-f]{8}$"
)
_HASH_KEYS = [k for k in MACOS_CURSOR_MAP if _HASH_PATTERN.match(k)]
assert not _HASH_KEYS, (
    f"MACOS_CURSOR_MAP 中存在 {len(_HASH_KEYS)} 个 32 位 hex 哈希名映射 (用户明确要求移除):\n"
    + "\n".join(f"  {k} -> {MACOS_CURSOR_MAP[k]}" for k in _HASH_KEYS)
    + "\n\n提示: 哈希 cursor 在 X11 主题包内是 symlink, 应由 normalizer 解析标准名, "
    "而不是在 MACOS_CURSOR_MAP 中硬编码."
)
