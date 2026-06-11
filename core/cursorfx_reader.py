"""
Stardock CursorFX (原 CursorXP) 主题包解析.

格式背景:
  - `*.CursorFX` 有两种形态:
    1. 二进制文件: 压缩的二进制格式,包含所有光标数据
    2. 目录形态: 在 Windows 资源管理器里看起来是一个"文件",但实际是一个
       带 `.CursorFX` 扩展名的目录(Windows shell compound document).
  - 解压到磁盘后,目录结构非常扁平:
      <ThemeName>.CursorFX/
          Scheme.ini          <- INI 格式元数据
          Arrow.png           <- 横向拼接的帧序列 (Frames=N 时宽=N×frame_w)
          Cross.png
          Hand.png
          ...
  - `Scheme.ini` 形如:
      [Scheme]
      Version=1
      Name=MyTheme
      Author=...
      [Arrow]
      Frames=1
      Hot spot x=0
      Hot spot y=0
      Interval=100
      [Wait]
      Frames=12
      Hot spot x=12
      Hot spot y=12
      Interval=100

参考实现:
  https://github.com/ewindisch/sd2xc  (Perl, Stardock CursorFX → X11 转换器)
  https://github.com/SystemRage/Metamorphosis (Python, CursorFX 二进制解析)

设计要点 (与现有 XCursor 管线兼容):
  - 一个 section (如 Arrow) 对应多个 X11 cursor alias (left_ptr, X_cursor,
    right_ptr),这是 Stardock 设计:同一 PNG 可作多种 cursor 状态用.
  - 我们把一个 section 拆成多个 Cursor 对象,每个对象 name = X11 alias.
    这样下游 `core/normalizer.py` 用 `MACOS_CURSOR_MAP[alias]` 即可查
    macOS identifier,完全复用 XCursor 路径.
  - 帧数据写到 `decoded/<Section>/<size>_<frame_index>.png` 目录,沿用
    kxcursor_reader 的目录约定 (供 sha1_index 等使用).

Mousecape 硬限制: FrameCount ≤ 24 (apply.m L16). 大于 24 帧的动画必须
按比例 subsample, 同时按比例放大 Interval 保持循环总时长不变.
"""

from __future__ import annotations

import configparser
from pathlib import Path

from core.cim import Cursor, CursorFrame
from core.cursorfx_binary_reader import is_cursorfx_binary, read_cursorfx_binary
from mapper.cursorfx_x11_map import CURSORFX_SECTION_TO_X11


# Mousecape 硬限制: 1 帧 ≤ FrameCount ≤ 24
MAX_MOUSECAPE_FRAMES = 24


# ----- 入口识别 -----

def is_cursorfx_theme(path: Path) -> bool:
    """
    判断 path 是否为 CursorFX 主题包.

    判定规则:
      - 如果是文件: 检查是否为 CursorFX 二进制文件
      - 如果是目录: 检查是否为已展开的 CursorFX 目录
        - 目录内含 Scheme.ini (case-insensitive, 容错)
        - Scheme.ini 含至少一个 cursor section (e.g. [Arrow])

    注: 某些用户可能会把 .CursorFX 目录打成 zip 再传过来,本函数只认
    "已展开的目录" 或 "二进制文件" 形态. 如果是 zip 形态, 先用通用 zip 解压后再走
    一次本判定.
    """
    if not path:
        return False

    # 检查是否为二进制文件
    if path.is_file():
        return is_cursorfx_binary(path)

    # 检查是否为目录
    if not path.is_dir():
        return False

    # 容错: 找任意一个 Scheme.ini (大小写不敏感)
    scheme = None
    for entry in path.iterdir():
        if entry.is_file() and entry.name.lower() == "scheme.ini":
            scheme = entry
            break
    if not scheme:
        return False
    # 简单 sniff: 至少有 1 个 [Section] 形如 [Arrow]/[Cross]/[Wait]/[Hand] 等
    try:
        text = scheme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "[Arrow]" in text or "[Cross]" in text or "[Wait]" in text or "[Hand]" in text


# ----- Scheme.ini 解析 -----

class CursorFxSection:
    """单个 [Section] 的元数据 (来自 Scheme.ini)."""

    __slots__ = ("name", "frames", "hot_x", "hot_y", "interval")

    def __init__(self, name: str, frames: int, hot_x: int, hot_y: int, interval: int):
        self.name = name
        self.frames = max(1, frames)
        self.hot_x = max(0, hot_x)
        self.hot_y = max(0, hot_y)
        # Interval 单位是毫秒, < 0 当 0 处理 (静态光标的常见情况)
        self.interval = max(0, interval)


