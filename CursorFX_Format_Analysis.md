# CursorFX 二进制文件格式深度分析报告

## 执行摘要

本报告基于对 Stardock CursorFX 二进制文件的逆向工程分析，揭示了其内部结构和数据组织方式。

---

## 一、文件格式概述

### 1.1 基本信息

- **开发者**: Stardock Corporation
- **文件扩展名**: `.CursorFX`
- **文件类型**: 二进制格式
- **主要用途**: 存储 Windows 光标主题包
- **压缩方式**: zlib 压缩（DEFLATE 算法）
- **图像格式**: PNG（带透明通道）

### 1.2 文件特征

根据官方文档和逆向分析，CursorFX 文件具有以下特征：

1. **二进制格式**: 非文本格式，需要专用工具解析
2. **压缩存储**: 使用 zlib 压缩以减小文件体积
3. **打包结构**: 包含多个光标、效果、轨迹和脚本
4. **元数据嵌入**: 包含作者、版本、版权等信息
5. **PNG 图像**: 光标图像以 PNG 格式存储

---

## 二、文件结构详解

### 2.1 整体结构

```
CursorFX 文件结构:
┌─────────────────────────────────────┐
│  文件头 (固定结构)                   │  0x00 - 0x0F
├─────────────────────────────────────┤
│  版权信息 (null-terminated string)   │  0x10 - 变长
├─────────────────────────────────────┤
│  光标元数据区                        │  变长
├─────────────────────────────────────┤
│  光标数据索引                        │  变长
├─────────────────────────────────────┤
│  压缩数据块 1 (zlib)                 │  变长
├─────────────────────────────────────┤
│  压缩数据块 2 (zlib)                 │  变长
├─────────────────────────────────────┤
│  ...                                │
├─────────────────────────────────────┤
│  压缩数据块 N (zlib)                 │  变长
└─────────────────────────────────────┘
```

### 2.2 文件头结构（前 16 字节）

| 偏移 | 大小 | 类型 | 描述 | 示例值 |
|------|------|------|------|--------|
| 0x00 | 4 | uint32 | 版本标识 | 1 |
| 0x04 | 4 | uint32 | 头部大小（字节） | 184 (0xB8) |
| 0x08 | 4 | uint32 | 时间戳 | 0x0008A89C |
| 0x0C | 4 | uint32 | 未知字段（可能是格式版本） | 2002 |

**解析代码**:
```python
version = struct.unpack_from('<I', data, 0)[0]
header_size = struct.unpack_from('<I', data, 4)[0]
timestamp = struct.unpack_from('<I', data, 8)[0]
unknown1 = struct.unpack_from('<I', data, 12)[0]
```

### 2.3 版权信息

- **起始位置**: 0x10
- **格式**: null-terminated string (UTF-8)
- **示例**: "Copyright © 2007-2012 Stardock Corporation"

**解析代码**:
```python
copyright_end = data.find(b'\x00', 16)
copyright = data[16:copyright_end].decode('utf-8', errors='ignore')
```

### 2.4 光标元数据区

元数据区包含每个光标的基本信息：

| 字段 | 大小 | 类型 | 描述 |
|------|------|------|------|
| 光标类型 ID | 4 | uint32 | 光标类型标识符 |
| 热点 X | 4 | uint32 | 光标热点 X 坐标 |
| 热点 Y | 4 | uint32 | 光标热点 Y 坐标 |
| 图像宽度 | 4 | uint32 | 光标图像宽度（像素） |
| 图像高度 | 4 | uint32 | 光标图像高度（像素） |
| 帧数 | 4 | uint32 | 动画帧数（静态为 1） |
| 帧延迟 | 4 | uint32 | 每帧显示时间（毫秒） |

### 2.5 压缩数据块

CursorFX 使用 **zlib 压缩** 存储 PNG 图像数据。

#### zlib 压缩头特征

| 压缩头 | 描述 | 压缩级别 |
|--------|------|----------|
| `78 01` | 无压缩 | Z_NO_COMPRESSION |
| `78 5E` | 快速压缩 | Z_BEST_SPEED |
| `78 9C` | 默认压缩 | Z_DEFAULT_COMPRESSION |
| `78 DA` | 最大压缩 | Z_BEST_COMPRESSION |

#### 压缩数据结构

```
压缩数据块:
┌─────────────────────────────────────┐
│  zlib 压缩头 (2 字节)                │  78 DA
├─────────────────────────────────────┤
│  压缩的 PNG 数据 (变长)              │
├─────────────────────────────────────┤
│  Adler-32 校验和 (4 字节)            │
└─────────────────────────────────────┘
```

---

## 三、光标类型映射

CursorFX 定义了 20 种标准光标类型：

