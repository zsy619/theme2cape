# macOS 鼠标指针 **全量对照列表**
基于 **Mousecape-swiftUI 源码 (MCDefs.m)** 精确解析，**100% 可用于 .cape 文件**。

> ⚠️ 重要：Mousecape 使用 `com.apple.cursor.N` 和 `com.apple.coregraphics.*` 两类 identifier。
> `com.apple.cursor.N` 中的 N 是 macOS CoreGraphics 内部编号，**不是** NSCursor API 的顺序编号！
> N 从 2 开始，不连续（无 0, 1, 6），直接使用 NSCursor 顺序编号会导致 Mousecape 显示 "Unknown"。

格式：**显示名 → identifier → 中文说明**

## 一、com.apple.coregraphics.* 标识符（9 个）
这些是命名光标，使用 `com.apple.coregraphics.` 前缀：
```
Arrow     → com.apple.coregraphics.Arrow     → 默认箭头
IBeam     → com.apple.coregraphics.IBeam     → 文本I型光标
IBeamXOR  → com.apple.coregraphics.IBeamXOR  → 文本I型(XOR反色)
Alias     → com.apple.coregraphics.Alias     → 拖拽替身(链接)
Copy      → com.apple.coregraphics.Copy      → 拖拽复制
Move      → com.apple.coregraphics.Move      → 移动指针
ArrowCtx  → com.apple.coregraphics.ArrowCtx  → 上下文箭头
Wait      → com.apple.coregraphics.Wait      → 等待(风火轮)
Empty     → com.apple.coregraphics.Empty     → 隐藏光标
```

## 二、com.apple.cursor.N 标识符（41 个）
这些是编号光标，使用 `com.apple.cursor.N` 格式，N 为 CoreGraphics 内部编号：

### 链接/拖拽类
```
Link              → com.apple.cursor.2   → 链接
Forbidden         → com.apple.cursor.3   → 禁止操作
Busy              → com.apple.cursor.4   → 旋转忙碌
Copy Drag         → com.apple.cursor.5   → 拖拽复制
```

### 十字/相机类
```
Crosshair         → com.apple.cursor.7   → 十字准星
Crosshair 2       → com.apple.cursor.8   → 十字准星2
Camera 2          → com.apple.cursor.9   → 截图光标2
Camera            → com.apple.cursor.10  → 截图光标
```

### 手型/抓取类
```
Closed            → com.apple.cursor.11  → 握紧手(拖动中)
Open              → com.apple.cursor.12  → 张开手(可拖动)
Pointing          → com.apple.cursor.13  → 手指指针(链接)
```

### 计数/动画类
```
Counting Up       → com.apple.cursor.14  → 向上计数
Counting Down     → com.apple.cursor.15  → 向下计数(progress)
Counting Up/Down  → com.apple.cursor.16  → 双向计数(half-busy)
```

### 调整大小类
```
Resize W          → com.apple.cursor.17  → 西向调整(←)
Resize E          → com.apple.cursor.18  → 东向调整(→)
Resize W-E        → com.apple.cursor.19  → 水平双向(↔)
Cell XOR          → com.apple.cursor.20  → 表格异或选区
Resize N          → com.apple.cursor.21  → 北向调整(↑)
Resize S          → com.apple.cursor.22  → 南向调整(↓)
Resize N-S        → com.apple.cursor.23  → 垂直双向(↕)
```

### 菜单/杂项类
```
Ctx Menu          → com.apple.cursor.24  → 右键菜单
Poof              → com.apple.cursor.25  → 拖放删除(烟雾)
IBeam H.          → com.apple.cursor.26  → 竖排文本I型
```

### 窗口边框类
```
Window E          → com.apple.cursor.27  → 东向窗口边
Window E-W        → com.apple.cursor.28  → 东西向窗口边
Window NE         → com.apple.cursor.29  → 东北向窗口角
Window NE-SW      → com.apple.cursor.30  → 东北-西南对角线
Window N          → com.apple.cursor.31  → 北向窗口边
Window N-S        → com.apple.cursor.32  → 南北向窗口边
Window NW         → com.apple.cursor.33  → 西北向窗口角
Window NW-SE      → com.apple.cursor.34  → 西北-东南对角线
Window SE         → com.apple.cursor.35  → 东南向窗口角
Window S          → com.apple.cursor.36  → 南向窗口边
Window SW         → com.apple.cursor.37  → 西南向窗口角
Window W          → com.apple.cursor.38  → 西向窗口边
Resize Square     → com.apple.cursor.39  → 方形调整
```

### 功能类
```
Help              → com.apple.cursor.40  → 帮助(问号)
Cell              → com.apple.cursor.41  → 表格单元格
Zoom In           → com.apple.cursor.42  → 放大
Zoom Out          → com.apple.cursor.43  → 缩小
```

## 三、defaultCursors 列表（11 个）
Mousecape 加载 cape 时默认显示的光标列表：
```
com.apple.coregraphics.Arrow
com.apple.coregraphics.IBeam
com.apple.coregraphics.IBeamXOR
com.apple.coregraphics.Alias
com.apple.coregraphics.Copy
com.apple.coregraphics.Move
com.apple.coregraphics.ArrowCtx
com.apple.coregraphics.ArrowS        ← 新增 (macOS 26 小尺寸箭头)
com.apple.coregraphics.IBeamS        ← 新增 (macOS 26 小尺寸I型)
com.apple.coregraphics.Wait
com.apple.coregraphics.Empty
```

