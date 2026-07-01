#!/usr/bin/env python3
"""生成占位贴图（独立运行，不依赖 PIL）"""
import struct
import zlib
import os


def create_png(width, height, r, g, b, filepath):
    """创建纯色 PNG"""
    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        return struct.pack('>I', len(data)) + chunk + struct.pack('>I', zlib.crc32(chunk) & 0xffffffff)

    # PNG signature
    signature = b'\x89PNG\r\n\x1a\n'

    # IHDR
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    ihdr = make_chunk(b'IHDR', ihdr_data)

    # IDAT - raw pixel data (RGB)
    raw_data = b''
    for y in range(height):
        raw_data += b'\x00'  # filter byte
        for x in range(width):
            raw_data += struct.pack('BBB', r, g, b)

    compressed = zlib.compress(raw_data)
    idat = make_chunk(b'IDAT', compressed)

    # IEND
    iend = make_chunk(b'IEND', b'')

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        f.write(signature + ihdr + idat + iend)
    print("Created: %s (%dx%d)" % (filepath, width, height))


def main():
    mod_dir = "d:/MCStudioDownload/work/z2710468140@163.com/Cpp/AddOn/pianoMod"
    res_dir = mod_dir + "/resource_pack_2GYBUGDZ"

    # 方块贴图 (64x64)
    create_png(64, 64, 101, 67, 33, res_dir + "/textures/music_box_block.png")  # 深棕色

    # 物品贴图 (16x16)
    create_png(16, 16, 220, 220, 200, res_dir + "/textures/items/blank_sheet.png")   # 米白色
    create_png(16, 16, 255, 215, 0,   res_dir + "/textures/items/preset_sheet.png")  # 金色
    create_png(16, 16, 70,  130, 220, res_dir + "/textures/items/custom_sheet.png")  # 蓝色

    print("\n所有占位贴图已生成！")
    print("提示：这些是纯色占位图，请用实际美术资源替换。")


if __name__ == "__main__":
    main()
