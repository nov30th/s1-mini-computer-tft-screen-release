#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def get_text_dimensions(text_string, font):
    # https://stackoverflow.com/a/46220683/9263761
    ascent, descent = font.getmetrics()

    text_width = font.getmask(text_string).getbbox()[2]
    text_height = font.getmask(text_string).getbbox()[3] + descent

    return text_width, text_height


# 计算Alpha合成的函数
def alpha_composite(background, foreground, alpha):
    return foreground * (alpha / 255.0) + background * (1 - alpha / 255.0)


# 步骤1: 读取图像
image = Image.open('init.png').convert('RGBA')

# 步骤2: 在图像上添加文本
draw = ImageDraw.Draw(image, 'RGBA')
font = ImageFont.truetype('arial.ttf', 10)  # 选择字体和大小
text = "Current Status: OK"

text_position = (20, 20)  # 文字的起始位置

text_width, text_height = get_text_dimensions(text, font)
padding = 10  # 文字与矩形边缘的间距
x0, y0 = text_position[0] - padding, text_position[1] - padding
x1, y1 = x0 + text_width + 2 * padding, y0 + text_height + 2 * padding

# # 在文字位置绘制半透明的黑色矩形作为背景
# draw.rectangle((x0, y0, x1, y1), fill=(0, 0, 0, 20))  # 128是半透明的alpha值


# 转换图像为NumPy数组
image_array = np.array(image)

# Alpha合成 - 将半透明矩形与背景合成
alpha_value = 128  # Alpha值，128表示50%透明度
for y in range(y0, y1):
    for x in range(x0, x1):
        bg_color = image_array[y, x, :3]  # 背景颜色
        fg_color = np.array([0, 0, 0])  # 前景色（黑色）
        composite_color = alpha_composite(bg_color, fg_color, alpha_value)
        image_array[y, x, :3] = composite_color.astype(np.uint8)

# 将合成后的图像转换回PIL图像，以便添加文字
image = Image.fromarray(image_array)
draw = ImageDraw.Draw(image, 'RGBA')

# 在半透明的矩形上绘制文字
draw.text(text_position, text, fill=(255, 255, 255, 255), font=font)  # 使用完全不透明的白色

image_array = np.array(image)


# 执行RGB到RGB565的转换
def rgb_to_rgb565(image_array):
    r = (image_array[:, :, 0] >> 3).astype(np.uint16)
    g = (image_array[:, :, 1] >> 2).astype(np.uint16)
    b = (image_array[:, :, 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    return rgb565


rgb565_array = rgb_to_rgb565(image_array)
# 在将数据写入之前执行字节交换
# 注意：'byteswap'方法不改变原数组，返回一个新数组
rgb565_bytes_swapped = rgb565_array.byteswap().tobytes()

# 保存或处理转换后的字节数据
with open('modified_image.bin', 'wb') as f:
    f.write(rgb565_bytes_swapped)