def parse_scheme_ini(scheme_path: Path) -> dict[str, CursorFxSection]:
    """
    解析 Scheme.ini → {section_name: CursorFxSection}.

    容错:
      - Section 名缺失 Frames/Hot spot/Interval 字段时用安全默认值
      - configparser 不允许 key 含空格, 我们用 raw 解析前先做归一化
        (把 "Hot spot x" 替换成 "HotspotX" 等)
      - 任何解析错误 (格式异常等) 不抛, 返回已成功解析的 sections
    """
    raw = scheme_path.read_text(encoding="utf-8", errors="replace")

    # 归一化 key: "Hot spot x" → "hotspotx" (configparser 要求 key 不含空格且唯一)
    normalized_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        # section header
        if stripped.startswith("[") and stripped.endswith("]"):
            normalized_lines.append(line)
            continue
        # key=value
        if "=" in line:
            k, v = line.split("=", 1)
            k_norm = k.strip().lower().replace(" ", "")
            normalized_lines.append(f"{k_norm}={v}")
        else:
            normalized_lines.append(line)

    cp = configparser.ConfigParser(strict=False, allow_no_value=True)
    cp.read_string("\n".join(normalized_lines))

    result: dict[str, CursorFxSection] = {}
    for section in cp.sections():
        # 跳过 [Scheme] 段 (这是元数据, 不是 cursor)
        if section.lower() == "scheme":
            continue

        def _get_int(key: str, default: int) -> int:
            try:
                return int(cp.get(section, key, fallback=default))
            except (ValueError, TypeError):
                return default

        frames = _get_int("frames", 1)
        hot_x = _get_int("hotspotx", 0)
        hot_y = _get_int("hotspoty", 0)
        interval = _get_int("interval", 0)

        result[section] = CursorFxSection(
            name=section, frames=frames, hot_x=hot_x, hot_y=hot_y, interval=interval
        )
    return result


# ----- 帧切分 (横向 strip → 单帧 PNG) -----

def _split_strip_png(
    png_path: Path,
    section_name: str,
    frames_count: int,
    decoded_root: Path,
) -> tuple[int, int, list[Path]]:
    """
    把横向 strip PNG 切成 N 张单帧 PNG, 写到 decoded_root/<section>/<size>_<i>.png.

    Returns:
        (frame_width, frame_height, [单帧 PNG 路径列表])

    Raises:
        ValueError: PNG 异常 (无法打开, 宽度不整除, 等)
    """
    from PIL import Image

    if not png_path.is_file():
        raise ValueError(f"PNG not found: {png_path}")

    img = Image.open(png_path)
    img.load()  # 立即加载, 避免 lazy load 反复打开文件
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    total_w, total_h = img.size
    if frames_count <= 1:
        frame_w, frame_h = total_w, total_h
    else:
        if total_w % frames_count != 0:
            # 宽度不整除 → 退化为单帧 (容错, 不抛错)
            # 部分主题作者把多帧做成 32×32 多行, 而不是 1×N strip
            # 这种我们降级为取第 0 帧, 而不是拒绝整个主题
            frame_w, frame_h = total_w, total_h
            frames_count = 1
        else:
            frame_w = total_w // frames_count
            frame_h = total_h

    out_dir = decoded_root / section_name
    out_dir.mkdir(parents=True, exist_ok=True)

    out_paths: list[Path] = []
    for i in range(frames_count):
        if frames_count <= 1:
            crop = img
        else:
            crop = img.crop((i * frame_w, 0, (i + 1) * frame_w, frame_h))
        out_path = out_dir / f"{max(frame_w, frame_h)}_{i}.png"
        crop.save(out_path, format="PNG")
        out_paths.append(out_path)
    return frame_w, frame_h, out_paths


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


# ----- 主入口 -----

