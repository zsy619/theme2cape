"""
Cape self-validator: 完整模拟 Mousecape 解析 .cape 的整条代码路径,确保我们
生成的文件能真正被 Mousecape 加载。

复现的代码路径(对照 /tmp/Mousecape 源码):
  1. MCCursorLibrary.m -initWithContentsOfURL:
       NSDictionary *dictionary = [NSDictionary dictionaryWithContentsOfURL:URL];
       # ↑ Foundation API,只支持 XML plist;binary plist 一律返回 nil
  2. MCCursorLibrary.m -_readFromDictionary:
       检查 Identifier 是否非空;
       检查 minimumVersion <= MCCursorParserVersion (2.0)
       调 addCursorsFromDictionary
  3. MCCursorLibrary.m -addCursorsFromDictionary:
       for key in cursorDicts.allKeys:
         cursor = MCCursor.cursorWithDictionary:cursorDictionary ofVersion:version
  4. MCCursor.m -_readFromDictionary: (v2.0 分支)
       if (frameCount && frameDuration && hotSpotX && hotSpotY && pointsWide && pointsHigh):
         self.frameCount    = frameCount.unsignedIntegerValue
         self.frameDuration = frameDuration.doubleValue
         self.hotSpot       = NSMakePoint(hotSpotX.doubleValue, hotSpotY.doubleValue)
         for data in reps:
           rep = NSBitmapImageRep initWithData:data   # 用 PIL 模拟
           rep.size = NSMakeSize(self.size.width, self.size.height * self.frameCount)
           # ↑ 这里 self.size 还没赋值(NSDocument init 时是 NSZeroSize),所以
           #   rep.size 会被设成 (0, 0) -- 源码 bug,但不影响 import
           self setRepresentation:rep.retaggedSRGBSpace forScale:cursorScaleForScale(...)
  5. MCCursor.m cursorScaleForScale:
       if (scale < 0) return MCCursorScaleNone;
       return (MCCursorScale)((NSInteger)scale * 100);
  6. MCCursor.m -setRepresentation:forScale:
       representations[@(scale)] = rep
       if (representations.count == 1):
         # 第一次设置时根据 rep 的实际像素重算 size
         # size.w = rep.pixelsWide / (scale/100.0)
         # size.h = rep.pixelsHigh / frameCount / (scale/100.0)
         if size != (0, 0): self.size = size
       # 第二次之后(L111 处) self.size 被覆写回 pointsWide/pointsHigh
"""

import io
import plistlib
from pathlib import Path
from typing import Any
from PIL import Image

# 共享的 Mousecape 源码常量 (来自 MCDefs.m)
# 兼容两种导入方式:作为 core 包内模块运行(无前缀) / 作为顶层模块运行(带 core. 前缀)
try:
    from mousecape_defs import (
        MAX_FRAME_COUNT,
        MIN_FRAME_COUNT,
        MAX_IMPORT_SIZE,
        MAX_HOTSPOT_VALUE,
        MCCURSOR_SCALE_100,
        MCCURSOR_SCALE_NONE,
        VALID_SCALES,
        cursor_scale_for_scale,
        # 字典键名常量
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
    )
except ImportError:
    from core.mousecape_defs import (
        MAX_FRAME_COUNT,
        MIN_FRAME_COUNT,
        MAX_IMPORT_SIZE,
        MAX_HOTSPOT_VALUE,
        MCCURSOR_SCALE_100,
        MCCURSOR_SCALE_NONE,
        VALID_SCALES,
        cursor_scale_for_scale,
        # 字典键名常量
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
    )


