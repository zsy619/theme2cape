# xcursor 名称 → Mousecape cursor identifier 映射
#
# identifier 是 macOS CGS / CoreCursor 内部使用的反向 DNS 字符串 (如
# "com.apple.coregraphics.Arrow"),不是给人看的"名称"。Mousecape cape 文件
# 的 Cursors 字典必须用 identifier 作为 key,系统加载 cape 时按 identifier
# 找到对应替换光标。
#
# 完整 identifier ↔ 名称对照表见 Mousecape 源码 MCDefs.m 的 cursorMap():
#   https://github.com/alexzielenski/Mousecape/blob/master/Mousecape/mousecloak/MCDefs.m
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
    "e29285e634086352946a0e7090d73106": "com.apple.cursor.13",  # X11 编码名 -> hand2
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
    "sb_h_double_arrow": "com.apple.cursor.19",  # 已在 RESIZE 段,这里重复占位无副作用
    "sb_v_double_arrow": "com.apple.cursor.23",
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
    "dnd-ask": "com.apple.cursor.3",  # 已在 COPY 段
    # ===== 杂项 =====
    "pirate": "com.apple.cursor.3",  # 海盗旗 -> forbidden
    "circle": "com.apple.cursor.3",  # 已在 COPY 段
    "left_ptr_help": "com.apple.cursor.40",  # 箭头+问号 -> help
    # ===== POOF / SPINNING =====
    "poof": "com.apple.cursor.25",
    "target": "com.apple.cursor.9",  # Camera 2 (target 已存在,这里给 camera)
    # ===== 32位哈希名(X11 cursor encoding) -> 对应 macOS identifier =====
    # Vimix 主题里有大量 32 位哈希名, 这是 X11 在 1.20+ 引入的 alias 机制
    # 实际指向已通过真实文件 / symlink 表建立, 我们直接用常用编码 → 标准名映射
    "00000000000000020006000e7e9ffc3f": "com.apple.cursor.15",  # progress
    "00008160000006810000408080010102": "com.apple.cursor.23",  # size_ver
    "03b6e0fcb3499374a867c041f52298f0": "com.apple.cursor.3",  # circle
    "08e8e1c95fe2fc01f976f1e063a24ccd": "com.apple.cursor.15",  # progress
    "1081e37283d90000800003c07f3ef6bf": "com.apple.cursor.2",  # copy drag variant
    "3085a0e285430894940527032f8b26df": "com.apple.coregraphics.Alias",
    "3ecb610c1bf2410f44200f48c40d3599": "com.apple.cursor.15",  # progress
    "4498f0e0c1937ffe01fd06f973665830": "com.apple.cursor.11",  # dnd-move
    "5c6cd98b3f3ebcb1f9c7f1c204630408": "com.apple.cursor.40",  # help
    "6407b0e94181790501fd1e167b474872": "com.apple.cursor.2",  # copy drag
    "640fb0e74195791501fd1ed57b41487f": "com.apple.coregraphics.Alias",
    "9081237383d90e509aa00f00170e968f": "com.apple.cursor.11",  # dnd-move
    "9d800788f1b08800ae810202380a0822": "com.apple.cursor.13",  # pointer
    "a2a266d0498c3104214a47bd64ab0fc8": "com.apple.coregraphics.Alias",
    "b66166c04f8c3109214a4fbd64a50fc8": "com.apple.cursor.2",  # copy drag
    "d9ce0ab605698f320427677b458ad60b": "com.apple.cursor.40",  # help
    "fcf21c00b30f7e3f83fe0dfd12e71cff": "com.apple.cursor.11",  # dnd-move
    # ===== 跳过(系统默认/X11 内部光标,无对应 macOS identifier)=====
    "X_cursor": None,
    "wayland-cursor": None,
    "x-cursor": None,
}
