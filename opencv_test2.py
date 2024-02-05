#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

import cv2
import numpy as np


def convert_to_565(image):
    # 将图片数据转换为NumPy数组
    np_image = np.array(image)
    # 提取RGB通道并转换为5-6-5格式
    r = (np_image[:, :, 0] >> 3) << 11
    g = (np_image[:, :, 1] >> 2) << 5
    b = np_image[:, :, 2] >> 3
    rgb_565 = r | g | b
    return rgb_565


# Open the png file and convert it to RGB mode
png = cv2.imread("whole.png", cv2.IMREAD_COLOR)
png_converted = convert_to_565(png)
# Create a new bitmap image with the same size and 16-bit color depth
bmp = cv2.cvtColor(png, cv2.COLOR_BGR2RGB)
bmp = bmp.astype("uint16")

print(len(bmp.tobytes()))
# Save the bitmap image as a binary file
with open("image222.bin", "wb") as f:
    f.write(bmp.tobytes())
