import os
import pathlib
import shutil
import struct
import subprocess
import tarfile
import zipfile
from collections import defaultdict
from pathlib import Path
from core.cim import Cursor, CursorFrame


def _make_case_insensitive_safe_symlink_to(orig):
    """
    返回一个 pathlib.PosixPath.symlink_to 的安全包装, 用于规避 macOS (APFS/HFS+
    默认 case-insensitive) 上 7z 包内"大小写冲突 entry"导致的 FileExistsError.

    触发场景:
      7z 包内同时存在 'sizenesw_down' (小写) 和 'SizeNESW_Down' (大写) 两个
      symlink entry, 它们都指向同一个 target. 在 case-insensitive 文件系统上,
      这两个 entry 解压到同一路径, 第二个解压调用 os.symlink 报 FileExistsError
      [Errno 17].

    行为:
      - 第一次直接调用 orig (正常路径, 无性能损失).
      - 仅当抛 FileExistsError 且 self (即 dst 位置) 已被一个**不同 target 的
        旧 symlink** 占用时, 才 unlink 旧 symlink 并重试.
      - **绝不删除普通文件** (避免误删用户数据), 这种情况让原始错误抛出.
      - 如果旧 symlink 的 target 与新 target 相同 (说明已经是想要的 symlink),
        也不 unlink, 直接重试 (通常会再次报 FileExistsError, 让上游感知).

    Args:
        orig: 原 pathlib.PosixPath.symlink_to (将被装饰)

    Returns:
        装饰后的函数, 签名与 orig 兼容.
    """

    def _safe_symlink_to(self, target, target_is_directory=False):
        # ---- 预防: 跳过 self-loop symlink (7z 包内 'arrow_down' -> 'arrow_down'
        # 这类故意自循环的 placeholder). 正常创建后, 后续 py7zr 调 os.utime() 时
        # 会 ELOOP [Errno 62]. 直接跳过这种 entry 即可.
        try:
            target_str = os.fspath(target)
        except TypeError:
            target_str = str(target)
        if target_str:
            target_abs = (
                self.parent / target_str
                if not os.path.isabs(target_str)
                else pathlib.Path(target_str)
            )
            if str(target_abs) == str(self):
                return  # self-loop, 静默跳过
        try:
            return orig(self, target, target_is_directory)
        except FileExistsError:
            # 仅在 self 已是 symlink (无论 target 是否相同) 时, 视为 case-insensitive
            # 冲突. 7z 包内常出现 "sizenesw_down" 和 "SizeNESW_Down" 两个 symlink
            # entry 都指向同一 target 的情况, 在 case-insensitive 文件系统上, 它们
            # 在磁盘上是同一个文件, 第二个 os.symlink 必须先 unlink 才能写入.
            # 严格的安全保证: 如果 self 不是 symlink 而是普通文件, 绝不 unlink,
            # 让原始 FileExistsError 透传, 避免误删用户数据.
            try:
                if self.is_symlink():
                    self.unlink()
                    return orig(self, target, target_is_directory)
            except OSError:
                # readlink/unlink 自身失败 (例如权限), 让原始错误透传
                pass
            raise

    return _safe_symlink_to


def _make_eloop_safe(orig):
    """
    返回一个 syscall 的安全包装, 用于在 self-loop symlink (7z 包内
    'arrow_down' -> 'arrow_down' 这类故意自循环的 placeholder) 上 ELOOP 时
    静默跳过, 不影响其他正常调用.

    触发场景:
      py7zr 解压每个 entry 后调 os.utime() / os.chmod() 等保留元数据.
      当 outfilename 是 self-loop symlink, 内核跟随解析会无限循环, 报
      OSError [Errno 62] Too many levels of symbolic links.

    行为:
      - 正常路径直接调 orig (无性能损失).
      - 仅当 errno == ELOOP (62) 时静默 return, 其他错误透传.
      - 任何 FileNotFoundError 等也透传 (不掩盖其他问题).

    Args:
        orig: 原 syscall (将被装饰, 任意签名)

    Returns:
        装饰后的函数, 签名与 orig 兼容.
    """

    def _safe(*args, **kwargs):
        try:
            return orig(*args, **kwargs)
        except OSError as e:
            if getattr(e, "errno", None) == 62:  # ELOOP
                return  # self-loop symlink, 静默跳过
            raise

    return _safe


def _reset_extracted_root(extracted_root: Path) -> None:
    """
    在解压前清理 extracted_root 下的旧内容,避免上次中断/失败留下的文件导致
    重跑时 py7zr / zipfile / tarfile 抛 FileExistsError 等冲突错误.

    设计:
      - 保留任何名为 "decoded" 的目录(里面是 read_xcursor 写出的 PNG 中间缓存,
        重跑时 read_xcursor 会**覆盖式**写入,所以理论上可删;但保留更安全,
        也避免极端情况下其他人手工加进来的产物被误删).
      - 其他文件和目录一律删除,确保解压目标目录是干净状态.

    Args:
        extracted_root: 即将被解压覆盖的目录(可能不存在,也可能存在并含残留)
    """
    if not extracted_root.exists():
        return
    for p in extracted_root.iterdir():
        # 保留 decoded/ 目录作为 PNG 缓存
        if p.name == "decoded" and p.is_dir():
            continue
        try:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
        except FileNotFoundError:
            # 竞态: iterdir 之后文件被外部删除, 忽略
            pass


