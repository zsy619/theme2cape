from pathlib import Path
import subprocess

THEME_DIR = Path("themes")

# 支持所有 cli.py 能识别的压缩包格式
SUPPORTED = (
    ".tar.xz",
    ".tar.gz",
    ".tgz",
    ".zip",
    ".tar",
    ".tar.bz2",
    ".tbz2",
)

total = 0
success = 0
failed = 0
# 记录失败的压缩包,最后统一输出
failed_items: list[str] = []

for item in THEME_DIR.iterdir():
    # 跳过目录
    if item.is_dir():
        continue
    # 跳过非支持的压缩包格式
    if not any(str(item).endswith(x) for x in SUPPORTED):
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
else:
    print("\n[OK] 全部压缩包处理成功,无失败项")
