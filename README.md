# theme2cape

把 X11 XCursor 主题 (Linux/Unix 鼠标指针) 一键转成 macOS Mousecape `.cape` 文件。

支持:

- 7 种压缩格式: `.tar.xz` / `.tar.gz` / `.tgz` / `.zip` / `.tar` / `.tar.bz2` / `.tbz2`
- 单套主题 + 多套子主题 (一个压缩包内含 N 套颜色/样式变种)
- KDE SVG 源主题 (自动 build SVG→XCursor, 需 cairosvg)
- 通用 XCursor 主题目录变体: `cursors/`, `cursors_scalable/`, `cursors_pixmap/`, `cursors_svg/`, `cursors_left/`, `cursors_right/`
- 自我校验机制 (5 阶段自动校验, 保证生成 cape 与 Mousecape 兼容)
- 通用生成规则: 永远按子主题名输出 N 个 cape, 唯一例外是字节 100% 完全相同的子主题

---

## 快速开始

```bash
# 安装 cairosvg (仅当处理 SVG 源主题如 WhiteSurX 时需要)
pip3 install --break-system-packages --user cairosvg

# 一键批量处理 themes/ 目录下所有压缩包
python3 batch.py

# 或处理单个主题
python3 cli.py themes/PolarCursorThemes.tar
```

生成的 `.cape` 文件输出到 `out/` 目录, 可直接拖入 Mousecape。

---

## 主题下载来源