# XCursor 二进制格式常量
# 文件头: "Xcur" 魔数 + 头大小(16) + 版本(0x00010000) + TOC 条目数
_XCUR_MAGIC = b"Xcur"
_XCUR_HEADER_SIZE = 16
_XCUR_TOC_ENTRY_SIZE = 12

# TOC 中 type 字段
_TYPE_IMAGE = 0xFFFD0002  # 单张图块(实际数据是带 36 字节 image header 的 ARGB 像素)

# 单个 image 块的头部大小
_IMAGE_HEADER_SIZE = 36

# 支持自动解压的压缩包后缀(全部小写比对)
# 7z 优先级放最后, 因为 py7zr 不在标准库 (需 pip install py7zr)
_ARCHIVE_SUFFIXES = (
    ".tar.xz",
    ".tar.gz",
    ".tgz",
    ".zip",
    ".tar",
    ".tar.bz2",
    ".tbz2",
    ".7z",
)


def _extract_7z(theme_path: Path, extracted_root: Path) -> None:
    """
    解压 7z 压缩包到 extracted_root.

    优先使用 py7zr (纯 Python 实现), 如果不可用则回退到系统 7z 命令.

    Args:
        theme_path: 7z 文件路径
        extracted_root: 解压目标目录

    Raises:
        RuntimeError: py7zr 和系统 7z 都不可用时抛出
    """
    # 方案 1: py7zr (纯 Python, 推荐)
    try:
        import py7zr  # type: ignore
        from py7zr import py7zr as _py7zr_mod  # type: ignore

        # ---- monkey-patch 1: 强制 py7zr 走串行解压路径 ----
        # py7zr.SevenZipFile._extract() 内部硬编码
        #   parallel=(not self.password_protected and not self._filePassed)
        # 当 7z 包不含密码时, 默认是 True (多线程并行解压).
        # py7zr 1.1.0 的 extractall() 没暴露 parallel 参数, 没法从外部关并行.
        # 直接 patch Worker.extract 让 parallel 永远为 False, 走 extract_single
        # 串行路径, 避免 worker 之间的竞态 (例如 A 写 SizeNESW_Down 普通文件
        # 与 B 创建 top_right_corner symlink 指向 SizeNESW_Down 的竞争).
        if not getattr(_py7zr_mod.Worker.extract, "_patched_serial", False):
            _orig_worker_extract = _py7zr_mod.Worker.extract

            def _serial_worker_extract(self, fp, path, parallel, *args, **kwargs):
                return _orig_worker_extract(self, fp, path, False, *args, **kwargs)

            _serial_worker_extract._patched_serial = True  # type: ignore
            _py7zr_mod.Worker.extract = _serial_worker_extract

        # ---- monkey-patch 2: 解决 macOS 大小写不敏感文件系统的"7z entry
        # 大小写冲突"问题 ----
        # 背景: microzoa.7z 包内同时存在 'sizenesw_down' (小写) 和
        # 'SizeNESW_Down' (大写) 两个 entry, 都是 symlink → 'top_right_corner'.
        # Linux 上是两个不同文件, 但 macOS 的 APFS/HFS+ 默认是 case-insensitive,
        # 这两个路径在文件系统层被视为同一个文件. py7zr 按 entry 顺序解压时:
        #   1. 先解压 'sizenesw_down' → 创建 symlink 成功
        #   2. 后解压 'SizeNESW_Down' → os.symlink 报 FileExistsError [Errno 17]
        # 因为 macOS 把 'SizeNESW_Down' 视为已存在的 'sizenesw_down'.
        #
        # 修复: 临时 patch pathlib.PosixPath.symlink_to, 在遇到 FileExistsError
        # 时检查 self 位置是否已被一个**旧 symlink** 占用 (即大小写冲突的
        # case-insensitive 重复). 如果是, 安全地 unlink 后重试.
        # **安全保证**: 仅当 self 已经是 symlink 才 unlink, 绝不删除普通文件
        # (避免误删用户数据).
        #
        # 此外, 7z 包内经常含 "self-loop symlink" (e.g. 'arrow_down' -> 'arrow_down'
        # 这种故意自循环的占位 entry). py7zr 解压后调 os.utime() / os.chmod() 保留
        # 元数据时, 在 self-loop symlink 上会 ELOOP [Errno 62]. 同时临时 patch 这些
        # syscall, 在 ELOOP 时静默跳过, 不影响其他正常调用.
        # 全部 patch 都用 try/finally 在解压结束后恢复, 不污染进程内其他调用.
        _orig_symlink_to = pathlib.PosixPath.symlink_to
        _patched_symlink_to = _make_case_insensitive_safe_symlink_to(_orig_symlink_to)
        # 包装 ELOOP 敏感 syscall: utime / chmod 等默认 follow_symlinks=True,
        # 在 self-loop symlink 上会 ELOOP. chown / getxattr / setxattr 同理,
        # 先把已确认出问题的加上, 后续如发现新问题再追加.
        _eloop_safe_names = ("utime", "chmod")
        _orig_safe = {n: getattr(os, n) for n in _eloop_safe_names}
        _patched_safe = {n: _make_eloop_safe(orig) for n, orig in _orig_safe.items()}
        pathlib.PosixPath.symlink_to = _patched_symlink_to  # type: ignore
        for n, fn in _patched_safe.items():
            setattr(os, n, fn)  # type: ignore
        try:
            with py7zr.SevenZipFile(theme_path, mode="r") as z:
                z.extractall(path=extracted_root)
        finally:
            pathlib.PosixPath.symlink_to = _orig_symlink_to  # type: ignore
            for n, fn in _orig_safe.items():
                setattr(os, n, fn)  # type: ignore
        return
    except ImportError:
        pass  # py7zr 未安装, 回退到方案 2
    except Exception as e:
        raise RuntimeError(f"py7zr failed to extract {theme_path}: {e}") from e

    # 方案 2: 系统 7z 命令
    for cmd in ("7z", "7za", "7zr"):
        try:
            # 使用 -o<path> 语法指定输出目录 (注意 7z 的 -o 后面无空格)
            subprocess.run(
                [cmd, "x", str(theme_path), f"-o{extracted_root}", "-y"],
                check=True,
                capture_output=True,
            )
            return
        except FileNotFoundError:
            continue  # 尝试下一个命令
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            raise RuntimeError(
                f"{cmd} failed to extract {theme_path}: {stderr}"
            ) from e

    # 方案 1 和 2 都失败
    raise RuntimeError(
        f"Cannot extract 7z file {theme_path}: "
        "py7zr not installed and no system 7z command found. "
        "Install py7zr: pip3 install --user py7zr, "
        "or install p7zip: brew install p7zip (macOS) / apt install p7zip-full (Linux)."
    )


