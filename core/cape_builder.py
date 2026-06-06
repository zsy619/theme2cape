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
            skipped_aliases.append((x11_name, identifier))
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

    # X11 cursor 命名空间保留: 用 X11 cursor 名作为主 identifier (非 macOS 标准名)
    # 优点: Mousecape 内部的 NSSet 会去重; cursorMap 查不到时把 X11 名作为 default name 显示,
    # 不会显示 "Unknown"
    # 策略: 遍历 cursor_set, 用 X11 名作为 identifier 写入 cape, 与 mac identifier 同一份 cursor dict
    # (避免重复 PNG 数据)
    # 跳过 32 位 hash 名 (Mousecape cursorMap 找不到 → "Unknown" type)
    def _is_x11_hash(name: str) -> bool:
        return len(name) == 32 and all(c in "0123456789abcdef" for c in name)

    x11_used: set[str] = set()
    x11_added_count = 0
    for c in cursor_set:
        x11_name = c.get("x11_name", c["mac_name"])
        if not c.get("frames"):
            continue
        if x11_name in x11_used:
            continue
        if _is_x11_hash(x11_name):
            continue  # 32 位 hash 名跳过, Mousecape cursorMap 找不到
        # 找这个 X11 名对应的 mac identifier (用于复用 frames)
        mac = c["mac_name"]
        if mac not in cape["Cursors"]:
            continue  # mac identifier 自身没生成 (e.g. 0 字节空文件且无 sibling), 跳过
        x11_used.add(x11_name)
        if x11_name == mac:
            continue  # 已经是 mac identifier, 不重复添加
        # 用 X11 名作为 identifier, 复用 mac identifier 的 cursor dict
        if x11_name in cape["Cursors"]:
            continue  # 已经有
        cape["Cursors"][x11_name] = dict(cape["Cursors"][mac])
        x11_added_count += 1
    if x11_added_count:
        print(f"  [info] kept {x11_added_count} X11 cursor name(s) as alias entry (no 'Unknown' display)")

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

    return out
