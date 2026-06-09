"""
归一化 X11 Cursor 对象 → (mac_name, frames) dict

策略 (按优先级):
  1. 先用 cursor.name 在 MACOS_CURSOR_MAP 中查找
  2. 如果 cursor.name 看起来是 32 位 hex 哈希 (X11 1.20+ SHA-1 alias):
     a. 先尝试 symlink realpath 解析 (旧版 X11 主题用 symlink)
     b. 再尝试 SHA-1 反查 (现代 X11 主题用真实目录)
  3. 都找不到则返回 None, 跳过该 cursor

SHA-1 反查原理:
  X11 1.20+ 引入 alias hash = SHA-1(cursor_file_content) 截断到 16 字符 hex
  现代主题把这些 hash 作为真实 cursor 目录名, 而不是 symlink
  → normalizer 需要计算 hash 名 cursor 的 SHA-1, 跟主题内 X11 standard name
    cursor 的 SHA-1 比对, 找到匹配的标准名

启动时 assert: MACOS_CURSOR_MAP 中不允许出现 32 位 hex 哈希名 (用户明确要求).
"""
import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path
from mapper.macos_full import MACOS_CURSOR_MAP


# X11 1.20+ 32 位 hex 哈希名 pattern (与 mapper/macos_full.py 中保持一致)
_HASH_PATTERN = re.compile(
    r"^[0-9a-f]{16,32}$"
    r"|^[0-9a-f]{8}_[0-9a-f]{8}_[0-9a-f]{8}_[0-9a-f]{8}$"
)

# SHA-1 截断长度: 16 字符 hex = 64 bit, 与 X11 cursor file hash 兼容
_SHA1_TRUNCATE_LEN = 16

# 统计: 用于诊断哪些 cursor 走了哪条 fallback 路径
_stats = defaultdict(int)


def _resolve_symlink_target_name(path: str) -> str | None:
    """如果 path 是 symlink, 解析 realpath, 取目标文件的 stem (X11 标准 cursor 名).

    例子:
      path = "themes/Vimix/cursors/0280060...0140"
      realpath = "themes/Vimix/cursors/left_ptr"
      → 返回 "left_ptr"  (再用它在 MACOS_CURSOR_MAP 查找)

    非 symlink 或 symlink 解析失败时返回 None.
    """
    if not path:
        return None
    try:
        real = os.path.realpath(path)
        if real == path:
            return None  # 不是 symlink
        return os.path.splitext(os.path.basename(real))[0]
    except OSError:
        return None


def _build_sha1_reverse_index(theme_root: str | None) -> dict[str, str]:
    """构建主题内 X11 standard name -> SHA-1[:16] 的反向表.

    策略:
      1. 找到 decoded/ 目录 (read_xcursor 生成的 PNG 解码目录)
      2. 遍历所有非哈希名 cursor 目录
      3. 计算每个 cursor 的 SHA-1 (按 frame_index 排序拼接 PNG 内容)
      4. 返回 {sha1: standard_name} 反向表

    注: 主题 root 通常是 .../cursors 目录的父目录, 函数会自动找 decoded/
    """
    if not theme_root:
        return {}

    # 找 decoded/ 目录
    decoded = None
    candidates = [Path(theme_root) / "decoded"]
    cur = Path(theme_root)
    while cur.parent != cur:
        candidates.append(cur / "decoded")
        cur = cur.parent

    for p in candidates:
        if p.exists() and p.is_dir():
            decoded = p
            break
    if not decoded:
        return {}

    index: dict[str, str] = {}
    for cursor_dir in decoded.iterdir():
        if not cursor_dir.is_dir():
            continue
        name = cursor_dir.name
        if _HASH_PATTERN.match(name):
            continue  # 跳过 hash 名 cursor
        # 计算 SHA-1
        frames = sorted(cursor_dir.glob("*.png"))
        if not frames:
            continue
        h = hashlib.sha1()
        for f in frames:
            h.update(f.read_bytes())
        sha = h.hexdigest()[:_SHA1_TRUNCATE_LEN]
        # 一个 SHA-1 可能对应多个 standard name (alias), 但我们只记第一个
        if sha not in index:
            index[sha] = name
    return index