def _parse_xcursor_bytes(data: bytes):
    """
    纯 Python 解析 XCursor 字节流，提取所有内嵌图像帧并分配 frame_index。

    每个 TOC 条目 type=0xFFFD0002 对应一个 image 块，结构如下：
        image_header (36 字节):
            header_size(4) | type(4) | nominal_size(4) | version(4) |
            width(4) | height(4) | xhot(4) | yhot(4) | delay(4)
        pixels: width * height * 4 字节 BGRA(pre-multiplied alpha, 小端序)

    重要: 一个 xcursor 文件里同一个 (width, height) 尺寸下若出现 N 个 image 块，
    它们就是同一尺寸下的 N 个动画帧(N=1 即静态光标)。
    frame_index 由 (width, height) 分组后在文件 position 顺序中的 rank 决定，
    与 X11 xcursorgen 工具的输出顺序一致(无论是 frame-major 还是 size-major 都成立)。

    返回 [{nominal_size,width,height,xhot,yhot,delay,frame_index,pixels_bgra}, ...]
    按 (nominal_size, frame_index) 升序排列。
    """
    # 校验魔数和最小长度
    if len(data) < _XCUR_HEADER_SIZE or data[:4] != _XCUR_MAGIC:
        raise ValueError("not a valid xcursor file")

    # 解析 TOC
    toc_count = struct.unpack_from("<I", data, 12)[0]
    entries = []
    for i in range(toc_count):
        offset = _XCUR_HEADER_SIZE + i * _XCUR_TOC_ENTRY_SIZE
        if offset + _XCUR_TOC_ENTRY_SIZE > len(data):
            break
        type_code = struct.unpack_from("<I", data, offset)[0]
        nominal_size = struct.unpack_from("<I", data, offset + 4)[0]
        pos = struct.unpack_from("<I", data, offset + 8)[0]
        entries.append((type_code, nominal_size, pos))

    # 按 position 排序后才是文件实际顺序
    entries.sort(key=lambda e: e[2])

    # 先按 (width, height) 分桶: 同一桶里的条目是该尺寸下的若干动画帧
    buckets = defaultdict(list)
    for type_code, nominal_size, pos in entries:
        if type_code != _TYPE_IMAGE:
            continue
        if pos + _IMAGE_HEADER_SIZE > len(data):
            continue
        # 解析 image header (9 个 uint32)
        (header_size, _t, _subtype, _version, width, height, xhot, yhot, delay) = (
            struct.unpack_from("<IIIIIIIII", data, pos)
        )
        # 容错: 实际 header_size 可能不是 36，按实际值取
        actual_header = (
            header_size if header_size >= _IMAGE_HEADER_SIZE else _IMAGE_HEADER_SIZE
        )
        pixel_start = pos + actual_header
        pixel_size = width * height * 4
        if pixel_start + pixel_size > len(data):
            continue
        buckets[(width, height)].append(
            {
                "nominal_size": nominal_size,
                "width": width,
                "height": height,
                "xhot": xhot,
                "yhot": yhot,
                "delay": delay,
                "pixels_bgra": data[pixel_start : pixel_start + pixel_size],
            }
        )

    # 同一桶内的 position 顺序就是动画帧顺序 -> 直接 assign frame_index
    #
    # 关键处理: Mousecape 硬限制 frameCount ≤ 24 (apply.m L16).
    # Bibata wait 真实是 54 帧动画 (设计如此, 2 轮 27 帧循环),
    # 必须均匀 subsample 到 ≤ 24 帧, 同时按比例放大 delay 保持循环总时长不变.

    # Mousecape mousecloak/apply.m L16:
    #   if (frameCount > 24 || frameCount < 1) { return NO; }
    MAX_MOUSECAPE_FRAMES = 24

    frames: list[dict] = []
    for (_w, _h), group in buckets.items():
        n = len(group)
        if n > MAX_MOUSECAPE_FRAMES:
            # 均匀采样: [0, 1*(n-1)/(k-1), 2*(n-1)/(k-1), ..., (k-1)*(n-1)/(k-1)]
            k = MAX_MOUSECAPE_FRAMES
            indices = sorted(
                {int(round(i * (n - 1) / (k - 1))) for i in range(k)}
            )
            sampled = [group[i] for i in indices]
            # 按比例放大 delay: 保留循环总时长不变
            scale = n / k
            for info in sampled:
                new_info = dict(info)
                if new_info["delay"] > 0:
                    new_info["delay"] = int(round(new_info["delay"] * scale))
                frames.append(new_info)
        else:
            for info in group:
                frames.append(dict(info))

    # 重新按 (size, frame_index) 排序并规范化 frame_index
    frames.sort(key=lambda f: (f["nominal_size"], f.get("frame_index", 0)))
    # 重新 assign frame_index (按 size 桶内顺序)
    by_size: dict[tuple[int, int], int] = {}
    for f in frames:
        k = (f["width"], f["height"])
        f["frame_index"] = by_size.get(k, 0)
        by_size[k] = f["frame_index"] + 1
    return frames