推荐从 [KDE Store - Cursors 分类](https://store.kde.org/browse?cat=107&ord=latest) 下载 X11 XCursor 主题压缩包。

### 下载步骤

1. 访问 https://store.kde.org/browse?cat=107&ord=latest
2. 浏览/搜索想要的主题 (如 `Bibata`, `BreezeX`, `WhiteSur`, `Moga` 等)
3. 进入主题详情页, 找到 **Files** 标签
4. 下载压缩包:
   - 优先选择 **`cursors.tar.xz`** 或 **`cursors.tar.gz`** (XCursor 二进制, 工具直接解析)
   - 部分主题提供 **`Source`** 链接, 包含 `cursors_scalable/*.svg` (KDE 源格式, 工具自动 build)

### 常用主题推荐

| 主题 | 特点 | 压缩包类型 |
|------|------|-----------|
| Bibata Modern / Original | 高清矢量, 多色 (Amber/Classic/Ice) | `.tar.xz` |
| BreezeX | KDE Breeze 风格, Black/Dark/Light | `.tar.xz` |
| WhiteSur | macOS Big Sur 风格 | `.tar.gz` |
| WhiteSurX | WhiteSur + KDE SVG 源 | `.tar` (SVG 源) |
| Moga | 多色霓虹 (14 套) | `.zip` |
| Drop | 多色 (4 套) | `.zip` |
| PolarCursorThemes | 极简 (3 套) | `.tar` |

### 放置到 themes/ 目录

把下载的压缩包放到项目 `themes/` 目录下:

```bash
# 例: 下载 Bibata 主题
curl -L "https://..." -o themes/Bibata-Modern-Amber.tar.xz

# 跑批量处理
python3 batch.py
```

### 常见问题

- **下载的是 Source 包而非 XCursor 包**: 进入主题 Files 标签, 找 `cursors.tar.xz` 或 `cursors.tar.gz`, 优先下载这个 (Source 包是 SVG 源, 工具会自动 build, 但下载二进制版更省事)
- **下载链接是 Pling Store / OCS**: 同一资源在 KDE Store 也有, 链接互通
- **下载慢/链接失效**: 可用 `curl -L -o themes/X.tar.xz <url>` 直接下载, 或用浏览器右键另存为

---

## 目录结构

```
theme2cape/
├── cli.py                  # 单个主题处理入口
├── batch.py                # 批量处理 themes/ 目录
├── core/
│   ├── kxcursor_reader.py  # 主题发现 + XCursor 解析 (含 SVG 检测, 多套子主题检测)
│   ├── svg_renderer.py     # SVG 源 → XCursor 自动 build (cairosvg/rsvg/magick)
│   ├── bibata_renderer.py  # Bibata 主题特殊处理 (像素级渲染)
│   ├── cim.py              # XCursor 二进制格式解析 (跨多尺寸 nominal size)
│   ├── normalizer.py       # X11 cursor 名 → macOS cursor identifier 映射
│   ├── cape_builder.py     # 组装 + 校验 + 写 .cape 文件
│   └── validator.py        # 5 阶段自我校验 (XML plist / 字段 / FrameCount≤24 / rep 维度)
├── mapper/
│   └── macos_full.py       # X11 cursor 名 ↔ macOS cursor identifier 完整映射表
├── themes/                 # 放待处理的 .tar.xz / .zip 等 (用户自行放入)
└── out/                    # 生成的 .cape 文件输出目录
```

---

## 通用生成规则

### N 套子主题 → N 个 cape

工具**永远按子主题名输出 N 个 cape** (N = 压缩包内 cursors 目录数):

```
PolarCursorThemes.tar 含 3 套子主题 (默认/Blue/Green) → 3 个 cape:
  out/PolarCursorThemes_PolarCursorTheme.cape
  out/PolarCursorThemes_PolarCursorTheme-Blue.cape
  out/PolarCursorThemes_PolarCursorTheme-Green.cape
```

### 唯一合并场景: 100% 字节完全相同

如果 N 套中**所有** cursor 字节完全相同 (整体 SHA-256 指纹一致), 自动合并为 1 个 cape (这是真冗余, 合理合并)。否则即使 99% 相同也保留 N 个 cape。

```
[info] skipping 2 fully-identical sub-theme(s) (100% byte-identical to 'X'):
  - SubThemeA
  - SubThemeB
```

### 高相似度 (≥90% 字节相同) 不合并

N 套中如有 ≥90% cursor 字节相同 (但不全相同), 仍输出 N 个 cape + info 警告:

```
[info] detected 3 sub-themes:
  63/65 shared cursor(s) are byte-identical across all sub-themes
  only 2 cursor(s) differ between sub-themes
  -> 通用规则: 永远输出 3 个 cape (按子主题名)
  -> 这些 cape 在 Mousecape UI 上看起来可能几乎一样 (主题包内容相似)
  -> tip: 如需去重, 编辑主题包或检查是否真的需要 3 套子主题
```

**设计哲学**: 主题包的内容是主题作者的责任, 工具忠实反映主题包结构, 不擅自合并。

---

## 支持的压缩格式

| 格式 | 扩展名 |
|------|-------|
| XZ 压缩 tar | `.tar.xz` |
| Gzip 压缩 tar | `.tar.gz` / `.tgz` |
| ZIP | `.zip` |
| 未压缩 tar | `.tar` |
| Bzip2 压缩 tar | `.tar.bz2` / `.tbz2` |

---

## 主题包内容检测与自动处理

| 主题类型 | 检测 | 处理 |
|---------|------|------|
| 标准 XCursor (`cursors/*.cur`) | `cursors/` 目录 + XCursor 魔数 `Xcur` | 直接解析 |
| 矢量主题 (`cursors_scalable/<name>/metadata.json` + `*.svg`) | KDE Breeze/WhiteSur 源格式 | **自动 build** SVG→PNG→XCursor (cairosvg 渲染, 多尺寸 24/32/48/64/96) |
| 主题变体目录 | `cursors_scalable/`, `cursors_pixmap/`, `cursors_svg/` 等 | 自动识别优先级 (scalable > pixmap > svg > cursors > 其他) |
| 单 cursor 0 字节空文件 | 文件大小为 0 | 复用同 mac identifier 的其他 X11 cursor 帧 (sibling fallback) |
| 主题完全没提供的 mac identifier | mapper 中无映射 | 用语义相邻的 mac identifier 帧兜底 (8 个 cross-fallback 映射) |

---

## 自我校验机制

每个 cape 写文件前自动校验 (5 阶段):

1. **XML plist 格式** (Mousecape 必须, binary plist 直接返回 nil)
2. **顶层字段完整性** (Identifier / MinimumVersion / Cursors)
3. **每 cursor 必填字段** (FrameCount / FrameDuration / HotSpot / Points / Representations)
4. **FrameCount ≤ 24 硬限制** (Mousecape apply.m L16 拒绝, 强制拆帧或合并)
5. **rep 像素维度一致性** (height = PointsHigh × scale × FrameCount, width 是 PointsWide 整数倍)

不通过抛 RuntimeError 拒绝写文件。Mousecape 打开 cape 时不会报"FrameCount exceeded"或"Invalid image"。

---

## 0 Unknown cursor 设计

每个 X11 cursor 名都映射到 macOS cursor identifier (X11 cursorMap 内部解析), Mousecape UI 显示真实 cursor 名称, 不是 "Unknown"。

策略:
- X11 cursor 名作为主 identifier (如 `arrow`, `xterm`, `crosshair`, `pointer`)
- macOS cursorMap 内部把 X11 名解析到正确 mac identifier
- 跳过 32 位 hash 名 (如 `00008160000006810000408080010102`, cursorMap 找不到)

---

## 命令行

### batch.py — 批量处理

```bash
python3 batch.py
```

自动处理 `themes/` 目录下所有支持的压缩包, 输出 `out/<主题名>.cape`。

### cli.py — 单个主题

```bash
python3 cli.py <theme-path>
```

`<theme-path>` 可以是压缩包或已解压目录。

---

## 常见问题

### 0 Unknown cursor?

正常。X11 cursor 名作为主 identifier, Mousecape 内部 cursorMap 解析, UI 显示真实名称。

### 生成的 cape 在 Mousecape 里只显示部分 cursor?

XCursor 主题里的某些 cursor (如 `wayland-cursor`, `x-cursor`) 是 X11 server 内部用, 不映射到 macOS。工具自动跳过。

### SVG 主题 (如 WhiteSurX) 渲染失败?

需要安装 cairosvg: `pip3 install --break-system-packages --user cairosvg`。也可选 rsvg-convert / ImageMagick / inkscape (按可用性自动选择)。

### 生成的多个 cape 看起来一样?

检查主题包内容。如 N 套中 ≥90% cursor 字节相同, 工具会输出 info 警告说明。这是主题包作者的问题 (没提供真正不同的 N 套内容), 不是工具的问题。

---

## 依赖

- Python 3.8+
- (可选) `cairosvg` — KDE SVG 源主题自动 build
- (可选) `rsvg-convert` / ImageMagick / inkscape — cairosvg 不可用时的备选 SVG 渲染器
- (可选) `Pillow` — XCursor PNG 解码

---

## 验证状态

最后跑通 36 个主题 (含 Bibata/BreezeX/Drop/Moga/Polar/Quintom/Vimix/WhiteSur/WhiteSurX/Marbre 等) → 38 个 cape 全部通过自我校验:
```
Total   : 36
Success : 36
Failed  : 0
```

每个 cape 0 Unknown cursor, 全部 Mousecape 兼容。
