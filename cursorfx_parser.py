#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CursorFX 二进制文件格式解析器
基于逆向工程和 Metamorphosis 项目的分析

CursorFX 文件结构：
1. 文件头（固定结构）
2. 版权信息（null-terminated string）
3. 光标元数据
4. 压缩的 PNG 图像数据（zlib 压缩）
"""

import struct
import zlib
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json


class CursorFXParser:
    """CursorFX 文件解析器"""
    
    # PNG 文件签名
    PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
    
    # 光标类型映射
    CURSOR_TYPES = {
        0: 'Arrow',           # 箭头
        1: 'Help',            # 帮助
        2: 'AppStarting',     # 应用启动
        3: 'Wait',            # 等待
        4: 'Cross',           # 十字
        5: 'IBeam',           # I型光标
        6: 'Handwriting',     # 手写
        7: 'NO',              # 禁止
        8: 'SizeNS',          # 南北调整
        9: 'SizeS',           # 南调整
        10: 'SizeWE',         # 东西调整
        11: 'SizeE',          # 东调整
        12: 'SizeNWSE',       # 西北东南调整
        13: 'SizeSE',         # 东南调整
        14: 'SizeNESW',       # 东北西南调整
        15: 'SizeSW',         # 西南调整
        16: 'SizeAll',        # 四向调整
        17: 'UpArrow',        # 向上箭头
        18: 'Hand',           # 手型
        19: 'Button',         # 按钮
    }
    
    def __init__(self, filepath: str):
        """初始化解析器
        
        Args:
            filepath: CursorFX 文件路径
        """
        self.filepath = filepath
        self.data = None
        self.metadata = {}
        self.cursors = []
        
    def read_file(self) -> None:
        """读取文件内容"""
        with open(self.filepath, 'rb') as f:
            self.data = f.read()
        print(f"✓ 文件大小: {len(self.data)} 字节")
    
    def parse_header(self) -> Dict:
        """解析文件头
        
        文件头结构（前 16 字节）：
        - 0x00: 版本标识 (uint32)
        - 0x04: 头部大小 (uint32)
        - 0x08: 时间戳 (uint32)
        - 0x0C: 未知字段 (uint32)
        
        Returns:
            包含文件头信息的字典
        """
        header = {}
        
        # 解析固定字段
        header['version'] = struct.unpack_from('<I', self.data, 0)[0]
        header['header_size'] = struct.unpack_from('<I', self.data, 4)[0]
        header['timestamp'] = struct.unpack_from('<I', self.data, 8)[0]
        header['unknown1'] = struct.unpack_from('<I', self.data, 12)[0]
        
        # 解析版权信息（null-terminated string）
        copyright_start = 16
        copyright_end = self.data.find(b'\x00', copyright_start)
        header['copyright'] = self.data[copyright_start:copyright_end].decode('utf-8', errors='ignore')
        
        self.metadata['header'] = header
        
        print("\n=== 文件头解析 ===")
        print(f"版本标识: {header['version']}")
        print(f"头部大小: {header['header_size']} 字节")
        print(f"时间戳: 0x{header['timestamp']:08x}")
        print(f"未知字段: {header['unknown1']}")
        print(f"版权信息: {header['copyright']}")
        
        return header
    
    def find_compressed_data(self) -> List[Tuple[int, bytes]]:
        """查找压缩数据块
        
        CursorFX 使用 zlib 压缩 PNG 图像
        zlib 压缩头特征：78 01, 78 5e, 78 9c, 78 da
        
        Returns:
            压缩数据块列表 [(offset, compressed_data), ...]
        """
        compressed_blocks = []
        
        # 查找所有 zlib 压缩头
        zlib_headers = [b'\x78\x01', b'\x78\x5e', b'\x78\x9c', b'\x78\xda']
        
        # 使用更高效的方法：查找所有 zlib 压缩头位置
        header_positions = []
        for header in zlib_headers:
            pos = 0
            while True:
                pos = self.data.find(header, pos)
                if pos == -1:
                    break
                header_positions.append(pos)
                pos += 1
        
        header_positions.sort()
        print(f"找到 {len(header_positions)} 个可能的 zlib 压缩头位置")
        
        # 尝试解压缩每个位置
        for offset in header_positions:
            # 使用 zlib.decompressobj 进行流式解压缩
            try:
                decompressor = zlib.decompressobj()
                # 尝试解压缩不同长度的数据
                for length in [1000, 5000, 10000, 50000, 100000]:
                    if offset + length > len(self.data):
                        length = len(self.data) - offset
                    
                    try:
                        decompressed = decompressor.decompress(self.data[offset:offset+length])
                        
                        # 检查是否包含 PNG 签名
                        if self.PNG_SIGNATURE in decompressed:
                            # 找到完整的压缩数据
                            compressed_size = offset + length - decompressor.unconsumed_tail
                            compressed_data = self.data[offset:compressed_size]
                            compressed_blocks.append((offset, compressed_data))
                            print(f"✓ 找到压缩数据块在偏移 0x{offset:04x}, 大小 {len(compressed_data)} 字节")
                            break
                    except zlib.error:
                        continue
            except Exception as e:
                continue
        
        return compressed_blocks
    
    def extract_png_images(self, compressed_blocks: List[Tuple[int, bytes]]) -> List[Tuple[int, bytes]]:
        """从压缩数据中提取 PNG 图像
        
        Args:
            compressed_blocks: 压缩数据块列表
            
        Returns:
            PNG 图像列表 [(index, png_data), ...]
        """
        png_images = []
        
        for idx, (offset, compressed_data) in enumerate(compressed_blocks):
            try:
                # 解压缩数据
                decompressed = zlib.decompress(compressed_data)
                
                # 查找 PNG 签名
                png_start = decompressed.find(self.PNG_SIGNATURE)
                
                if png_start >= 0:
                    # 提取完整的 PNG 数据
                    # PNG 文件以 IEND 块结束
                    iend_sig = b'IEND'
                    png_end = decompressed.find(iend_sig, png_start)
                    
                    if png_end >= 0:
                        # IEND 块结构：长度(4) + 类型(4) + CRC(4) = 12 字节
                        png_end += 8  # 包含 IEND 和 CRC
                        png_data = decompressed[png_start:png_end]
                        png_images.append((idx, png_data))
                        
                        print(f"✓ 提取 PNG 图像 #{idx}, 大小 {len(png_data)} 字节")
            except Exception as e:
                print(f"✗ 解压缩块 #{idx} 失败: {e}")
        
        return png_images
    
    def parse_cursor_metadata(self, offset: int) -> Optional[Dict]:
        """解析光标元数据
        
        光标元数据结构（推测）：
        - 光标类型 ID
        - 热点 X 坐标
        - 热点 Y 坐标
        - 图像宽度
        - 图像高度
        - 帧数（动画）
        - 帧延迟
        
        Args:
            offset: 元数据起始偏移
            
        Returns:
            光标元数据字典
        """
        try:
            metadata = {}
            
            # 读取光标类型
            cursor_type = struct.unpack_from('<I', self.data, offset)[0]
            metadata['type_id'] = cursor_type
            metadata['type_name'] = self.CURSOR_TYPES.get(cursor_type, f'Unknown_{cursor_type}')
            
            # 读取热点坐标（推测位置）
            metadata['hotspot_x'] = struct.unpack_from('<I', self.data, offset + 4)[0]
            metadata['hotspot_y'] = struct.unpack_from('<I', self.data, offset + 8)[0]
            
            # 读取尺寸（推测位置）
            metadata['width'] = struct.unpack_from('<I', self.data, offset + 12)[0]
            metadata['height'] = struct.unpack_from('<I', self.data, offset + 16)[0]
            
            return metadata
        except Exception as e:
            print(f"✗ 解析元数据失败: {e}")
            return None
    
    def save_png_images(self, png_images: List[Tuple[int, bytes]], output_dir: str) -> None:
        """保存 PNG 图像到文件
        
        Args:
            png_images: PNG 图像列表
            output_dir: 输出目录
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for idx, png_data in png_images:
            filename = output_path / f"cursor_{idx:02d}.png"
            with open(filename, 'wb') as f:
                f.write(png_data)
            print(f"✓ 保存图像: {filename}")
    
    def analyze_structure(self) -> None:
        """分析文件结构"""
        print("\n=== 文件结构分析 ===")
        
        # 显示前 256 字节的十六进制和 ASCII
        print("\n前 256 字节十六进制视图:")
        for i in range(0, min(256, len(self.data)), 16):
            hex_str = ' '.join(f'{b:02x}' for b in self.data[i:i+16])
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in self.data[i:i+16])
            print(f"{i:04x}: {hex_str}  {ascii_str}")
        
        # 查找关键标记
        print("\n关键标记位置:")
        
        # PNG 签名
        png_pos = self.data.find(self.PNG_SIGNATURE)
        if png_pos >= 0:
            print(f"PNG 签名位置: 0x{png_pos:04x}")
        else:
            print("PNG 签名: 未找到（可能被压缩）")
        
        # zlib 压缩头
        zlib_headers = [(b'\x78\xda', '最大压缩'), (b'\x78\x9c', '默认压缩'), 
                        (b'\x78\x5e', '快速压缩'), (b'\x78\x01', '无压缩')]
        
        for header, desc in zlib_headers:
            pos = self.data.find(header)
            if pos >= 0:
                print(f"zlib 压缩头 ({desc}): 0x{pos:04x}")
    
    def parse(self) -> Dict:
        """完整解析 CursorFX 文件
        
        Returns:
            包含所有解析结果的字典
        """
        print(f"\n{'='*60}")
        print(f"CursorFX 文件解析器")
        print(f"{'='*60}")
        print(f"文件: {self.filepath}")
        
        # 读取文件
        self.read_file()
        
        # 解析文件头
        header = self.parse_header()
        
        # 分析文件结构
        self.analyze_structure()
        
        # 查找压缩数据
        print("\n=== 查找压缩数据 ===")
        compressed_blocks = self.find_compressed_data()
        
        # 提取 PNG 图像
        print("\n=== 提取 PNG 图像 ===")
        png_images = self.extract_png_images(compressed_blocks)
        
        # 汇总结果
        result = {
            'metadata': self.metadata,
            'compressed_blocks_count': len(compressed_blocks),
            'png_images_count': len(png_images),
            'png_images': png_images,
        }
        
        print(f"\n{'='*60}")
        print(f"解析完成")
        print(f"{'='*60}")
        print(f"压缩数据块: {len(compressed_blocks)}")
        print(f"PNG 图像: {len(png_images)}")
        
        return result


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='CursorFX 二进制文件解析器')
    parser.add_argument('file', help='CursorFX 文件路径')
    parser.add_argument('-o', '--output', help='PNG 图像输出目录', default='./extracted_pngs')
    parser.add_argument('-s', '--save', help='保存 PNG 图像', action='store_true')
    
    args = parser.parse_args()
    
    # 创建解析器
    cursorfx_parser = CursorFXParser(args.file)
    
    # 解析文件
    result = cursorfx_parser.parse()
    
    # 保存 PNG 图像
    if args.save and result['png_images']:
        print(f"\n保存 PNG 图像到: {args.output}")
        cursorfx_parser.save_png_images(result['png_images'], args.output)


if __name__ == '__main__':
    main()