def _bgra_to_rgba_png(
    pixels_bgra: bytes, width: int, height: int, out_path: Path
) -> None:
    """
    把 XCursor 存储的 pre-multiplied BGRA 像素转成不 pre-multiply 的 RGBA PNG 写入 out_path。
    使用 numpy 向量化做 un-premultiply + 通道重排。
    """
    import numpy as np
    from PIL import Image

    arr = np.frombuffer(pixels_bgra, dtype=np.uint8).reshape(height, width, 4)
    # 拆分通道 (BGRA)
    b = arr[..., 0].astype(np.uint16)
    g = arr[..., 1].astype(np.uint16)
    r = arr[..., 2].astype(np.uint16)
    a = arr[..., 3].astype(np.uint16)

    # Un-premultiply alpha: 当 a==0 时直接置 0，避免除零
    safe_a = np.where(a == 0, 1, a)
    r = np.minimum((r * 255 + safe_a // 2) // safe_a, 255).astype(np.uint8)
    g = np.minimum((g * 255 + safe_a // 2) // safe_a, 255).astype(np.uint8)
    b = np.minimum((b * 255 + safe_a // 2) // safe_a, 255).astype(np.uint8)

    rgba = np.dstack([r, g, b, a.astype(np.uint8)])
    img = Image.fromarray(rgba, mode="RGBA")
    img.save(out_path, format="PNG")


def read_xcursor(file: Path) -> Cursor:
    """
    解析单个 XCursor 文件，提取其中的图像帧并写到
    file.parent / "decoded" / file.stem / 目录下（PNG 格式）。

    这是替换原 subprocess 调用 xcursortocursor 的纯 Python 实现，
    不依赖任何外部命令行工具，仅依赖 Pillow + numpy。
    """
    out_dir = file.parent / "decoded" / file.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(file, "rb") as f:
        data = f.read()

    frames_info = _parse_xcursor_bytes(data)

    frames = []
    for info in frames_info:
        # 文件名编码两个维度: 尺寸 + 该尺寸下的帧序号
        # 例如 32_0.png (32x32 尺寸第 0 帧), 32_1.png (第 1 帧) ...
        # 静态光标每个尺寸只有一帧, 就是 {size}_0.png
        out_path = out_dir / f"{info['nominal_size']}_{info['frame_index']}.png"
        _bgra_to_rgba_png(
            info["pixels_bgra"],
            info["width"],
            info["height"],
            out_path,
        )
        # hotspot 真实值来自 xcursor 文件的 xhot/yhot 字段
        frames.append(
            CursorFrame(
                image_path=str(out_path),
                hotspot=(info["xhot"], info["yhot"]),
                delay=float(info["delay"]),
                width=info["width"],
                height=info["height"],
                frame_index=info["frame_index"],
                nominal_size=info["nominal_size"],
            )
        )

    return Cursor(file.stem, frames, path=str(file))


def _is_archive(path: Path) -> bool:
    """判断 path 是否为支持的压缩包。"""
    if not path.is_file():
        return False
    return path.name.lower().endswith(_ARCHIVE_SUFFIXES)


def _find_cursor_dirs(root: Path) -> list[Path]:
    """
    找根目录下所有的 cursors 子目录.
    规则 (XCursor 规范 + 常见变体):
      - 找名为 'cursors' 的目录 (标准名, 最常见)
      - 也找 'cursors_scalable', 'cursors_pixmap', 'cursors_svg',
        'cursors_left', 'cursors_right' 等 XCursor 规范变体
        (X11 XCursor 主题规范允许任意 cursors* 前缀目录)
      - **深度限制**: 只看 cursor 集合目录本身 (即 cursors/ 或 cursors_*/),
        不看它们里面的子目录 (e.g. cursors_scalable/alias/ 不是 cursor 目录)
      - 排除 decoded/ 内部 (read_xcursor 生成的中间目录)
      - **优先级**: 如果主题同时含 cursors/ 和 cursors_scalable/,
        优先用 cursors_scalable (更高质量), 把 cursors 当 fallback
    返回按"优先级"排序的 Path 列表 (scalable 在前, cursors 在后).
    """
    cursors_dirs: list[Path] = []
    for d in root.rglob('*'):
        if not d.is_dir():
            continue
        # 只匹配名为 'cursors' 或 'cursors_*' 的"集合目录"
        if d.name == 'cursors':
            cursors_dirs.append(d)
            continue
        if d.name.startswith('cursors_') and len(d.name) > len('cursors'):
            cursors_dirs.append(d)
            continue
        # decoded/ 内部排除
        if 'decoded' in d.parts:
            continue
        # 其他目录都不是 cursor 集合目录, 跳过

    # **优先级排序**: scalable > pixmap > svg > cursors > 其他变体
    # scalable 优先 (高 DPI), 然后是 cursors 标准 (作为 fallback 备份)
    def _priority_key(d: Path) -> tuple:
        # scalable 最高优先级 (数字最小 = 排最前)
        if d.name == 'cursors_scalable':
            return (0, str(d))
        if d.name == 'cursors_pixmap':
            return (1, str(d))
        if d.name == 'cursors_svg':
            return (2, str(d))
        if d.name == 'cursors':
            return (3, str(d))
        # 其他 cursors_ 变体
        return (4, str(d))

    return sorted(cursors_dirs, key=_priority_key)


def _cursor_dir_fingerprint(cd: Path) -> str:
    """
    计算一个 cursors/ 目录的内容指纹 (SHA-256).
    指纹算法:
      - 收集所有非 dotfile, 非 symlink 的 xcursor 真实文件
      - 跳过 symlink (它们指向其他真实文件, 已包含)
      - 对每个真实文件: (相对路径, size, sha256(content)) 元组
      - 排序后拼接, 再 hash 一次

    两个 cursors/ 目录如果内容完全相同, 指纹相同;
    内容不同 (哪怕一个文件差 1 字节), 指纹不同.

    返回: hex 指纹字符串.
    """
    import hashlib
    files_info: list[tuple[str, int, str]] = []
    for p in sorted(cd.iterdir()):
        if p.name.startswith('.'):
            continue
        if p.is_symlink():
            continue  # symlink 指向已包含的真实文件
        if not p.is_file():
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        h = hashlib.sha256(data).hexdigest()
        files_info.append((p.name, len(data), h))
    if not files_info:
        return "EMPTY"
    # 拼成 (name,size,sha) 序列, 再整体 hash
    combined = "\n".join(f"{n}|{s}|{h}" for n, s, h in files_info).encode()
    return hashlib.sha256(combined).hexdigest()


def discover_themes(theme_path: Path, out_root: Path = None, merge_similar: bool = True, merge_threshold: float = 0.9) -> list[tuple[str, list]]:
    """
    发现压缩包/目录中的所有 cursor 主题.
    返回 list[(theme_name, [Cursor 列表])].

    策略 (通用规则):
      1. 如果是压缩包: 解压到 out_root/_extracted_<主题名>/
      2. 找所有 cursors/ 子目录
      3. 如果只有 1 个 cursors/: 用压缩包名作为主题名
      4. 如果有多个 cursors/:
         a) 计算每个 cursors/ 的**整体指纹** (SHA-256):
            - 完全相同 → 自动合并为 1 套, 打印警告
         b) 计算每个 cursors/ 的**逐 cursor 相似度**:
            - 对每个 X11 cursor 名, 收集 N 套中各自的 SHA-256
            - 如果 shared cursor 中**完全字节相同**的比例 ≥ merge_threshold (默认 90%):
              - **merge_similar=True** (默认): 自动只保留 1 套 (避免生成几乎相同的 cape),
                打印详细 warning, 列出被合并的子主题
              - **merge_similar=False**: 保留所有 cape 但加标注 (用户主动选择)
    """
    if not theme_path.exists():
        raise FileNotFoundError(f"theme path not found: {theme_path}")

    # ===== CursorFX 早分支 =====
    # Stardock CursorFX 主题包有两种形态:
    #   1) 目录形态: 带 .CursorFX 扩展名的目录(Windows shell compound document),
    #      解压后是含 Scheme.ini + <Section>.png 的扁平目录.
    #   2) 二进制文件形态: Stardock 私有打包格式, 需要用 cursorfx_binary_reader 解析.
    # 与 XCursor 的 `cursors/<name>` 嵌套结构完全不同,需走独立 reader.
    if theme_path.is_dir():
        from core.cursorfx_reader import is_cursorfx_theme, read_cursorfx_theme
        if is_cursorfx_theme(theme_path):
            theme_name, cursors = read_cursorfx_theme(theme_path)
            return [(theme_name, cursors)]
    elif theme_path.is_file() and theme_path.suffix.lower() == ".cursorfx":
        # CursorFX 二进制文件
        from core.cursorfx_reader import is_cursorfx_theme, read_cursorfx_theme
        if is_cursorfx_theme(theme_path):
            theme_name, cursors = read_cursorfx_theme(theme_path)
            return [(theme_name, cursors)]

    extracted_root: Path = None
    if _is_archive(theme_path):
        out_root = Path(out_root) if out_root else theme_path.parent
        out_root.mkdir(parents=True, exist_ok=True)
        name = theme_path.name
        lower = name.lower()
        archive_theme_name = name
        for ext in _ARCHIVE_SUFFIXES:
            if lower.endswith(ext):
                archive_theme_name = name[: -len(ext)]
                break
        extracted_root = out_root / f"_extracted_{archive_theme_name}"
        extracted_root.mkdir(parents=True, exist_ok=True)
        # 解压前先清理上次残留的文件,避免重跑时 FileExistsError 冲突
        # (例如 microzoa.7z 上次解压到一半中断,留下了部分 cursors/ 文件 + symlink,
        #  py7zr 再次解压时遇到 symlink 目标已存在就抛 FileExistsError)
        _reset_extracted_root(extracted_root)
        if theme_path.name.lower().endswith(".zip"):
            with zipfile.ZipFile(theme_path) as zf:
                zf.extractall(extracted_root)
        elif theme_path.name.lower().endswith(".7z"):
            # 7z 解压: 优先 py7zr, 回退到系统 7z 命令
            _extract_7z(theme_path, extracted_root)
        else:
            # Python 3.14+ tarfile 默认 data filter 会拒绝:
            #   1) symlink 指向绝对路径 (AbsoluteLinkError)
            #   2) symlink 跳出目标目录 (LinkOutsideDestinationError)
            #   3) symlink 自身形成循环 (Too many levels of symbolic links)
            # 但 XCursor 主题里经常出现 (例如 silver-arrow-cursor 的 x_cursor
            # 自循环, Skyrim 主题的 sb_down_arrow 绝对路径 symlink).
            # 用 'fully_trusted' filter 接受所有, 与旧版 Python 行为一致.
            #
            # 进一步, 解压过程中**逐个 member** 提取并 try/except, 跳过问题
            # symlink (例如自循环 x_cursor 会被 OS 拒绝, 必须跳过).
            try:
                with tarfile.open(theme_path) as tf:
                    try:
                        # 新版 Python 支持 filter 参数
                        skip_count = 0
                        for member in tf.getmembers():
                            try:
                                tf.extract(member, extracted_root, filter="fully_trusted")
                            except (OSError, tarfile.TarError) as e:
                                # 跳过问题 symlink (自循环, 绝对路径, 路径逃逸等)
                                skip_count += 1
                        if skip_count:
                            print(
                                f"  [info] skipped {skip_count} problematic symlink(s) in archive"
                            )
                    except TypeError:
                        # 旧版 Python 不支持 filter 参数
                        tf.extractall(extracted_root)
            except Exception:
                # 最终回退: 让原始异常抛出 (保留可诊断性)
                raise
    elif theme_path.is_dir():
        extracted_root = theme_path
    else:
        # 单个文件
        return [(theme_path.stem, [read_xcursor(theme_path)])]

    # 找所有 cursors/ 目录
    cursors_dirs = _find_cursor_dirs(extracted_root)

    # **SVG 源自动 build** (cursors_scalable/<name>/metadata.json + *.svg)
    # 通用规则: 如果发现 cursors_scalable 目录含 SVG 源 (KDE 主题格式),
    # 自动 build 成 xcursor 二进制, 写到 _extracted_<name>/_built_scalable/
    if cursors_dirs:
        from core.svg_renderer import build_svg_theme
        for cd in cursors_dirs:
            # 检查这个 cd 是 SVG 源目录
            # SVG 源特征: cd 自身**没有** xcursor 二进制文件 (无 'Xcur' 魔数),
            # 但子目录里含 metadata.json (KDE 主题的子目录结构)
            cd_is_xcursor = any(
                p.is_file() and not p.name.startswith('.') and p.read_bytes()[:4] == b"Xcur"
                for p in cd.iterdir() if p.is_file()
            )
            has_svg_subdirs_with_metadata = False
            if not cd_is_xcursor:
                for sub in cd.iterdir():
                    if sub.is_dir() and not sub.name.startswith('.'):
                        if (sub / 'metadata.json').is_file():
                            has_svg_subdirs_with_metadata = True
                            break

            if has_svg_subdirs_with_metadata and not cd_is_xcursor:
                # SVG 源! build 成 xcursor
                built_dir = extracted_root / f"_built_{cd.name}"
                if not built_dir.exists():
                    print(f"  [info] detected SVG source theme at {cd.relative_to(extracted_root)}, auto-building to xcursor...")
                    success, failed, errors = build_svg_theme(cd, built_dir)
                    print(f"    built {success} cursor(s), failed {failed}")
                    if errors:
                        for e in errors[:3]:
                            print(f"    error: {e}")
                # 把 built_dir 也加到 cursors_dirs (作为更高优先级)
                if built_dir.exists() and built_dir not in cursors_dirs:
                    cursors_dirs.append(built_dir)

    if not cursors_dirs:
        # 没有 cursors/ 目录, 当作单套处理
        return [(extracted_root.name, _read_all_cursors(extracted_root))]

    if len(cursors_dirs) == 1:
        # 只有 1 套, 用压缩包/顶层目录名
        cd = cursors_dirs[0]
        rel = cd.parent.relative_to(extracted_root)
        if str(rel) == '.':
            return [(extracted_root.name, _read_all_cursors(cd))]
        else:
            return [(str(rel), _read_all_cursors(cd))]

    # 多套: 1) 整体指纹检测完全相同的子目录
    fingerprints: list[tuple[Path, str, str]] = []  # (cd, theme_name, fingerprint)
    for cd in cursors_dirs:
        rel = cd.parent.relative_to(extracted_root)
        if str(rel) == '.':
            theme_name = extracted_root.name
        else:
            theme_name = str(rel).replace('/', '_')
        fp = _cursor_dir_fingerprint(cd)
        fingerprints.append((cd, theme_name, fp))

    # 按整体指纹分组, 完全相同合并
    seen_fps: dict[str, str] = {}  # fp -> first theme_name
    fully_dup_groups: list[tuple[str, list[str]]] = []
    for cd, theme_name, fp in fingerprints:
        if fp in seen_fps:
            kept = seen_fps[fp]
            for grp in fully_dup_groups:
                if grp[0] == kept:
                    grp[1].append(theme_name)
                    break
            else:
                fully_dup_groups.append((kept, [theme_name]))
            continue
        seen_fps[fp] = theme_name

    # 2) 逐 cursor 相似度检测 (N 套之间)
    # 对每个 X11 cursor 名, 收集 N 套中各自的 SHA-256
    cursor_hash_matrix: dict[str, dict[str, str]] = {}  # {x11_name: {theme_name: sha256}}
    for cd, theme_name, fp in fingerprints:
        for p in cd.iterdir():
            if p.name.startswith('.') or p.is_symlink() or not p.is_file():
                continue
            try:
                data = p.read_bytes()
            except OSError:
                continue
            import hashlib
            cursor_hash_matrix.setdefault(p.name, {})[theme_name] = hashlib.sha256(data).hexdigest()

    # 找出"绝大多数套里这个 cursor 字节相同"的 cursor
    near_dup_report: list[str] = []
    total_themes = len(fingerprints)
    for x11_name, thashes in cursor_hash_matrix.items():
        if len(thashes) < total_themes:
            # 不是所有套都有这个 cursor, 跳过
            continue
        unique_hashes = set(thashes.values())
        if len(unique_hashes) == 1:
            # 完全相同
            continue
        # 找出"主流" hash (出现最多的)
        from collections import Counter
        c = Counter(thashes.values())
        most_common_hash, _ = c.most_common(1)[0]
        same_count = sum(1 for h in thashes.values() if h == most_common_hash)
        # 如果多数套这个 cursor 相同
        if same_count >= total_themes * 0.9:
            near_dup_report.append(x11_name)

    # 打印警告
    if fully_dup_groups:
        print(f"  [warn] detected {len(fully_dup_groups)} group(s) of fully-identical sub-theme(s):")
        for kept, dups in fully_dup_groups:
            print(f"    keeping '{kept}' (skipping identical copies: {', '.join(dups)})")

    # 计算"绝大多数 shared cursor 在 N 套中完全字节相同"
    same_cursor_count = sum(1 for x11 in cursor_hash_matrix
                            if len(cursor_hash_matrix[x11]) == total_themes
                            and len(set(cursor_hash_matrix[x11].values())) == 1)
    total_shared = sum(1 for x11 in cursor_hash_matrix if len(cursor_hash_matrix[x11]) == total_themes)

    # **通用规则 (最终版)**: 永远按子主题名输出 N 个 cape
    # 核心原则:
    #   - **N 套 → N cape** (用户明确要求"几套输出几个")
    #   - 绝不"自动合并"伪多套 (用户多次报怨"只输出一个" / "生成的一样")
    #   - 唯一例外: **完全相同**的子主题 (100% 字节相同, Layer 1 整体指纹) 才合并
    #   - 高相似度 (≥90% 但不全相同) **不合并**, 仍输出 N 个 cape
    #
    # 设计哲学:
    #   - 主题包可能含 N 套子主题 (e.g. "Blue", "Green", "Yellow" 颜色变种)
    #   - 主题作者可能没真正提供 N 套不同图片 (e.g. 只改了 wait 帧, 其他复制)
    #   - **这是主题包作者的问题, 不是工具的问题**
    #   - 工具应**忠实**反映主题包结构, 总是输出 N 个 cape
    #   - 用户可自行选择使用哪个 cape (UI 上看起来一样 → 选任意一个)

    # 打印 N 套内容差异信息 (供用户决策, 不影响输出)
    if total_themes > 1 and total_shared > 0 and same_cursor_count < total_shared:
        ratio = same_cursor_count / total_shared
        different = total_shared - same_cursor_count
        if ratio >= merge_threshold:
            print(f"  [info] detected {total_themes} sub-themes:")
            print(f"    {same_cursor_count}/{total_shared} shared cursor(s) are byte-identical across all sub-themes")
            print(f"    only {different} cursor(s) differ between sub-themes: {', '.join(near_dup_report[:5]) if near_dup_report else '(no 90%-majority match)'}")
            print(f"    -> 通用规则: 永远输出 {total_themes} 个 cape (按子主题名)")
            print(f"    -> 这些 cape 在 Mousecape UI 上看起来可能几乎一样 (主题包内容相似)")
            print(f"    -> tip: 如需去重, 编辑主题包或检查是否真的需要 {total_themes} 套子主题")
    elif total_themes > 1 and same_cursor_count == total_shared and total_shared > 0:
        # N 套 100% 相同 (all shared cursors identical)
        # 这是 Layer 1 整体指纹场景, 由 skip_themes 处理
        pass
    elif total_themes > 1:
        # N 套真不同
        print(f"  [info] detected {total_themes} distinct sub-themes")

    # 计算"应该保留哪些子主题":
    # 唯一跳过条件: **整体字节指纹完全相同** (Layer 1, 100% 字节相同)
    # 这是唯一不会让用户"感觉一样"的合并 (因为字节完全相同)
    skip_themes: set[str] = set()
    for cd, theme_name, fp in fingerprints:
        if fp in seen_fps and seen_fps[fp] != theme_name:
            # 整体指纹重复 (100% 字节相同)
            skip_themes.add(theme_name)

    # 打印完全相同子主题的警告
    if skip_themes:
        kept_full_dup = [name for name in (t[1] for t in fingerprints) if name not in skip_themes]
        print(f"  [info] skipping {len(skip_themes)} fully-identical sub-theme(s) (100% byte-identical to '{kept_full_dup[0] if kept_full_dup else '?'}'):")
        for s in sorted(skip_themes):
            print(f"    - {s}")

    # 只保留不被 skip 的子主题
    results: list[tuple[str, list]] = []
    for cd, theme_name, fp in fingerprints:
        if theme_name in skip_themes:
            continue
        results.append((theme_name, _read_all_cursors(cd)))
    return results


def _read_all_cursors(root: Path):
    """
    递归扫描 root，找出所有以 'Xcur' 魔数开头的 xcursor 文件并解析。
    自动跳过主题元数据文件（*.theme）、已解码的 PNG、以及本工具生成的 decoded/ 目录。

    ⚠️ 关键: 按"cursor 名"去重 (不是 realpath) -- 保留所有 X11 cursor 别名
    背景: Vimix 类主题里一个真实光标图有 5+ 个 X11 名称 (default, arrow, left_ptr
    都是 symlink → default), 我们要把每个 X11 名都保留为独立 Cursor 对象,
    这样下游 normalizer 能正确为每个 X11 名查找对应 macOS identifier.
    只有当两个文件 X11 名相同时才去重 (即: 一个 X11 名只产生一个 Cursor).

    实现:
      - real 文件: 入 candidates 列表 (X11 名 = 文件名 stem)
      - symlink 文件: 入 candidates 列表 (X11 名 = symlink 名)
      - 同名 (real vs symlink 同名) 只取一个
      - 同名 (symlink vs symlink 同名) 只取第一个
    """
    cursors: list[Cursor] = []
    # 用 "cursor 名" (X11 stem) 去重, 不用 realpath
    seen_names: set[str] = set()
    candidates: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix in (".theme", ".png", ".jpg", ".jpeg"):
            continue
        if path.parent.name == "decoded":
            continue
        # 快速魔数校验: 不是 xcursor 就跳过
        try:
            with open(path, "rb") as f:
                head = f.read(4)
            if head != _XCUR_MAGIC:
                continue
        except OSError:
            continue
        # 用 X11 cursor 名 (path.stem) 去重
        if path.name in seen_names:
            continue
        seen_names.add(path.name)
        candidates.append(path)

    for path in candidates:
        cursors.append(read_xcursor(path))
    return cursors
