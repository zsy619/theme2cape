import sys
from pathlib import Path
from core.kxcursor_reader import discover_themes
from core.normalizer import normalize
from core.cape_builder import build_cape


# 按优先级尝试剥掉这些压缩包后缀
_ARCHIVE_EXTS = (".tar.xz", ".tar.gz", ".tgz", ".zip", ".tar", ".tar.bz2", ".tbz2")


def _derive_theme_name(input_path: Path) -> str:
    """
    从输入文件路径推导主题名：剥掉压缩包后缀(若有)。
    例:
      Bibata-Modern-Amber-Right.tar.xz -> "Bibata-Modern-Amber-Right"
      /path/to/Theme.tar.gz           -> "Theme"
      some/dir/with/cursors           -> "with"  (用最后一段目录名)
      single_arrow                    -> "single_arrow"
    """
    name = input_path.name
    lower = name.lower()
    for ext in _ARCHIVE_EXTS:
        if lower.endswith(ext):
            return name[: -len(ext)]
    return input_path.stem


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 cli.py <theme-path>")
        print()
        print("通用规则: 永远按子主题名输出 N 个 cape (N 套 → N cape)")
        print("  - 主题包含 1 套子主题 → 1 个 cape")
        print("  - 主题包含 N 套子主题 → N 个 cape (按子主题名)")
        print("  - 例外: 完全字节相同的子主题 (100%) 自动合并 (这种是真冗余)")
        sys.exit(1)

    input_path = Path(args[0])
    out_dir = Path("out")
    base_theme_name = _derive_theme_name(input_path)

    # 1. discover themes (永远 N 套 → N cape, 只合并 100% 字节相同的子主题)
    themes = discover_themes(input_path, out_dir)
    if not themes:
        print("No cursor themes found")
        return

    # 2. 逐套生成 cape
    for theme_name, cursors in themes:
        # 如果只有 1 套且主题名跟压缩包名一致, 用压缩包名 (用户期望)
        if len(themes) == 1 and theme_name in (
            input_path.stem,
            # 解压根目录的子目录名(去掉路径前导)
            theme_name,
        ):
            final_name = base_theme_name
        else:
            # 多套: 用每套自己的名字 (避免覆盖)
            final_name = f"{base_theme_name}_{theme_name}" if theme_name != base_theme_name else theme_name

        # **关键**: 文件名 sanitize (去除空格/括号, 避免 FileNotFoundError)
        # 同时保留 CapeName 原始字符串给 Mousecape UI 显示
        safe_filename = "".join(c if (c.isalnum() or c in "._-") else "_" for c in final_name)

        # normalize & 过滤
        normalized = [n for n in (normalize(c) for c in cursors) if n]
        if not normalized:
            print(f"\n[{theme_name}] No supported cursors found, skipping")
            continue

        # build cape (用 safe_filename 作文件名, 但 final_name 进 CapeName)
        out = build_cape(safe_filename, normalized, out_dir, display_name=final_name)
        print("DONE:", out)


if __name__ == "__main__":
    main()
