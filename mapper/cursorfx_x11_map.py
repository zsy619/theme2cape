"""
Stardock CursorFX section name → X11 cursor alias 映射.

来源:
  https://github.com/ewindisch/sd2xc/blob/master/sd2xc.pl  的 $filemap hash
  (Stardock CursorFX 官方对应的 X11 cursor 命名约定)

设计:
  - 一个 CursorFX section (如 [Arrow]) 通常对应**多个** X11 cursor alias
    (left_ptr, X_cursor, right_ptr). 同一份 PNG 数据可被不同 X11 cursor
    状态复用.
  - 我们为每个 alias 生成一个独立 Cursor 对象,共享同一组 frames.
    这样下游 `core/normalizer.py` 用 `MACOS_CURSOR_MAP[alias]` 即可
    映射到正确的 macOS identifier.

未知 section 处理:
  `core/cursorfx_reader.read_cursorfx_theme()` 走
  `CURSORFX_SECTION_TO_X11.get(sec_name, [sec_name])` fallback,
  即未在表中登记的 section 会被原名当成 X11 cursor 名,留给 normalizer
  决定是否能映射. 这给未来 Stardock 引入新 section 留了兼容口子.
"""

# 官方标准 section (摘自 sd2xc.pl 的 $filemap)
CURSORFX_SECTION_TO_X11: dict[str, list[str]] = {
    # Arrow: 普通指针 (Stardock 习惯拆成 3 个 X11 alias)
    "Arrow": ["left_ptr", "X_cursor", "right_ptr"],
    # Cross: 十字光标
    "Cross": ["tcross", "cross"],
    # Hand: 链接/手指
    "Hand": ["hand1", "hand2", "pointer"],
    # IBeam: 文本光标
    "IBeam": ["xterm"],
    # UpArrow: 移动光标 (不太常用)
    "UpArrow": ["center_ptr"],
    # SizeNWSE: 斜向调整 (左上/右下)
    "SizeNWSE": ["bottom_right_corner", "top_left_corner"],
    # SizeNESW: 斜向调整 (右上/左下)
    "SizeNESW": ["bottom_left_corner", "top_right_corner"],
    # SizeWE: 水平调整
    "SizeWE": ["sb_h_double_arrow", "left_side", "right_side"],
    # SizeNS: 垂直调整
    "SizeNS": ["double_arrow", "bottom_side", "top_side"],
    # Help: 帮助/问号
    "Help": ["question_arrow", "help"],
    # Handwriting: 手写/钢笔
    "Handwriting": ["pencil"],
    # AppStarting: 程序启动中 (指针+沙漏)
    "AppStarting": ["left_ptr_watch"],
    # SizeAll: 全方向移动
    "SizeAll": ["fleur"],
    # Wait: 等待/沙漏
    "Wait": ["watch"],
    # NO: 禁止/不可用
    "NO": ["not-allowed", "forbidden"],
}


# ---- 辅助函数 ----

def expand_section_to_x11_names(section_name: str) -> list[str]:
    """
    把 CursorFX section 名展开成 X11 cursor alias 列表.

    未在 CURSORFX_SECTION_TO_X11 中的 section → 返回 [section_name] (原名).
    让 normalizer 自行决定是否能映射 (给未来扩展留口).
    """
    return CURSORFX_SECTION_TO_X11.get(section_name, [section_name])
