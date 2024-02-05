#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

import numpy as np
from PIL import Image


def resize_and_crop_image(input_image_path, output_size=(320, 170)):
    # 打开图片
    with Image.open(input_image_path) as img:
        # 计算缩放比例
        img_ratio = img.width / img.height
        target_ratio = output_size[0] / output_size[1]

        # 缩放图片
        if img_ratio > target_ratio:
            # 图片过宽
            new_height = output_size[1]
            new_width = int(new_height * img_ratio)
        else:
            # 图片过高
            new_width = output_size[0]
            new_height = int(new_width / img_ratio)

        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 裁切图片
        left = (new_width - output_size[0]) / 2
        top = (new_height - output_size[1]) / 2
        right = (new_width + output_size[0]) / 2
        bottom = (new_height + output_size[1]) / 2

        img_cropped = img_resized.crop((left, top, right, bottom))

        return img_cropped


def convert_to_332(image):
    np_image = np.array(image)
    r = (np_image[:, :, 0] >> 5) << 5  # 红色占最高的3位
    g = (np_image[:, :, 1] >> 5) << 2  # 绿色占次高的3位
    b = np_image[:, :, 2] >> 6  # 蓝色占最低的2位
    rgb_332 = r | g | b
    return rgb_332


def convert_to_4444(image):
    np_image = np.array(image)
    r = (np_image[:, :, 0] >> 4) << 12  # 红色移至最高的4位
    g = (np_image[:, :, 1] >> 4) << 8  # 绿色移至次高的4位
    b = (np_image[:, :, 2] >> 4) << 4  # 蓝色移至次低的4位
    a = 0  # Alpha通道移至最低的4位，假设图像具有Alpha通道
    rgba_4444 = r | g | b | a
    return rgba_4444


def convert_to_5551(image):
    np_image = np.array(image)
    r = (np_image[:, :, 0] >> 3) << 11  # 红色移至最高的5位
    g = (np_image[:, :, 1] >> 3) << 6  # 绿色移至次高的5位
    b = (np_image[:, :, 2] >> 3) << 1  # 蓝色移至次低的5位
    a = 0x1  # Alpha通道只取最高位，转换为1位
    rgb_5551 = r | g | b | a
    return rgb_5551


def convert_to_565(image):
    # 将图片数据转换为NumPy数组
    np_image = np.array(image)
    np_image = np_image.astype(np.uint16)

    # 提取RGB通道并转换为5-6-5格式
    r = (np_image[:, :, 0] >> 3) << 11
    g = (np_image[:, :, 1] >> 2) << 5
    b = np_image[:, :, 2] >> 3
    rgb_565 = r | g | b
    return rgb_565


def convert_to_555(image):
    # 将图片数据转换为NumPy数组
    np_image = np.array(image)
    # 提取RGB通道并转换为5-5-5格式
    # 注意：最后一位我们将其设置为0，因此每个通道仍然是5位
    r = (np_image[:, :, 0] >> 3).astype(np.uint16) << 10  # 红色通道移动到最高的5位
    g = (np_image[:, :, 1] >> 3).astype(np.uint16) << 5  # 绿色通道移动到中间的5位
    b = (np_image[:, :, 2]).astype(np.uint16) >> 3  # 蓝色通道保留在最低的5位
    rgb_555 = r | g | b  # 合并三个通道
    return rgb_555


def process_image(image_path):
    # 调整图片大小并裁切
    img_cropped = resize_and_crop_image(image_path)
    # 转换颜色格式
    img_565 = convert_to_565(img_cropped)
    # img_565 = convert_to_555(img_cropped)
    # 将二维数组转换为一维数组
    img_array = img_565.flatten()
    return img_array


def process_image_main(input_filename='init.png', output_filename='image_init.bin'):
    global img_bytes
    # 用你的图片路径替换 'a.jpg'
    image_array = process_image(input_filename)
    # 首先，确保数据类型为uint16
    img_array_uint16 = image_array.astype(np.uint16)
    # 交换字节序
    img_array_byteswap = img_array_uint16.byteswap().newbyteorder()
    # 然后，转换为字节串
    img_bytes = img_array_byteswap.tobytes()
    # save image_array as bin file for test, name is image.bin
    with open(output_filename, "wb") as f:
        f.write(img_bytes)
        print(rf"{output_filename} has been saved")


def bytes_to_image(img_bytes, output_size=(320, 170), output_path='image.png'):
    # 将字节数据转换为16位的numpy数组
    img_array = np.frombuffer(img_bytes, dtype=np.uint16)

    # 确保数组是正确的形状（一维数组转换为二维像素阵列）
    img_array = img_array.reshape(output_size[1], output_size[0])

    # 初始化一个空的RGB数组
    rgb_array = np.zeros((output_size[1], output_size[0], 3), dtype=np.uint8)

    # 将5-6-5格式的颜色值转换回RGB格式
    rgb_array[:, :, 0] = ((img_array >> 11) & 0x1F) << 3  # 红色
    rgb_array[:, :, 1] = ((img_array >> 5) & 0x3F) << 2  # 绿色
    rgb_array[:, :, 2] = (img_array & 0x1F) << 3  # 蓝色

    # 使用Pillow创建一个新图片
    img = Image.fromarray(rgb_array, 'RGB')

    # 保存图片
    img.save(output_path)


#
# # 假设 img_bytes 是你之前转换得到的字节数据
# # 使用函数保存为图片
# bytes_to_image(img_bytes, output_size=(320, 170), output_path='image.png')

process_image_main("init.png", "image_init.bin")
process_image_main("warn.png", "image_warn.bin")
process_image_main("error.png", "image_error.bin")