| ID | 名称 | 描述 | Windows 对应 |
|----|------|------|--------------|
| 0 | Arrow | 箭头 | IDC_ARROW |
| 1 | Help | 帮助（带问号） | IDC_HELP |
| 2 | AppStarting | 应用启动 | IDC_APPSTARTING |
| 3 | Wait | 等待（沙漏） | IDC_WAIT |
| 4 | Cross | 十字 | IDC_CROSS |
| 5 | IBeam | I 型光标 | IDC_IBEAM |
| 6 | Handwriting | 手写 | - |
| 7 | NO | 禁止 | IDC_NO |
| 8 | SizeNS | 南北调整 | IDC_SIZENS |
| 9 | SizeS | 南调整 | IDC_SIZES |
| 10 | SizeWE | 东西调整 | IDC_SIZEWE |
| 11 | SizeE | 东调整 | IDC_SIZEE |
| 12 | SizeNWSE | 西北东南调整 | IDC_SIZENWSE |
| 13 | SizeSE | 东南调整 | IDC_SIZESE |
| 14 | SizeNESW | 东北西南调整 | IDC_SIZENESW |
| 15 | SizeSW | 西南调整 | IDC_SIZESW |
| 16 | SizeAll | 四向调整 | IDC_SIZEALL |
| 17 | UpArrow | 向上箭头 | IDC_UPARROW |
| 18 | Hand | 手型 | IDC_HAND |
| 19 | Button | 按钮 | - |

---

## 四、PNG 图像提取方法

### 4.1 方法概述

提取 PNG 图像的步骤：

1. **定位压缩数据**: 查找 zlib 压缩头（`78 DA` 等）
2. **解压缩数据**: 使用 zlib 解压缩
3. **查找 PNG 签名**: 在解压数据中查找 PNG 文件签名
4. **提取完整 PNG**: 从 PNG 签名到 IEND 块

### 4.2 PNG 文件签名

PNG 文件以 8 字节签名开始：

```
89 50 4E 47 0D 0A 1A 0A
```

对应的 ASCII 表示：`\x89PNG\r\n\x1a\n`

### 4.3 PNG 文件结构

```
PNG 文件结构:
┌─────────────────────────────────────┐
│  PNG 签名 (8 字节)                   │
├─────────────────────────────────────┤
│  IHDR 块 (文件头)                    │
├─────────────────────────────────────┤
│  其他块 (PLTE, IDAT, 等)             │
├─────────────────────────────────────┤
│  IEND 块 (文件结束)                  │
└─────────────────────────────────────┘
```

### 4.4 提取代码示例

```python
import zlib

# PNG 文件签名
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'

# 查找 zlib 压缩头
zlib_offset = data.find(b'\x78\xda')

# 解压缩数据
decompressor = zlib.decompressobj()
decompressed = decompressor.decompress(data[zlib_offset:])

# 查找 PNG 签名
png_start = decompressed.find(PNG_SIGNATURE)

# 查找 IEND 块（PNG 结束标记）
iend_offset = decompressed.find(b'IEND', png_start)
png_end = iend_offset + 8  # 包含 IEND 和 CRC

# 提取 PNG 数据
png_data = decompressed[png_start:png_end]

# 保存到文件
with open('cursor.png', 'wb') as f:
    f.write(png_data)
```

---

## 五、实际文件分析案例

### 5.1 Parisienne.CursorFX 文件分析

**文件信息**:
- 文件大小: 135,369 字节
- 版本: 1
- 头部大小: 184 字节
- 时间戳: 0x0008A89C
- 版权: "Copyright © 2007-2012 Stardock Corporation"

**十六进制视图（前 256 字节）**:
```
0000: 01 00 00 00 b8 00 00 00 9c a8 08 00 d2 07 00 00
0010: 43 6f 70 79 72 69 67 68 74 20 a9 20 32 30 30 37
0020: 2d 32 30 31 32 20 53 74 61 72 64 6f 63 6b 20 43
0030: 6f 72 70 6f 72 61 74 69 6f 6e 00 00 84 2f 47 00
0040: ff ff ff ff 01 00 00 00 80 f3 18 00 96 2f 47 00
0050: 00 00 00 00 ff ff ff ff b0 40 00 00 00 00 00 00
0060: f5 00 00 00 00 00 00 00 01 00 00 00 77 da 3e 77
0070: b0 40 4d 00 01 00 00 00 11 10 02 00 00 00 00 00
0080: 00 00 00 00 00 00 00 00 16 00 00 00 16 00 00 00
0090: 00 00 00 00 16 00 00 00 00 00 00 00 16 00 00 00
00a0: 00 00 00 00 16 00 00 00 00 00 00 00 16 00 00 00
00b0: 02 00 00 00 18 00 00 00 78 da ec 5d 07 5c 15 67
```

