from pathlib import Path
import subprocess

THEME_DIR = Path("themes")

# 支持所有 cli.py 能识别的压缩包格式 + CursorFX 主题
# CursorFX 有两种形态:
#   1) 目录形态: 带 .cursorfx 扩展名的目录(Windows shell compound document),
#      解压后是含 Scheme.ini + <Section>.png 的扁平目录.
#   2) 二进制文件形态: Stardock 私有打包格式, 由 cursorfx_binary_reader 解析.
SUPPORTED = (
    ".tar.xz",
    ".tar.gz",
    ".tgz",
    ".zip",
    ".tar",
    ".tar.bz2",
    ".tbz2",
    ".7z",
    ".cursorfx",  # Stardock CursorFX 二进制文件 (由 cursorfx_binary_reader 支持)
)
# CursorFX 后缀用于识别"以 .cursorfx 结尾的目录"
CURSORFX_SUFFIX = ".cursorfx"

total = 0
success = 0
failed = 0
# 记录失败的压缩包,最后统一输出
failed_items: list[str] = []

for item in THEME_DIR.iterdir():
    # ----- CursorFX 主题 (两种形态都支持) -----
    # 形态 1: 目录形态 (已经是展开的 Scheme.ini+PNG)
    # 形态 2: 二进制文件形态 (Stardock 私有格式, 由 cursorfx_binary_reader 解析)
    # 两种形态都由 cli.py 的 discover_themes 自动识别并处理
    if item.is_file() and item.name.lower().endswith(CURSORFX_SUFFIX):
        # CursorFX 二进制文件,走正常处理流程
        pass
    elif item.is_dir() and item.name.lower().endswith(CURSORFX_SUFFIX):
        # CursorFX 目录形态,走正常处理流程
        pass
    # ----- 其他目录一律跳过 (避免误处理 _extracted_xxx 等中间目录) -----
    elif item.is_dir():
        continue
    # ----- 非 CursorFX 的文件: 必须以支持的压缩包后缀结尾 -----
    elif not any(str(item).endswith(x) for x in SUPPORTED):
        continue

    total += 1

    print(f"\n[{total}] {item.name}")

    try:

        subprocess.run(["python3", "cli.py", str(item)], check=True)

        success += 1

    except subprocess.CalledProcessError:

        failed += 1
        # 记录失败的压缩包名称(保留完整路径方便定位)
        failed_items.append(str(item))

print("\n====================")
print("Batch Finished")
print("====================")
print(f"Total   : {total}")
print(f"Success : {success}")
print(f"Failed  : {failed}")

# 统一输出失败列表
if failed_items:
    print("\n====================")
    print(f"失败列表 (共 {len(failed_items)} 个):")
    print("====================")
    for idx, name in enumerate(failed_items, start=1):
        print(f"  {idx}. {name}")
    print("\n说明: 这些文件处理失败,请检查错误信息")
else:
    if failed == 0:
        print("\n[OK] 全部压缩包处理成功,无失败项")