def _resolve_via_sha1(cursor_path: str, sha_index: dict[str, str]) -> str | None:
    """用 SHA-1 反查 hash 名 cursor 对应的 X11 standard name.

    返回 standard name (如 'left_ptr') 供 MACOS_CURSOR_MAP 查找.
    """
    if not cursor_path or not sha_index:
        return None
    p = Path(cursor_path)
    if not p.exists():
        return None

    # 找 cursor 的 decoded/ 子目录
    # cursor_path 通常是 .../cursors/<hash>
    # decoded 对应 .../cursors/decoded/<hash>/
    decoded = p.parent / "decoded" / p.name
    if not decoded.exists() or not decoded.is_dir():
        return None

    frames = sorted(decoded.glob("*.png"))
    if not frames:
        return None

    h = hashlib.sha1()
    for f in frames:
        h.update(f.read_bytes())
    sha = h.hexdigest()[:_SHA1_TRUNCATE_LEN]
    return sha_index.get(sha)


def normalize(cursor, sha1_index: dict[str, str] | None = None):
    """把 Cursor 对象归一化为 (mac_name, frames) dict, 保留原始 X11 名字用于 warning.

    返回 None 表示该 cursor 没有 macOS identifier 映射 (X11 内部 cursor, 跳过).

    处理流程:
      1. cursor.name 命中 MACOS_CURSOR_MAP → 直接返回
      2. cursor.name 是 32 位 hex 哈希:
         a. symlink realpath 解析 → 用标准名查 MACOS_CURSOR_MAP
         b. SHA-1 反查 → 用 standard name 查 MACOS_CURSOR_MAP
      3. 都查不到 → 返回 None

    Args:
        cursor: Cursor 对象 (含 .name, .frames, .path)
        sha1_index: 可选的 SHA-1 -> X11 standard name 反向表
                    (由 _build_sha1_reverse_index 构建)
                    如果为 None, 只走 symlink 路径
    """
    # ===== 第 1 步: 直接查 MACOS_CURSOR_MAP =====
    mac_name = MACOS_CURSOR_MAP.get(cursor.name)
    if mac_name:
        _stats["direct_hit"] += 1
        return {
            "mac_name": mac_name,
            "x11_name": cursor.name,  # 保留 X11 原名, 用于 cape_builder 报告
            "frames": cursor.frames,
        }

    # ===== 第 2 步: 如果 cursor.name 是 32 位 hex 哈希, 走 fallback =====
    if _HASH_PATTERN.match(cursor.name):
        _stats["hash_name_seen"] += 1

        # 2a. symlink 解析 (旧版主题)
        resolved = _resolve_symlink_target_name(cursor.path)
        if resolved:
            mac_name = MACOS_CURSOR_MAP.get(resolved)
            if mac_name:
                _stats["symlink_resolved"] += 1
                return {
                    "mac_name": mac_name,
                    "x11_name": cursor.name,
                    "frames": cursor.frames,
                    "_resolved_from": resolved,
                }

        # 2b. SHA-1 反查 (现代主题用真实目录代替 symlink)
        if sha1_index:
            standard_name = _resolve_via_sha1(cursor.path, sha1_index)
            if standard_name:
                mac_name = MACOS_CURSOR_MAP.get(standard_name)
                if mac_name:
                    _stats["sha1_resolved"] += 1
                    return {
                        "mac_name": mac_name,
                        "x11_name": cursor.name,
                        "frames": cursor.frames,
                        "_resolved_from": standard_name,
                    }

        # 都失败
        _stats["hash_unresolved"] += 1
        return None

    # ===== 第 3 步: 都不是, 正常返回 None =====
    _stats["unmapped"] += 1
    return None


def get_stats() -> dict:
    """获取归一化统计 (供 cli.py / 报告使用)."""
    return dict(_stats)


def reset_stats() -> None:
    """重置统计 (每次 build_cape 之前调用)."""
    _stats.clear()


# 启动时 assert: 确保没有 32 位 hex 哈希名混入 MACOS_CURSOR_MAP
def _verify_no_hash_in_map():
    for k in MACOS_CURSOR_MAP:
        if _HASH_PATTERN.match(k):
            raise AssertionError(
                f"MACOS_CURSOR_MAP 中包含 32 位 hex 哈希名: '{k}' (用户明确要求移除)"
            )


_verify_no_hash_in_map()


# 为了在 cli.py 中方便使用, 提供一个工厂函数
def make_sha1_index(theme_root: str | None) -> dict[str, str]:
    """构建 SHA-1 反向表的公开接口."""
    return _build_sha1_reverse_index(theme_root)
