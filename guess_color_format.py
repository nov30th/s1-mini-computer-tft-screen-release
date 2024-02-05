#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

import numpy as np

# 假设pixels是一个包含像素数据的numpy数组
"""
A5 77 B6 19 B6 19 B6 39 BE 5A BE 5A BE 5A BE 5A BE 5A BE 5A BE 5A BE 5A BE 3A BE 3A B6 19 B6 3A BE 5A BE 3A BE 3A BE 3A BE 3A BE 3A BE 3A B6 3A B6 3A BE 3A BE 3A BE 3A B6 19 B5 F9 BE 3A BE 3A B6 19 B6 19 B6 19 B6 19 B6 3A AD D8 84 93 4A CC 3A 4A 32 2A 29 C8 11 26 19 67 19 66 3A 4A BE 5A 5B 4D 31 E8 AD B7 7C 51 21 66 31 C8 31 E8 29 C8 21 87 21 66 21 66 21 66 19 46 29 A7 3A 09 84 52 84 52 21 86 29 A7 4A CB 19 25 29 66 19 25 29 86 19 25 21 66 3A 08 21 66 10 C3 21 46 32 09 31 E8 21 86 21 45 10 E4 31 E8 32 09 19 25 08 C2 11 04 29 A7 19 25 11 24 19 24 00 00 18 E3 29 86 21 65 21 45 21 26 19 25 19 25 19 25 19 25 19 25 19 25 19 25 19 25 19 25 19 05 19 05 19 05 19 05 11 05 10 C4 10 C4 10 A4 10 A4 10 C4 42 6A 52 EC 29 A7 10 E4 10 E4 10 A4 10 C4 08 A3 08 83 08 C4 08 A4 10 C4 08 C4 08 C4 00 83 00 42 08 83 10 C4 08 A3 08 A3 08 C4 10 E4 11 05 10 C4 08 C4 08 C4 08 C4
"""

data = "A5 77 B6 19 B6 19 B6 39 BE 5A BE 5A BE 5A BE 5A BE 5A BE 5A BE 5A BE 5A BE 3A BE 3A B6 19 B6 3A BE 5A BE 3A BE 3A BE 3A BE 3A BE 3A BE 3A B6 3A B6 3A BE 3A BE 3A BE 3A B6 19 B5 F9 BE 3A BE 3A B6 19 B6 19 B6 19 B6 19 B6 3A AD D8 84 93 4A CC 3A 4A 32 2A 29 C8 11 26 19 67 19 66 3A 4A BE 5A 5B 4D 31 E8 AD B7 7C 51 21 66 31 C8 31 E8 29 C8 21 87 21 66 21 66 21 66 19 46 29 A7 3A 09 84 52 84 52 21 86 29 A7 4A CB 19 25 29 66 19 25 29 86 19 25 21 66 3A 08 21 66 10 C3 21 46 32 09 31 E8 21 86 21 45 10 E4 31 E8 32 09 19 25 08 C2 11 04 29 A7 19 25 11 24 19 24 00 00 18 E3 29 86 21 65 21 45 21 26 19 25 19 25 19 25 19 25 19 25 19 25 19 25 19 25 19 25 19 05 19 05 19 05 19 05 11 05 10 C4 10 C4 10 A4 10 A4 10 C4 42 6A 52 EC 29 A7 10 E4 10 E4 10 A4 10 C4 08 A3 08 83 08 C4 08 A4 10 C4 08 C4 08 C4 00 83 00 42 08 83 10 C4 08 A3 08 A3 08 C4 10 E4 11 05 10 C4 08 C4 08 C4 08 C4"
pixels = np.array([int(x, 16) for x in data.split()])

# 分析像素值范围
max_value = pixels.max()
min_value = pixels.min()
print(f"Max value: {max_value}, Min value: {min_value}")

# 位掩码和右移位数
formats = {
    "4-4-4-4": {"masks": [(0xF000, 12), (0x0F00, 8), (0x00F0, 4), (0x000F, 0)], "range": 15},
    "5-5-5-1": {"masks": [(0xF800, 11), (0x07C0, 6), (0x003E, 1), (0x0001, 0)], "range": 31},  # 注意Alpha通道为1位
    "5-6-5": {"masks": [(0xF800, 11), (0x07E0, 5), (0x001F, 0)], "range": [31, 63, 31]},  # 绿色通道范围特殊
    "3-3-2": {"masks": [(0xE0, 5), (0x1C, 2), (0x03, 0)], "range": 7}
}


def analyze_pixel_format(pixels, formats):
    for format_name, info in formats.items():
        valid = True
        channel_ranges = info["range"] if isinstance(info["range"], list) else [info["range"]] * len(info["masks"])

        for (mask, shift), channel_range in zip(info["masks"], channel_ranges):
            channel_values = (pixels & mask) >> shift
            if not (channel_values.max() <= channel_range and channel_values.min() >= 0):
                valid = False
                break

        if valid:
            print(f"Format {format_name} could be valid.")
        else:
            print(f"Format {format_name} is not valid.")


analyze_pixel_format(pixels, formats)