## 四、X11 → macOS 映射速查表

### 基础指针
```text
arrow / left_ptr / default / top_left_arrow / right_ptr / top_right_arrow  →  com.apple.coregraphics.Arrow
# ⚠️ right_ptr 是右上角箭头, 不是上下文菜单光标, 不映射到 Ctx Menu
```

### 文本
```text
xterm / ibeam / text / IBeamXOR / @xterm / ib / handwriting / horizontal-text  →  com.apple.coregraphics.IBeam
vertical-text / text_vertical  →  com.apple.cursor.26 (IBeam H.)
```

### 手型/链接
```text
hand2 / pointer / hand1 / hand / pointing_hand / pointer2 / button  →  com.apple.cursor.13 (Pointing)
link  →  com.apple.cursor.2  (Link)
e29285e634086352946a0e7090d73106  →  com.apple.cursor.13 (X11 编码名 → hand2)
```

### 复制/拖拽
```text
copy  →  com.apple.coregraphics.Copy
dnd-copy  →  com.apple.cursor.5  (Copy Drag)
dnd-move / dnd-none / dragging  →  com.apple.cursor.11 (Closed)
dnd-link  →  com.apple.cursor.2  (Link)
dnd-grab  →  com.apple.cursor.12 (Open)
dnd_no_drop / not-allowed / forbidden / circle / crossed_circle / crossed-circle / no-drop / dnd-no-drop / dnd-ask / pirate / kill  →  com.apple.cursor.3  (Forbidden)
```

### 别名/移动
```text
alias  →  com.apple.coregraphics.Alias
move / fleur / all-scroll / scroll-all / size_all / sizing / pointer-move / pointer_move  →  com.apple.coregraphics.Move
```

### 水平双向箭头
```text
sb_h_double_arrow / size_hor / size-hor / ew-resize / h_double_arrow / h_double / col-resize / split_h / double-arrow / double_arrow / HDoubleArrow  →  com.apple.cursor.19 (Resize W-E)
```

### 垂直双向箭头
```text
sb_v_double_arrow / size_ver / size-ver / ns-resize / v_double_arrow / v_double / row-resize / split_v / VDoubleArrow  →  com.apple.cursor.23 (Resize N-S)
```

### 对角线双向箭头
```text
bd_double_arrow / size_fdiag / size-fdiag / nwse-resize / top_left_corner / bottom_right_corner / ul_angle / lr_angle / nw-resize / sw-resize / nw_sizegrip / sw_sizegrip  →  com.apple.cursor.34 (Window NW-SE)
fd_double_arrow / size_bdiag / size-bdiag / nesw-resize / top_right_corner / bottom_left_corner / ur_angle / ll_angle / ne-resize / se-resize / ne_sizegrip / se_sizegrip / SizeNESW_Down  →  com.apple.cursor.30 (Window NE-SW)
```

### 单方向调整
```text
left_side / left-side / w-resize / left_tee / sb_left_arrow / left-arrow / left_arrow  →  com.apple.cursor.17 (Resize W)
right_side / right-side / e-resize / right_tee / sb_right_arrow / right-arrow / right_arrow  →  com.apple.cursor.18 (Resize E)
top_side / top-side / n-resize / top_tee / sb_up_arrow / up-arrow / up_arrow / based_arrow_up / base_arrow_up  →  com.apple.cursor.21 (Resize N)
bottom_side / bottom-side / s-resize / bottom_tee / sb_down_arrow / down-arrow / down_arrow / based_arrow_down / base_arrow_down  →  com.apple.cursor.22 (Resize S)
```

### 十字/精度
```text
cross / crosshair / tcross / plus / center_ptr / pencil / draft / draft_large / draft_small / color-picker / diamond_cross / cross_reverse / center_main  →  com.apple.cursor.7  (Crosshair)
dotbox / dot_box / dot_box_mask / cell / icon / target / draped_box / dot / person  →  com.apple.cursor.41 (Cell)
```

### 帮助
```text
help / question_arrow / question-arrow / whats_this / left_ptr_help  →  com.apple.cursor.40 (Help)
```

### 等待/忙碌
```text
watch / wait / clock / left_ptr_watch  →  com.apple.coregraphics.Wait
progress  →  com.apple.cursor.15 (Counting Down)
half-busy / half_busy  →  com.apple.cursor.16 (Counting Up/Down)
```

### 抓取
```text
grab / openhand / HandGrab  →  com.apple.cursor.12 (Open)
grabbing / closedhand / HandSqueezed  →  com.apple.cursor.11 (Closed)
```

### 缩放
```text
zoom-in / zoom_in / zoomIn  →  com.apple.cursor.42 (Zoom In)
zoom-out / zoom_out / zoomOut  →  com.apple.cursor.43 (Zoom Out)
```

### 菜单/杂项
```text
context-menu  →  com.apple.cursor.24 (Ctx Menu)
poof  →  com.apple.cursor.25 (Poof)
```

### 跳过 (无 macOS 对应)
```text
X_cursor / x_cursor / X-cursor / x-cursor / wayland-cursor / spot-anchor / spot-hover / spot-touch  →  None (跳过)
```
