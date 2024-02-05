#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

from PIL import Image

# Open the png file and convert it to RGB mode
png = Image.open("image.png").convert("RGB")

# Create a new bitmap image with the same size and 16-bit color depth
bmp = Image.new("RGB", png.size, (0, 0, 0))
bmp = bmp.convert("RGB;16")

# Copy the pixel data from the png to the bitmap
bmp_data = bmp.load()
png_data = png.load()
width, height = png.size
for x in range(width):
    for y in range(height):
        bmp_data[x, y] = png_data[x, y]

print(len(bmp.tobytes()))

# # Save the bitmap image as a binary file
# with open("image.bin", "wb") as f:
#     f.write(bmp.tobytes())
