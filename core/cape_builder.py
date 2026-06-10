"""
按 Mousecape v2.0 cape 文件规范生成 .cape。

规范来源:
  - Mousecape 源码中的相关实现

关键发现:
  - 必须使用 XML 格式的 plist，binary plist 无法导入
  - 所有 50 个 cursorNameMap 槽位都必须填充
  - 18 个 Pointer 槽位优先使用 X11 真实数据，剩余使用 cross-fallback
"""

import getpass
import hashlib
import io
import plistlib
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from PIL import Image

from core.mousecape_defs import (
    CROSS_FALLBACK,
    CURSOR_MAP,
    MACOS_SYSTEM_RECOGNIZED,
    MACOS_USED,
    MOUSECAPE_POINTERS,
    MOUSECAPE_POINTERS_LIST,
    POINTER_DISPLAY_NAMES,
    POINTER_MISSING_X11,
    PRIVATE_PREFERRED,
    SPARE_IDENTIFIER_MAP,
    VALID_CURSOR_IDENTIFIERS,
    WINDOW_AND_PRIVATE_PREFERRED,
    X11_PRIORITY,
    # 版本与字典键常量
    MCCURSOR_CREATOR_VERSION,
    MCCURSOR_DICTIONARY_MINIMUM_VERSION_KEY,
    MCCURSOR_DICTIONARY_VERSION_KEY,
    MCCURSOR_DICTIONARY_CURSORS_KEY,
    MCCURSOR_DICTIONARY_AUTHOR_KEY,
    MCCURSOR_DICTIONARY_CLOUD_KEY,
    MCCURSOR_DICTIONARY_HIDPI_KEY,
    MCCURSOR_DICTIONARY_IDENTIFIER_KEY,
    MCCURSOR_DICTIONARY_CAPENAME_KEY,
    MCCURSOR_DICTIONARY_CAPEVERSION_KEY,
    MCCURSOR_DICTIONARY_FRAMECOUNT_KEY,
    MCCURSOR_DICTIONARY_FRAMEDURATION_KEY,
    MCCURSOR_DICTIONARY_HOTSPOTX_KEY,
    MCCURSOR_DICTIONARY_HOTSPOTY_KEY,
    MCCURSOR_DICTIONARY_POINTSWIDE_KEY,
    MCCURSOR_DICTIONARY_POINTSHIGH_KEY,
    MCCURSOR_DICTIONARY_REPRESENTATIONS_KEY,
    # 限制常量
    MAX_FRAME_COUNT,
    MAX_HOTSPOT_VALUE,
    # 工具函数
    get_cursor_name,
    is_pointer,
)
from core.validator import CapeValidator

# Mousecape 支持的标准 scale 倍数
_STANDARD_SCALES: tuple[float, ...] = (1.0, 2.0, 5.0)

# 默认 @1x 目标尺寸
_DEFAULT_TARGET_SIZE = 48


def _select_base_size(frames, target: int = 48) -> tuple[int, int]:
    """
    选 base size (PointsWide/High) 用作 cape 顶层元数据.

    选桶策略 (与 _frame_count 保持完全一致):
      1. 优先精确匹配 target (≤48 时选 36 或 48 等"标准" 尺寸)
      2. 否则选**帧数最多**的 size 桶 (动画最完整)
      3. 帧数相同时选 size 最大的桶 (细节最丰富)
      4. 静态光标 (全 1 帧) 时回到原 target 策略
    """
    sizes = sorted({(f.width, f.height) for f in frames})
    if not sizes:
        return target, target

    # 计算每个 size 桶的帧数
    by_size: dict[tuple[int, int], int] = defaultdict(int)
    for f in frames:
        by_size[(f.width, f.height)] += 1

    # 1. 优先 target 精确匹配
    if (target, target) in sizes:
        return target, target

    # 2. 选帧数最多 + size 最大的桶 (与 _frame_count 一致)
    #    这样保证 FrameCount 与 sheet 高度匹配
    best_size = max(
        by_size.keys(),
        key=lambda s: (by_size[s], s[0] * s[1]),
    )

    # 3. 若主导桶帧数为 1 (静态), 仍按 target 策略选
    #    (因为没有动画, 不需要"完整动画周期")
    if by_size[best_size] == 1:
        below = [s for s in sizes if s[0] <= target and s[1] <= target]
        if below:
            return below[-1]
        return sizes[-1]  # 取最大 size
    return best_size