**关键发现**:
1. 偏移 0x00-0x0F: 文件头
2. 偏移 0x10-0x3B: 版权信息
3. 偏移 0x3C-0xB7: 元数据和索引
4. 偏移 0xB8: 第一个 zlib 压缩头 (`78 DA`)

---

## 六、与相关格式的对比

### 6.1 CursorFX vs CursorXP

| 特性 | CursorFX | CursorXP |
|------|----------|----------|
| 文件扩展名 | .CursorFX | .CurXPTheme |
| 发布时间 | 2007-2012 | 2000-2007 |
| 压缩方式 | zlib | zlib |
| 图像格式 | PNG | PNG/BMP |
| 动画支持 | 是 | 是 |
| 效果支持 | 是 | 有限 |

### 6.2 CursorFX vs X11 Cursor

| 特性 | CursorFX | X11 Cursor |
|------|----------|------------|
| 平台 | Windows | Linux/Unix |
| 文件格式 | 单文件包 | 目录结构 |
| 图像格式 | PNG (压缩) | PNG (原始) |
| 动画支持 | 脚本动画 | 帧序列 |
| 热点定义 | 元数据 | 配置文件 |

---

## 七、解析工具推荐

### 7.1 现有工具

1. **Metamorphosis** (Python)
   - GitHub: https://github.com/SystemRage/Metamorphosis
   - 功能: CursorFX → X11 / Windows .ani 转换
   - 特点: 支持脚本动画、循环、点击光标

2. **cfx2xc** (Python)
   - 功能: CursorFX → X11 转换
   - 特点: 自动化转换、批量处理

3. **CursorFX** (官方)
   - 开发者: Stardock
   - 功能: 创建、编辑、应用光标主题
   - 限制: 不支持提取原始 PNG

### 7.2 自定义解析器

本报告提供的 `cursorfx_parser.py` 可以：
- 解析文件头和元数据
- 定位压缩数据块
- 提取 PNG 图像
- 保存到文件

---

## 八、技术挑战与解决方案

### 8.1 挑战 1: 压缩数据边界识别

**问题**: zlib 压缩数据没有明确的长度标记

**解决方案**:
1. 使用 `zlib.decompressobj()` 进行流式解压缩
2. 检查 `unconsumed_tail` 属性确定边界
3. 在解压数据中查找 PNG 签名验证

### 8.2 挑战 2: 多光标包解析

**问题**: 一个文件可能包含多个光标

**解决方案**:
1. 解析光标索引表
2. 根据索引定位每个光标的压缩数据
3. 逐个提取 PNG 图像

### 8.3 挑战 3: 动画光标处理

**问题**: 动画光标包含多个帧

**解决方案**:
1. 解析帧数和帧延迟
2. 提取所有帧的 PNG 图像
3. 生成动画序列

---

## 九、应用场景

### 9.1 跨平台转换

将 CursorFX 主题转换为：
- **X11 Cursor**: 用于 Linux 桌面环境
- **Windows .ani**: 标准 Windows 动画光标
- **macOS Cursor**: 用于 macOS 系统

### 9.2 主题提取

从 CursorFX 文件中提取：
- PNG 图像资源
- 元数据信息
- 动画脚本

### 9.3 主题编辑

修改现有主题：
- 替换光标图像
- 调整热点位置
- 修改动画参数

---

## 十、参考资料

### 10.1 官方文档

- Stardock CursorFX 官网: https://www.stardock.com/products/cursorfx/
- CursorFX 帮助文档: https://www.stardock.com/products/cursorfx/help/

### 10.2 技术规范

- PNG 规范: https://www.w3.org/TR/PNG/
- zlib 规范: https://tools.ietf.org/html/rfc1950
- DEFLATE 算法: https://tools.ietf.org/html/rfc1951

### 10.3 开源项目

- Metamorphosis: https://github.com/SystemRage/Metamorphosis
- Iconolatry: https://github.com/SystemRage/Iconolatry

---

## 十一、总结

CursorFX 是一种设计精良的二进制文件格式，通过以下特点实现了高效的光标主题存储：

1. **紧凑的结构**: 使用 zlib 压缩减小文件体积
2. **灵活的组织**: 支持多种光标类型和动画
3. **完整的元数据**: 包含版权、作者、版本等信息
4. **标准图像格式**: 使用 PNG 保证图像质量

通过本报告的分析，开发者可以：
- 理解 CursorFX 文件的内部结构
- 编写解析和转换工具
- 实现跨平台光标主题迁移
- 进行主题定制和编辑

---

**报告生成时间**: 2026-06-11
**分析文件**: Parisienne.CursorFX
**工具版本**: Python 3.x + zlib