class CapeValidator:
    """完整模拟 Mousecape v2.0 cape 文件的解析流程"""

    # MCCursorLibrary.m L176-184 读取的字段 (使用源码定义的常量)
    TOP_KEYS = (
        MCCURSOR_DICTIONARY_MINIMUM_VERSION_KEY,
        MCCURSOR_DICTIONARY_VERSION_KEY,
        MCCURSOR_DICTIONARY_CAPENAME_KEY,
        MCCURSOR_DICTIONARY_CAPEVERSION_KEY,
        MCCURSOR_DICTIONARY_CLOUD_KEY,
        MCCURSOR_DICTIONARY_AUTHOR_KEY,
        MCCURSOR_DICTIONARY_HIDPI_KEY,
        MCCURSOR_DICTIONARY_IDENTIFIER_KEY,
        MCCURSOR_DICTIONARY_CURSORS_KEY,
    )

    # MCCursor.m L85-92 读取的字段 (使用源码定义的常量)
    CURSOR_KEYS = (
        MCCURSOR_DICTIONARY_FRAMECOUNT_KEY,
        MCCURSOR_DICTIONARY_FRAMEDURATION_KEY,
        MCCURSOR_DICTIONARY_HOTSPOTX_KEY,
        MCCURSOR_DICTIONARY_HOTSPOTY_KEY,
        MCCURSOR_DICTIONARY_POINTSWIDE_KEY,
        MCCURSOR_DICTIONARY_POINTSHIGH_KEY,
        MCCURSOR_DICTIONARY_REPRESENTATIONS_KEY,
    )

    def __init__(self, cape_path: str | Path):
        self.path = Path(cape_path)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def validate(self) -> bool:
        # ---- Step 1: NSDictionary dictionaryWithContentsOfURL: ----
        # Foundation 这个 API 只读 XML plist;binary plist 直接返回 nil
        if not self.path.exists():
            self.errors.append(f"file not found: {self.path}")
            return False

        try:
            data = self.path.read_bytes()
        except OSError as e:
            self.errors.append(f"read error: {e}")
            return False

        # 严格 XML-only -- 用 plistlib 但 FMT_XML 检测
        head = data[:32]
        if not (head.startswith(b"<?xml") or head.startswith(b"<plist")):
            self.errors.append(
                f"file is NOT XML plist (head={head[:16]!r}); "
                f"NSDictionary dictionaryWithContentsOfURL: requires XML plist"
            )
            return False

        try:
            # 必须显式 fmt=plistlib.FMT_XML,匹配 Mousecape 的解析路径
            d = plistlib.loads(data, fmt=plistlib.FMT_XML)
        except Exception as e:
            self.errors.append(f"XML plist parse failed: {e}")
            return False

        # ---- Step 2: _readFromDictionary 顶层字段 ----
        if not isinstance(d, dict):
            self.errors.append(f"top-level not a dict: {type(d).__name__}")
            return False
        if not d:
            self.errors.append("top-level dict is empty")
            return False

        # identifier 必须非空(L193) - 支持新旧键名
        identifier = d.get(MCCURSOR_DICTIONARY_IDENTIFIER_KEY) or d.get("Identifier")
        if not identifier or not isinstance(identifier, str):
            self.errors.append(
                f"Identifier is empty or not a string: {identifier!r}"
            )
            return False
        self.info.append(f"Identifier = {identifier!r}")

        # minimumVersion 检查(L202): 超过 parser version 则拒绝 - 支持新旧键名
        min_v = d.get(MCCURSOR_DICTIONARY_MINIMUM_VERSION_KEY) or d.get("MinimumVersion")
        parser_v = 2.0
        if not isinstance(min_v, (int, float)):
            self.warnings.append(
                f"MinimumVersion not a number: {min_v!r}; will be treated as 0"
            )
        elif min_v > parser_v:
            self.errors.append(
                f"MinimumVersion {min_v} > parser {parser_v}; Mousecape will refuse"
            )
            return False

        # Cursors dict - 支持新旧键名
        cursor_d = d.get(MCCURSOR_DICTIONARY_CURSORS_KEY) or d.get("Cursors")
        if not isinstance(cursor_d, dict):
            self.errors.append(f"Cursors is not a dict: {type(cursor_d).__name__}")
            return False
        if not cursor_d:
            self.warnings.append("Cursors dict is empty")
        self.info.append(f"top-level: {len(cursor_d)} cursors")

        # ---- Step 3: addCursorsFromDictionary ----
        for cid, cdict in cursor_d.items():
            self._validate_cursor(cid, cdict)

        return not self.errors

    def _validate_cursor(self, cid: Any, cdict: Any) -> None:
        """MCCursor.m -_readFromDictionary 的 v2.0 分支"""
        if not isinstance(cdict, dict):
            self.errors.append(f"cursor {cid}: not a dict")
            return

        # 辅助函数：获取键值，支持新旧键名
        def _get_key(orig_key, new_key):
            return cdict.get(new_key) or cdict.get(orig_key)

        # L96 必填字段检查 - 支持新旧键名
        # 检查是否至少有一套完整的键（旧或新）
        has_old_keys = all(k in cdict for k in (
            "FrameCount", "FrameDuration", "HotSpotX", "HotSpotY",
            "PointsWide", "PointsHigh", "Representations"
        ))
        has_new_keys = all(k in cdict for k in self.CURSOR_KEYS)
        
        if not has_old_keys and not has_new_keys:
            # 尝试找出缺失的字段
            missing = []
            for old_key, new_key in zip(
                ("FrameCount", "FrameDuration", "HotSpotX", "HotSpotY",
                 "PointsWide", "PointsHigh", "Representations"),
                self.CURSOR_KEYS
            ):
                if old_key not in cdict and new_key not in cdict:
                    missing.append(f"{old_key}/{new_key}")
            self.errors.append(f"cursor {cid}: missing {missing}")
            return

        # L98-100 类型/值校验
        fc = _get_key("FrameCount", MCCURSOR_DICTIONARY_FRAMECOUNT_KEY)
        if not isinstance(fc, int) or fc < MIN_FRAME_COUNT:
            self.errors.append(f"cursor {cid}: FrameCount invalid: {fc!r}")
            return

        # ⚠️ 关键: Mousecape mousecloak/apply.m L16 硬性检查
        #   if (frameCount > 24 || frameCount < 1) { NSLog "out of range"; return NO; }
        # 超过 24 帧直接拒绝 import, 整批 cursor 全部失败.
        # (Bibata-Original-Classic 的 wait/left_ptr_watch/progress 等动画 cursor
        #  file 内部 ntoc 字段被填成 2 倍, 不去重的话 FrameCount 会变 54.)
        if fc > MAX_FRAME_COUNT:
            self.errors.append(
                f"cursor {cid}: FrameCount {fc} > {MAX_FRAME_COUNT} (Mousecape apply.m L16 "
                f"硬限制). 这通常是 xcursor file 内部有重复 frame (ntoc 写错 "
                f"或 inline 多份), reader 需做 image content dedup."
            )
            return

        fd = _get_key("FrameDuration", MCCURSOR_DICTIONARY_FRAMEDURATION_KEY)
        if not isinstance(fd, (int, float)) or fd <= 0:
            self.errors.append(f"cursor {cid}: FrameDuration invalid: {fd!r}")
            return

        # 热点坐标
        hot_x = _get_key("HotSpotX", MCCURSOR_DICTIONARY_HOTSPOTX_KEY)
        hot_y = _get_key("HotSpotY", MCCURSOR_DICTIONARY_HOTSPOTY_KEY)
        for k, v in [("HotSpotX", hot_x), ("HotSpotY", hot_y)]:
            if not isinstance(v, (int, float)) or v < 0:
                self.errors.append(f"cursor {cid}: {k} invalid: {v!r}")
                return

        # 尺寸
        points_w = float(_get_key("PointsWide", MCCURSOR_DICTIONARY_POINTSWIDE_KEY))
        points_h = float(_get_key("PointsHigh", MCCURSOR_DICTIONARY_POINTSHIGH_KEY))
        for k, v in [("PointsWide", points_w), ("PointsHigh", points_h)]:
            if not isinstance(v, (int, float)) or v <= 0:
                self.errors.append(f"cursor {cid}: {k} invalid: {v!r}")
                return

        reps = _get_key("Representations", MCCURSOR_DICTIONARY_REPRESENTATIONS_KEY)
        if not isinstance(reps, list) or not reps:
            self.errors.append(f"cursor {cid}: Representations empty or not list")
            return

        # L103-109 模拟 rep 处理循环
        rep_storage: dict[int, dict] = {}  # 模拟 self.representations
        first_size_auto: tuple[float, float] | None = None
        scales_seen: set[int] = set()

        for i, data in enumerate(reps):
            # L105 NSBitmapImageRep initWithData: -> PIL decode
            if not isinstance(data, bytes):
                self.errors.append(f"cursor {cid}: rep[{i}] not bytes")
                continue
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception as e:
                self.errors.append(
                    f"cursor {cid}: rep[{i}] PNG/TIFF decode failed: {e}"
                )
                continue

            pix_w, pix_h = img.size

            # L108 setRepresentation: -> cursorScaleForScale
            if points_w <= 0:
                self.errors.append(
                    f"cursor {cid}: PointsWide <= 0, can't compute scale"
                )
                continue
            scale = pix_w / points_w
            mcc_scale = cursor_scale_for_scale(scale)
            if mcc_scale == MCCURSOR_SCALE_NONE:
                self.errors.append(
                    f"cursor {cid}: rep[{i}] scale {scale} < 0 (MCCURSOR_SCALE_NONE)"
                )
                continue
            scales_seen.add(mcc_scale)
            rep_storage[mcc_scale] = {
                "pixels": (pix_w, pix_h),
                "raw": data,
            }

            # L194 setRepresentation 内的 size auto-compute
            # (只在 self.representations.count == 1 时触发,即第一个 rep)
            if len(rep_storage) == 1:
                auto_w = pix_w / (mcc_scale / 100.0)
                auto_h = pix_h / fc / (mcc_scale / 100.0)
                if auto_w > 0 and auto_h > 0:
                    first_size_auto = (auto_w, auto_h)

        # L111 覆写 self.size 为 pointsWide/pointsHigh(无论 auto size 是什么)
        # 这个 size 才是最终生效的

        # ---- 维度一致性检查 ----
        # 真实约束 (从 MCCursor.m L194-198 setRepresentation 解读):
        #   rep.pixelsWide  = pointsWide * scale
        #   rep.pixelsHigh  = pointsHigh * scale * frameCount
        # 因为 setRepresentation 解读时:
        #   size.h = (rep.pixelsHigh / frameCount) / scale
        #         = pointsHigh
        for mcc_scale, info in rep_storage.items():
            pix_w, pix_h = info["pixels"]
            scale_x = mcc_scale / 100.0
            expected_h = points_h * scale_x * fc
            if abs(pix_h - expected_h) > 0.5:
                self.errors.append(
                    f"cursor {cid}: rep[scale={mcc_scale}] height {pix_h} != "
                    f"PointsHigh({points_h}) * scale({scale_x}) * FrameCount({fc}) = {expected_h}"
                )
            # rep width 必须是 points_w 的整数倍
            if abs(pix_w / points_w - round(pix_w / points_w)) > 0.01:
                self.warnings.append(
                    f"cursor {cid}: rep[scale={mcc_scale}] width {pix_w} / "
                    f"PointsWide({points_w}) = {pix_w / points_w:.3f} (not integer)"
                )

        # 必须有 @1x (MCCURSOR_SCALE_100)
        if MCCURSOR_SCALE_100 not in scales_seen:
            self.warnings.append(
                f"cursor {cid}: no @1x (scale={MCCURSOR_SCALE_100}) rep; scales seen: {sorted(scales_seen)}"
            )

        # FrameDuration 警告: 静态光标 (FrameCount=1) FrameDuration 不应有意义
        # 但真实 .cape 都给 1.0,所以这里只警告动画光标 delay 异常的情况
        if fc > 1 and fd > 1.0:
            self.warnings.append(
                f"cursor {cid}: FrameDuration {fd}s for {fc}-frame animation "
                f"seems too slow (>1s); macOS may not animate properly"
            )

    def report(self) -> str:
        lines = [f"=== Validating: {self.path.name} ==="]
        for line in self.info:
            lines.append(f"  · {line}")
        if self.errors:
            lines.append(f"\n  ✗ {len(self.errors)} ERROR(S) -- Mousecape will reject:")
            for e in self.errors:
                lines.append(f"    - {e}")
        if self.warnings:
            lines.append(f"\n  ⚠ {len(self.warnings)} warning(s):")
            for w in self.warnings:
                lines.append(f"    - {w}")
        if not self.errors and not self.warnings:
            lines.append("\n  ✓ All checks passed - file is Mousecape-compatible")
        return "\n".join(lines)