def _build_representations(frames, points_w: int, points_h: int) -> list[bytes]:
    """
    把每个 size 下的多帧垂直堆叠成一张大图，为每个 scale 选择合适的 size，
    编码成 PNG 字节。

    选桶策略: caller (build_cape) 通过 _select_base_size 选好 base size,
    传入 points_w/h, 这里直接用它来选桶. 这保证 FrameCount 与 sheet 高度匹配.
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

        best = None
        for s in sizes_sorted:
            if s == (target_w, target_h):
                best = s
                break

        if best is None:
            candidates = [
                s for s in sizes_sorted if s[0] % points_w == 0 and s[1] % points_h == 0
            ]
            if candidates:
                best = min(
                    candidates,
                    key=lambda s: abs(s[0] - target_w) + abs(s[1] - target_h),
                )

        if best is None:
            continue

        group = by_size[best]
        if not group:
            continue

        w, h = best
        n = len(group)

        stacked = Image.new("RGBA", (w, h * n), (0, 0, 0, 0))
        for i, f in enumerate(group):
            img = Image.open(f.image_path).convert("RGBA")
            if img.size != (w, h):
                img = img.resize((w, h), Image.NEAREST)
            stacked.paste(img, (0, i * h))

        buf = io.BytesIO()
        stacked.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        if png_bytes not in seen:
            seen.add(png_bytes)
            representations.append(png_bytes)

    return representations


def _frame_count(frames) -> int:
    """
    动画帧数 = 主导 size 桶里的条目数 (静态光标返回 1).

    重要: 必须与 _build_representations 实际选用的 size 桶保持一致,
    否则 validator 会报 "rep height != PointsHigh * scale * FrameCount".

    选桶策略:
      1. 优先选帧数最多的桶 (动画最完整)
      2. 若帧数相同, 选 size 最大的桶 (动画细节最丰富)
      3. 若全为 1 帧, 选 size 最大的桶 (高分辨率, 静态)
    """
    by_size: dict[tuple[int, int], int] = defaultdict(int)
    for f in frames:
        by_size[(f.width, f.height)] += 1
    if not by_size:
        return 1
    # 选帧数最多 + size 最大的桶
    best_size, best_count = max(
        by_size.items(),
        key=lambda kv: (kv[1], kv[0][0] * kv[0][1]),
    )
    return best_count


def _frame_duration_seconds(frames) -> float:
    """单帧持续时间(秒)。静态光标给 1.0，动画光标取首个 delay > 0 的值。"""
    if _frame_count(frames) <= 1:
        return 1.0
    for f in frames:
        if f.delay > 0:
            return float(f.delay) / 1000.0
    return 1.0


def _hotspot_for_points(frames, points_w: int, points_h: int) -> tuple[float, float]:
    """选与 PointsWide/High 同坐标空间的 hotspot。"""
    for f in frames:
        if f.width == points_w and f.height == points_h:
            return float(f.hotspot[0]), float(f.hotspot[1])

    ref = min(frames, key=lambda f: f.width * f.height)
    if ref.width <= 0 or ref.height <= 0:
        return 0.0, 0.0

    sx = points_w / ref.width
    sy = points_h / ref.height
    return float(ref.hotspot[0]) * sx, float(ref.hotspot[1]) * sy


def _frame_fingerprint(frames_list) -> str:
    """计算帧数据指纹，用于识别相同数据。"""
    h = hashlib.md5()
    for f in sorted(frames_list, key=lambda f: (f.width, f.height, f.frame_index)):
        h.update(f.image_path.encode())
        h.update(f"{f.width},{f.height},{f.frame_index}".encode())
    return h.hexdigest()


def _find_spare_identifier(
    used: set[str],
    needed: set[str],
    current_fp: str,
    fp_to_used_ids: dict[str, set[str]],
) -> str | None:
    """找一个未使用的 macOS identifier 作为备用槽位。"""
    # 1. 优先 Window 系列
    for mac in WINDOW_AND_PRIVATE_PREFERRED:
        if (
            mac not in used
            and mac not in needed
            and mac not in MACOS_USED
            and mac not in fp_to_used_ids.get(current_fp, set())
        ):
            return mac
    # 2. 罕见的 private 槽位
    for mac in PRIVATE_PREFERRED:
        if (
            mac not in used
            and mac not in needed
            and mac not in MACOS_USED
            and mac not in fp_to_used_ids.get(current_fp, set())
        ):
            return mac
    # 3. 兜底: 任意未用且非 MACOS_USED 的 identifier
    for mac in sorted(VALID_CURSOR_IDENTIFIERS):
        if (
            mac in MACOS_USED
            or mac in used
            or mac in needed
            or mac in fp_to_used_ids.get(current_fp, set())
        ):
            continue
        return mac
    return None


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
    把归一化后的 cursor 列表序列化成 .cape 文件。

    与 Mousecape-swiftUI 源码 v1.1.3 完全兼容的实现：
    - 使用 MCDefs.m 定义的常量与键名
    - 遵循 apply.m 中的验证规则
    - 最大化 50 个 cursor identifier 的利用率

    Args:
        theme_name: 主题名称
        cursor_set: 归一化后的光标集合
        out_dir: 输出目录
        author: 作者名称 (默认当前用户)
        target_size: 目标 @1x 尺寸 (默认 48)
        self_validate: 是否在生成后验证 (默认 True)
        display_name: 显示名称 (默认同 theme_name)

    Returns:
        生成的 .cape 文件路径
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if display_name is None:
        display_name = theme_name

    if author is None:
        try:
            author = getpass.getuser()
        except Exception:
            author = "Anonymous"

    # 构建顶层结构 (使用源码定义的常量)
    cape: dict = {
        MCCURSOR_DICTIONARY_MINIMUM_VERSION_KEY: MCCURSOR_CREATOR_VERSION,
        MCCURSOR_DICTIONARY_VERSION_KEY: MCCURSOR_CREATOR_VERSION,
        MCCURSOR_DICTIONARY_CAPENAME_KEY: display_name,
        MCCURSOR_DICTIONARY_CAPEVERSION_KEY: 1.0,
        MCCURSOR_DICTIONARY_CLOUD_KEY: False,
        MCCURSOR_DICTIONARY_AUTHOR_KEY: author,
        MCCURSOR_DICTIONARY_HIDPI_KEY: True,
        MCCURSOR_DICTIONARY_IDENTIFIER_KEY: f"local.{author}.{theme_name}.{int(time.time())}",
        MCCURSOR_DICTIONARY_CURSORS_KEY: {},
    }

    # 排序 cursor_set: hash cursor 排最后，同 identifier 按优先级排序
    def _priority(c):
        if "_resolved_from" in c:
            return (1, float("inf"))
        mac = c["mac_name"]
        x11 = c.get("x11_name", mac)
        priority_list = X11_PRIORITY.get(mac, [])
        if x11 in priority_list:
            return (0, priority_list.index(x11))
        return (0, len(priority_list))

    cursor_set = sorted(cursor_set, key=_priority)
    # 输出排序后的 cursor_set长度
    print(f"Sorted cursor_set length: {len(cursor_set)}")
    # print(cursor_set)

    # 收集需要的 identifier
    all_needed_macs = set()
    for c in cursor_set:
        all_needed_macs.add(c["mac_name"])
    all_needed_macs.update(MOUSECAPE_POINTERS)
    print(f"Needed macs: {len(all_needed_macs)}")
    print(all_needed_macs)

    # 所有可用的 identifier 排序
    all_available_ids = sorted(VALID_CURSOR_IDENTIFIERS)

    # 先按 mac_name 分组，收集所有可能的帧
    frames_by_mac: dict[str, list[dict]] = defaultdict(list)
    for c in cursor_set:
        mac = c["mac_name"]
        x11 = c.get("x11_name", mac)
        if c.get("frames"):
            frames_by_mac[mac].append({"x11": x11, "frames": c["frames"]})

    seen_identifiers: set[str] = set()
    skipped_aliases: list[tuple[str, str]] = []
    fallback_used: list[tuple[str, str, str]] = []
    redistributed: list[tuple[str, str, str]] = []
    fp_to_used_ids: dict[str, set[str]] = defaultdict(set)
    pointer_missing_idx = 0

    # 处理所有 cursor
    for c in cursor_set:
        x11_name = c.get("x11_name", c["mac_name"])
        identifier = c["mac_name"]
        frames = c.get("frames", [])

        if not frames:
            continue

        # 检查是否明确跳过
        if x11_name in SPARE_IDENTIFIER_MAP and SPARE_IDENTIFIER_MAP[x11_name] is None:
            skipped_aliases.append((x11_name, c["mac_name"]))
            continue

        current_fp = _frame_fingerprint(frames)

        # 如果主槽位已被占用，或者是 hash cursor，尝试分配其他槽位
        if identifier in seen_identifiers or "_resolved_from" in c:
            assigned = False

            # 1. 优先用 SPARE_IDENTIFIER_MAP
            if x11_name in SPARE_IDENTIFIER_MAP:
                spare_mac = SPARE_IDENTIFIER_MAP[x11_name]
                if (
                    spare_mac not in seen_identifiers
                    and spare_mac not in fp_to_used_ids.get(current_fp, set())
                ):
                    identifier = spare_mac
                    redistributed.append((x11_name, c["mac_name"], spare_mac))
                    assigned = True

            # 2. 尝试分配给缺少 X11 候选的 Pointer 槽位
            if not assigned and pointer_missing_idx < len(POINTER_MISSING_X11):
                target_ptr = POINTER_MISSING_X11[pointer_missing_idx]
                if (
                    target_ptr not in seen_identifiers
                    and target_ptr not in fp_to_used_ids.get(current_fp, set())
                ):
                    identifier = target_ptr
                    pointer_missing_idx += 1
                    redistributed.append((x11_name, c["mac_name"], target_ptr))
                    assigned = True

            # 3. 最后尝试找其他槽位
            if not assigned:
                spare_id = _find_spare_identifier(
                    seen_identifiers, all_needed_macs, current_fp, fp_to_used_ids
                )
                if spare_id is not None:
                    identifier = spare_id
                    redistributed.append((x11_name, c["mac_name"], spare_id))
                    assigned = True

            # 4. 都没有就跳过
            if not assigned:
                skipped_aliases.append((x11_name, c["mac_name"]))
                continue

        # 现在有了可用的 identifier
        seen_identifiers.add(identifier)
        fp_to_used_ids[current_fp].add(identifier)

        # Fallback a: 如果当前 frames 为空，从同 identifier 找其他 X11 帧
        if not frames and identifier in frames_by_mac:
            for src in frames_by_mac[identifier]:
                if src["x11"] != x11_name and src["frames"]:
                    frames = src["frames"]
                    fallback_used.append((src["x11"], x11_name, "sibling"))
                    break

        if not frames:
            continue

        # 构建这个 cursor 的数据
        try:
            frame_count = _frame_count(frames)
            # 验证帧计数 (源码 apply.m 限制: 1 <= frame_count <= 24)
            if frame_count < 1 or frame_count > MAX_FRAME_COUNT:
                print(
                    f"  [skip] {identifier}: frame count {frame_count} out of range [1, {MAX_FRAME_COUNT}]"
                )
                continue

            points_w, points_h = _select_base_size(frames, target=target_size)
            representations = _build_representations(frames, points_w, points_h)
            if not representations:
                continue

            hot_x, hot_y = _hotspot_for_points(frames, points_w, points_h)
            # 验证并 clamp hot spot (源码 apply.m 限制: 0 <= hotSpot <= MAX_HOTSPOT_VALUE)
            hot_x_clamped = max(0.0, min(hot_x, MAX_HOTSPOT_VALUE))
            hot_y_clamped = max(0.0, min(hot_y, MAX_HOTSPOT_VALUE))
            if hot_x != hot_x_clamped or hot_y != hot_y_clamped:
                print(
                    f"  [warn] {identifier}: hot spot ({hot_x:.1f}, {hot_y:.1f}) clamped to ({hot_x_clamped:.1f}, {hot_y_clamped:.1f})"
                )

            # 使用源码定义的键名构建字典
            cursor_dict = {
                MCCURSOR_DICTIONARY_FRAMECOUNT_KEY: int(frame_count),
                MCCURSOR_DICTIONARY_FRAMEDURATION_KEY: float(
                    _frame_duration_seconds(frames)
                ),
                MCCURSOR_DICTIONARY_HOTSPOTX_KEY: float(hot_x_clamped),
                MCCURSOR_DICTIONARY_HOTSPOTY_KEY: float(hot_y_clamped),
                MCCURSOR_DICTIONARY_POINTSWIDE_KEY: float(points_w),
                MCCURSOR_DICTIONARY_POINTSHIGH_KEY: float(points_h),
                MCCURSOR_DICTIONARY_REPRESENTATIONS_KEY: representations,
            }
            cape[MCCURSOR_DICTIONARY_CURSORS_KEY][identifier] = cursor_dict
        except Exception as e:
            print(f"  [skip] {identifier}: {e}")
            continue

    # Fallback b: 处理 cross-fallback，只填充还空着的槽位
    cursors_dict = cape[MCCURSOR_DICTIONARY_CURSORS_KEY]
    for target_mac, src_mac in CROSS_FALLBACK.items():
        if src_mac not in cursors_dict:
            continue
        if target_mac not in cursors_dict:
            src_dict = cursors_dict[src_mac]
            cursors_dict[target_mac] = dict(src_dict)
            fallback_used.append((src_mac, target_mac, "cross"))
            seen_identifiers.add(target_mac)

    # 打印处理信息
    if redistributed:
        print(
            f"  [info] redistributed {len(redistributed)} X11 cursor(s) to spare identifiers:"
        )
        grouped_to: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for x11, from_mac, to_mac in redistributed:
            grouped_to[to_mac].append((x11, from_mac))
        for to_mac in sorted(grouped_to):
            items = grouped_to[to_mac]
            x11s = ", ".join(x for x, _ in items[:5])
            more = "" if len(items) <= 5 else f" (+{len(items) - 5} more)"
            from_macs = ", ".join(sorted(set(f for _, f in items)))
            print(f"    {to_mac}: [{x11s}{more}]  ← from {from_macs}")

    if skipped_aliases:
        grouped: dict[str, list[str]] = defaultdict(list)
        for x11, mac in skipped_aliases:
            grouped[mac].append(x11)
        print(
            f"  [info] merged {len(skipped_aliases)} X11 alias(es) into existing mac identifiers:"
        )
        for mac, names in sorted(grouped.items()):
            sample = sorted(set(names))[:5]
            more = "" if len(names) <= 5 else f" (+{len(names) - 5} more)"
            print(f"    {mac}: {', '.join(sample)}{more}")

    if fallback_used:
        siblings = [f for f in fallback_used if f[2] == "sibling"]
        cross = [f for f in fallback_used if f[2] == "cross"]
        if siblings:
            print(
                f"  [info] reused frames from siblings for {len(siblings)} zero-byte X11 cursor file(s):"
            )
            for src, target, _ in siblings:
                print(f"    {target} (empty) ← reused from {src}")
        if cross:
            print(
                f"  [info] cross-identifier fallback for {len(cross)} mac identifier(s):"
            )
            for src, target, _ in cross:
                print(f"    {target} ← reused frames from {src}")

    out = out_dir / f"{theme_name}.cape"
    # 必须是 XML plist
    with open(out, "wb") as f:
        plistlib.dump(cape, f, fmt=plistlib.FMT_XML)

    # Self-validation
    if self_validate:
        validator = CapeValidator(out)
        ok = validator.validate()
        print(validator.report())
        if not ok:
            raise RuntimeError(
                f"Cape validation failed ({len(validator.errors)} error(s)). "
                "Mousecape will refuse to import this file."
            )

    # 获取 cursors 字典
    cursors_dict = cape[MCCURSOR_DICTIONARY_CURSORS_KEY]

    # 最终总结
    total_x11_in = len(cursor_set)
    total_in_cape = len(cursors_dict)
    total_redistributed = len(redistributed)
    total_merged = len(skipped_aliases)
    total_cross = len([f for f in fallback_used if f[2] == "cross"])
    main_uses_x11 = total_in_cape - total_redistributed - total_cross
    x11_accounted = main_uses_x11 + total_redistributed + total_merged

    print()
    print(f"  ====== Summary ======")
    print(
        f"  CapeName             : {cape.get(MCCURSOR_DICTIONARY_CAPENAME_KEY, theme_name)}"
    )
    print(f"  CapeFile             : {out}")
    print(f"  X11 cursor input     : {total_x11_in}")
    print(f"  mac identifiers used : {total_in_cape} / {len(VALID_CURSOR_IDENTIFIERS)}")
    print(f"    - main (主 cursor) : {main_uses_x11}")
    print(f"    - redistributed    : {total_redistributed}")
    print(f"    - cross-fallback   : {total_cross}")
    print()
    print(f"  X11 cursors 处理明细:")
    print(f"    - 独立槽位         : {main_uses_x11 + total_redistributed}")
    print(f"    - 合并别名         : {total_merged}")
    print()
    print(f"  说明:")
    print(f"    main = 优先级最高的 X11 cursor")
    print(f"    redistributed = 其他不同帧数据分配到备用槽位")
    print(f"    merged = 相同帧数据，复用主 cursor 帧")
    print(f"    cross-fallback = 完全没有数据，从其他 identifier 复制")

    if x11_accounted == total_x11_in:
        print()
        print(f"  [OK] 所有 {total_x11_in} 个 X11 cursor 都已处理")
    else:
        diff = total_x11_in - x11_accounted
        print()
        print(
            f"  [WARN] 数量不平: 输入 {total_x11_in} vs 已处理 {x11_accounted} (差 {diff})"
        )

    # ===== 三层分类报告 =====
    # Cape 文件 cursor 状态 (50 槽位视图): 让用户看到每个槽位是否被填充
    # macOS 系统响应视图 (25 个): 系统实际能注册成功的 cursor
    # Mousecape UI Pointer 视图 (15 个 Windows 风格): UI 主界面显示的分组

    print()
    print(f"  ====== 三层分类汇总 ======")
    print(f"  层级 1: cape 文件 50 个 cursorMap 槽位 (cursorMap 全集)")
    print(f"  层级 2: macOS 系统能响应的 {len(MACOS_SYSTEM_RECOGNIZED)} 个 cursor (实测)")
    print(f"  层级 3: Mousecape UI 15 个 Pointer 分组 (Windows 风格)")
    print()

    cross_fallback_targets = {
        target for src, target, kind in fallback_used if kind == "cross"
    }

    # 收集 X11 候选
    pointer_x11_candidates: dict[str, list[str]] = {p: [] for p in VALID_CURSOR_IDENTIFIERS}
    for c in cursor_set:
        x11 = c.get("x11_name", c["mac_name"])
        mac = c["mac_name"]
        if mac in pointer_x11_candidates:
            pointer_x11_candidates[mac].append(x11)

    # 统计三层的填充情况
    # 层级 1: 50 槽位
    total_50 = len(VALID_CURSOR_IDENTIFIERS)
    filled_50 = sum(1 for p in VALID_CURSOR_IDENTIFIERS if p in cursors_dict)
    print(
        f"  [1] cape 文件 50 槽位: ✅ {filled_50}/{total_50} 填充 "
        f"({total_50 - filled_50} 缺失)"
    )

    # 层级 2: 25 个 macOS 系统响应
    total_25 = len(MACOS_SYSTEM_RECOGNIZED)
    filled_25 = sum(
        1 for p in MACOS_SYSTEM_RECOGNIZED if p in cursors_dict
    )
    print(
        f"  [2] macOS 系统响应 {total_25} 个: ✅ {filled_25}/{total_25} 填充 "
        f"({total_25 - filled_25} 缺失)"
    )

    # 层级 3: 15 个 UI Pointer 分组（每个分组只要任一 identifier 填充就视为已填充）
    from core.mousecape_defs import UI_POINTER_GROUPS
    total_15 = len(UI_POINTER_GROUPS)
    filled_15 = sum(
        1
        for _, idents in UI_POINTER_GROUPS
        if any(p in cursors_dict for p in idents)
    )
    print(
        f"  [3] Mousecape UI 15 Pointer 分组: ✅ {filled_15}/{total_15} 填充 "
        f"({total_15 - filled_15} 分组空缺)"
    )

    # 详细列出每层的缺失项
    print()
    missing_50 = [p for p in VALID_CURSOR_IDENTIFIERS if p not in cursors_dict]
    if missing_50:
        print(f"  [1] 50 槽位缺失 ({len(missing_50)} 个):")
        for p in missing_50:
            print(f"      ❌ {p} ({get_cursor_name(p)})")

    missing_25 = [p for p in MACOS_SYSTEM_RECOGNIZED if p not in cursors_dict]
    if missing_25:
        print(f"  [2] macOS 系统响应缺失 ({len(missing_25)} 个):")
        for p in missing_25:
            # 用 CURSOR_MAP 反查名称, 没有的用描述性占位符
            name = get_cursor_name(p)
            if name == "Unknown":
                # 列出在 CURSOR_MAP 中没注册但源码 defaultCursors[] 中有的 cursor
                # 这些 cursor 实际系统不响应, 不应该出现在本层级
                print(f"      ⚠️ {p} (不在 CURSOR_MAP, 默认跳过)")
            else:
                print(f"      ❌ {p} ({name})")

    missing_15 = [
        (gname, idents)
        for gname, idents in UI_POINTER_GROUPS
        if not any(p in cursors_dict for p in idents)
    ]
    if missing_15:
        print(f"  [3] 15 UI 分组空缺 ({len(missing_15)} 个):")
        for gname, idents in missing_15:
            print(f"      ❌ {gname} <- {[get_cursor_name(p) for p in idents]}")

    # 关键成功标准
    print()
    if filled_50 == 50:
        print(f"  [OK] cape 文件 {total_50} 个 cursorMap 槽位全部填充!")
    else:
        print(f"  [WARN] cape 文件缺 {total_50 - filled_50} 个槽位 (期望 50)")

    if filled_25 == total_25:
        print(f"  [OK] macOS 系统响应的 {total_25} 个 cursor 全部填充!")
    else:
        print(f"  [WARN] macOS 系统响应缺 {total_25 - filled_25} 个")

    if filled_15 == 15:
        print(f"  [OK] Mousecape UI 15 个 Pointer 分组全部填充!")

    return out
