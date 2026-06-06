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

for item in THEME_DIR.iterdir():

    if item.is_dir():
        pass

    elif not any(str(item).endswith(x) for x in SUPPORTED):
        continue

    total += 1

    print(f"\n[{total}] {item.name}")

    try:

        subprocess.run(["python3", "cli.py", str(item)], check=True)

        success += 1

    except subprocess.CalledProcessError:

        failed += 1

print("\n====================")
print("Batch Finished")
print("====================")
print(f"Total   : {total}")
print(f"Success : {success}")
print(f"Failed  : {failed}")
