from mapper.macos_full import MACOS_CURSOR_MAP


def normalize(cursor):
    """把 Cursor 对象归一化为 (mac_name, frames) dict, 保留原始 X11 名字用于 warning.

    返回 None 表示该 cursor 没有 macOS identifier 映射 (X11 内部 cursor, 跳过).
    """
    mac_name = MACOS_CURSOR_MAP.get(cursor.name)

    if not mac_name:
        return None

    return {
        "mac_name": mac_name,
        "x11_name": cursor.name,  # 保留 X11 原名, 用于 cape_builder 报告被合并的别名
        "frames": cursor.frames,
    }