def read_cursorfx_theme(theme_path: Path) -> tuple[str, list[Cursor]]:
    """
    读一个 .CursorFX 文件或目录, 返回 (theme_name, [Cursor 列表]).

    行为:
      - 如果是文件: 调用二进制解析器
      - 如果是目录: 解析 Scheme.ini 和 PNG 文件

    目录形态处理流程:
      1. 解析 Scheme.ini
      2. 对每个 section, 找同目录下的 <Section>.png
      3. 横向切帧, 写到 decoded/<Section>/<size>_<i>.png
      4. 查 CURSORFX_SECTION_TO_X11 拿 X11 alias 列表, 每个 alias 生成一个 Cursor
      5. 如果 Frames > 24, 按比例 subsample, 同时按比例放大 Interval

    Args:
        theme_path: CursorFX 二进制文件或已展开的 .CursorFX 目录路径

    Returns:
        (theme_name, [Cursor 列表])
        - theme_name: 优先用 [Scheme] 段 Name 字段, 缺省用文件/目录名
        - Cursor 列表: 每个 X11 alias 一个 Cursor, 共享同一组 frames

    Raises:
        FileNotFoundError: 文件/目录不存在或 Scheme.ini 不存在
        ValueError: 二进制文件格式无效
    """
    # 检查是否为二进制文件
    if theme_path.is_file():
        return read_cursorfx_binary(theme_path)

    # 以下是目录形态的处理逻辑
    theme_dir = theme_path

    # ---- 1. 找 Scheme.ini ----
    scheme_path = None
    for entry in theme_dir.iterdir():
        if entry.is_file() and entry.name.lower() == "scheme.ini":
            scheme_path = entry
            break
    if not scheme_path:
        raise FileNotFoundError(f"Scheme.ini not found in {theme_dir}")

    # ---- 2. 解析 + 提取 theme name ----
    sections = parse_scheme_ini(scheme_path)

    # 尝试从 [Scheme] 段拿主题名
    theme_name = theme_dir.name
    try:
        raw = scheme_path.read_text(encoding="utf-8", errors="replace")
        cp = configparser.ConfigParser(strict=False)
        # 把 "Hot spot x" 归一化后 [Scheme] 段才能正常解析
        normalized = []
        for line in raw.splitlines():
            if "=" in line and not line.strip().startswith("["):
                k, v = line.split("=", 1)
                k_norm = k.strip().lower().replace(" ", "")
                normalized.append(f"{k_norm}={v}")
            else:
                normalized.append(line)
        cp.read_string("\n".join(normalized))
        if cp.has_section("Scheme") and cp.has_option("Scheme", "name"):
            candidate = cp.get("Scheme", "name").strip()
            if candidate:
                theme_name = candidate
    except (configparser.Error, OSError):
        pass  # fallback 到目录名

    # ---- 3. decoded/ 根目录 ----
    decoded_root = theme_dir / "decoded"
    decoded_root.mkdir(parents=True, exist_ok=True)

    # ---- 4. 遍历 sections, 切帧 + 生成 Cursor ----
    cursors: list[Cursor] = []
    for sec_name, meta in sections.items():
        # 找 <Section>.png (case-insensitive, 容错)
        png_path = None
        for entry in theme_dir.iterdir():
            if entry.is_file() and entry.stem.lower() == sec_name.lower() and entry.suffix.lower() == ".png":
                png_path = entry
                break
        if not png_path:
            # 这个 section 没对应的 PNG, 跳过
            continue

        # 切帧
        try:
            frame_w, frame_h, frame_pngs = _split_strip_png(
                png_path=png_path,
                section_name=sec_name,
                frames_count=meta.frames,
                decoded_root=decoded_root,
            )
        except (ValueError, OSError) as e:
            # 单个 section 切帧失败, 不让整个主题失败
            print(f"  [warn] failed to split {sec_name}.png: {e}")
            continue

        n_original = len(frame_pngs)
        if n_original == 0:
            continue

        # ---- 5. FrameCount ≤ 24 硬限制 ----
        # Mousecape apply.m L16 拒绝 frameCount > 24.
        # 均匀下采样 + 按比例放大 interval 保持循环总时长.
        if n_original > MAX_MOUSECAPE_FRAMES:
            indices = _subsample_indices(n_original, MAX_MOUSECAPE_FRAMES)
            sampled = [frame_pngs[i] for i in indices]
            scale = n_original / MAX_MOUSECAPE_FRAMES
            sampled_interval = max(1, int(round(meta.interval * scale))) if meta.interval > 0 else 0
            print(
                f"  [info] CursorFX {sec_name}: {n_original} frames > 24, "
                f"subsampled to {len(sampled)} (interval {meta.interval}ms → {sampled_interval}ms)"
            )
            frame_pngs = sampled
            interval = sampled_interval
        else:
            interval = meta.interval

        # ---- 6. 构造 CursorFrame 列表 ----
        # nominal_size 选 max(frame_w, frame_h) — 与 XCursor 习惯一致
        # 例如 24×32 箭头 → nominal_size=32
        nominal = max(frame_w, frame_h)
        frames: list[CursorFrame] = []
        for idx, png in enumerate(frame_pngs):
            frames.append(
                CursorFrame(
                    image_path=str(png),
                    hotspot=(meta.hot_x, meta.hot_y),
                    delay=float(interval),
                    width=frame_w,
                    height=frame_h,
                    frame_index=idx,
                    nominal_size=nominal,
                )
            )

        # ---- 7. 查 X11 alias 列表, 每个 alias 生成一个 Cursor ----
        aliases = CURSORFX_SECTION_TO_X11.get(sec_name, [sec_name])
        for alias in aliases:
            cursors.append(
                Cursor(
                    name=alias,                # X11 cursor name (给 normalizer 用)
                    frames=frames,             # 共享同一组帧
                    path=str(png_path),        # 原始 PNG 路径 (供 sha1_index 用)
                )
            )

    return theme_name, cursors
