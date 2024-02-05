#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

import asyncio
import os
import sys
import time
# noinspection PyUnresolvedReferences
from sys import exit

import hid
import numpy as np
import psutil
from PIL import Image, ImageDraw, ImageFont

# 全局变量来存储设备实例
global_device = None
# 控制是否发送背景数据的标志
is_sending_background = False
version = "0.0.1"

network_latest_recv = 0
network_latest_recv_snapshot_at = 0
network_latest_sent = 0
network_latest_sent_snapshot_at = 0


def get_text_dimensions(text_string, font):
    ascent, descent = font.getmetrics()
    text_width = font.getmask(text_string).getbbox()[2]
    text_height = font.getmask(text_string).getbbox()[3] + descent
    return text_width, text_height


def alpha_composite(background, foreground, alpha):
    return foreground * (alpha / 255.0) + background * (1 - alpha / 255.0)


def add_text_and_border(image, text, position, padding):
    draw = ImageDraw.Draw(image, 'RGBA')
    font = ImageFont.truetype('fonts/JetBrainsMono-Regular-2.ttf', 16)
    text_width, text_height = get_text_dimensions(text, font)
    x0, y0 = position[0] - padding, position[1] - padding
    x1, y1 = x0 + text_width + 2 * padding, y0 + text_height + 2 * padding
    image_array = np.array(image)
    alpha_value = 160
    for y in range(y0, y1):
        for x in range(x0, x1):
            bg_color = image_array[y, x, :3]
            fg_color = np.array([0, 0, 0])
            composite_color = alpha_composite(bg_color, fg_color, alpha_value)
            image_array[y, x, :3] = composite_color.astype(np.uint8)
    image = Image.fromarray(image_array)
    draw = ImageDraw.Draw(image, 'RGBA')
    draw.text(position, text, fill=(255, 255, 255, 255), font=font)
    return image


def load_image(loading=False):
    if loading:
        # if not found the image, show error
        if not os.path.exists("images/init.png"):
            print("Error: images/init.png not found.")
            sys.exit(1)
        image = Image.open("images/init.png").convert('RGBA')
        text = "Still under development"
        text2 = "Demo version"
        # text_position = (50, 50)
        # text_position2 = (70, 110)
        # padding = 5
        # image = add_text_and_border(image, text, text_position, padding)
        # image = add_text_and_border(image, text2, text_position2, padding)
    else:
        cpu = get_cpu_usage()
        memory = get_memory_usage()
        disk = get_disk_usage()

        if memory > 90 or disk > 90:
            image_filename = "images/error.png"
        else:
            if cpu > 80 or memory > 80 or disk > 80:
                image_filename = "images/warn.png"
            else:
                image_filename = "images/init.png"

        image = Image.open(image_filename).convert('RGBA')

        text = "Network IP: " + get_network_ip()
        text_position = (20, 25)
        padding = 5
        image = add_text_and_border(image, text, text_position, padding)

        text = " " + str(cpu) + "%"
        text_position = (46, 55)
        padding = 5
        image = add_text_and_border(image, text, text_position, padding)

        text = " " + str(memory) + "%"
        text_position = (46, 85)
        padding = 5
        image = add_text_and_border(image, text, text_position, padding)

        text = " " + str(disk) + "%"
        text_position = (46, 115)
        padding = 5
        image = add_text_and_border(image, text, text_position, padding)

        network = get_network_traffic()
        if network:
            global network_latest_recv, network_latest_sent, network_latest_recv_snapshot_at, network_latest_sent_snapshot_at
            if network['sent'] < network_latest_sent or network_latest_sent == 0:
                network_latest_sent = network['sent']
                network_latest_sent_snapshot_at = time.time() - 1
            if network['recv'] < network_latest_recv or network_latest_recv == 0:
                network_latest_recv = network['recv']
                network_latest_recv_snapshot_at = time.time() - 1
            sent_diff = network['sent'] - network_latest_sent
            sent_diff_per_second = sent_diff / (time.time() - network_latest_sent_snapshot_at)
            recv_diff = network['recv'] - network_latest_recv
            recv_diff_per_second = recv_diff / (time.time() - network_latest_recv_snapshot_at)
            network_latest_sent = network['sent']
            network_latest_sent_snapshot_at = time.time()
            network_latest_recv = network['recv']
            network_latest_recv_snapshot_at = time.time()

            # if more than 1MB use MB, less than 1MB use KB, sent and recv use two different var
            if sent_diff_per_second > 1024 * 1024:
                sent = str(round(sent_diff_per_second / 1024 / 1024, 2)) + "MB"
            else:
                sent = str(round(sent_diff_per_second / 1024, 2)) + "KB"
            if recv_diff_per_second > 1024 * 1024:
                recv = str(round(recv_diff_per_second / 1024 / 1024, 2)) + "MB"
            else:
                recv = str(round(recv_diff_per_second / 1024, 2)) + "KB"

            combo_text = "S: " + sent + " R: " + recv
        else:
            combo_text = "Not Detected"

        text = " " + combo_text
        text_position = (46, 145)
        padding = 5
        image = add_text_and_border(image, text, text_position, padding)

        # Load the icon images
        cpu_icon = Image.open('images/cpuicon.png').resize((30, 30))
        memory_icon = Image.open('images/memoryicon.png').resize((30, 30))
        disk_icon = Image.open('images/diskicon.png').resize((30, 30))
        network_icon = Image.open('images/networkicon.png').resize((30, 30))

        # Paste the icons onto the main image
        image.paste(cpu_icon, (15, 50), cpu_icon.convert('RGBA'))
        image.paste(memory_icon, (15, 80), cpu_icon.convert('RGBA'))
        image.paste(disk_icon, (15, 110), cpu_icon.convert('RGBA'))
        image.paste(network_icon, (15, 140), cpu_icon.convert('RGBA'))

    image_array = np.array(image)
    return image_array


# 执行RGB到RGB565的转换
def rgb_to_rgb565(image_array):
    r = (image_array[:, :, 0] >> 3).astype(np.uint16)
    g = (image_array[:, :, 1] >> 2).astype(np.uint16)
    b = (image_array[:, :, 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    return rgb565


def open_device_by_id(vendor_id, product_id):
    global global_device
    print("Now Searching....")
    devices = hid.enumerate(vendor_id, product_id)
    target_device_info = next((device for device in devices if device['vendor_id'] == vendor_id and device['product_id'] == product_id), None)
    if target_device_info:
        try:
            device = hid.device()
            device.open(vendor_id, product_id)
            print(f"Opened S1 mini computer TFT screen device successfully.")
            global_device = device
            return True
        except IOError as e:
            print(f"Could not open the S1 mini computer TFT screen device.")
            # show error details and stack
            print(e)
            print(e.with_traceback())
            return False
    else:
        print(f"No S1 mini computer TFT screen device found.")
        return False


async def open_device_async(vendor_id, product_id):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, open_device_by_id, vendor_id, product_id)
    if not result:
        print("Error opening device. Exiting after 10 seconds.")
        # list all hid usb devices
        print(hid.enumerate())
        await asyncio.sleep(10)
        sys.exit(1)
    print("Device opened successfully.")


def hex_string_to_byte_array_with_00(hex_string, total_length=4104):
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    bytes_to_add = total_length - len(byte_data)
    if bytes_to_add > 0:
        byte_data += bytes([0x00]) * bytes_to_add
    return byte_data


def send_data(device, data):
    if device:
        try:
            data_with_report_id = [0] + list(data)
            device.write(data_with_report_id)
            # print("Data sent successfully.")
        except IOError as e:
            # print(f"Error sending data: {e}")
            pass


def hex_string_to_byte_array_normal(hex_string):
    # Remove spaces and convert to bytes
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    return byte_data


async def periodic_refresh_screen():
    while True:
        await asyncio.sleep(5)
        await sends_testing_background()


async def periodic_send_data():
    global is_sending_background
    while True:
        if not is_sending_background and global_device is not None:
            pre_end_data = "55 a1 f2 "
            current_hour = int(time.strftime("%H"))
            current_minute = int(time.strftime("%M"))
            current_second = int(time.strftime("%S"))
            pre_end_data += format(current_hour, '02x') + " " + format(current_minute, '02x') + " " + format(current_second, '02x')
            data_to_send = hex_string_to_byte_array_normal(pre_end_data)
            send_data(global_device, data_to_send)
        await asyncio.sleep(0.5)


def hex_string_to_byte_array(hex_string, total_length=4104):
    # Remove spaces and convert to bytes
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    # Calculate the number of bytes to add to make the data reach the desired length
    bytes_to_add = total_length - len(byte_data)
    if bytes_to_add > 0:
        # Append the necessary number of 0x00 bytes
        byte_data += bytes([0x00]) * bytes_to_add
    return byte_data


async def sends_testing_background(loading=False):
    global is_sending_background
    is_sending_background = True
    try:
        print("Sending background data...")
        # 你的sends_testing_background逻辑
        # 请在这里添加相应的异步发送数据代码

        pre_end_data = "55 a1 f2 00 00 00"
        data_to_send = hex_string_to_byte_array_with_00(pre_end_data)
        send_data(global_device, data_to_send)

        org_image_array = load_image(loading)
        rgb565_array = rgb_to_rgb565(org_image_array)
        image_array = rgb565_array.byteswap().tobytes()

        for x in range(0, 26):
            x_str = format(x + 1, '02x')
            second_str = format(x % 16, 'x')
            pre_str = '0' if x == 0 else '1'
            # pre_str = str(int((x+1)/16))
            hex_data = "55 A3 F" + pre_str + " " + x_str + " 00 " + second_str + "0 00 10"
            # print(hex_data)
            # adds top 4096 bytes of image_array after hex_data, and removes the 4096 bytes from image_array
            if len(image_array) >= 4096:
                hex_data = hex_data + " " + image_array[:4096].hex()
                image_array = image_array[4096:]
            hex_string_to_byte_array(hex_data)
            data_to_send = hex_string_to_byte_array(hex_data)
            send_data(global_device, data_to_send)
        pre_end_data = "55 A3 F2 1B 00 A0 00 09"

        if len(image_array) > 4096:
            print("ERROR! too large for end")
            sys.exit(1)
        pre_end_data = pre_end_data + " " + image_array.hex()
        data_to_send = hex_string_to_byte_array_with_00(pre_end_data)
        send_data(global_device, data_to_send)
        end_data = "55 A1 F1 01"
        data_to_send = hex_string_to_byte_array(end_data)
        send_data(global_device, data_to_send)
    except Exception as e:
        print(f"Error sending background data: {e}")
    finally:
        is_sending_background = False
    print("Background data sent successfully.")


# 获取网卡的每秒流量
def get_network_traffic():
    net_io = psutil.net_io_counters(pernic=True)
    traffic_details = {}
    for interface, io_counters in net_io.items():
        traffic_details[interface] = {
            'sent': io_counters.bytes_sent,
            'recv': io_counters.bytes_recv
        }
        break
    # returns first interface
    if len(traffic_details) == 0:
        return None
    return traffic_details[list(traffic_details.keys())[0]]


def get_network_ip():
    import socket
    return socket.gethostbyname(socket.gethostname())


def get_disk_usage():
    return psutil.disk_usage('/').percent


def get_memory_usage():
    return psutil.virtual_memory().percent


def get_cpu_usage():
    return psutil.cpu_percent(interval=1)


async def main():
    print("Starting up HOHO`` TFT Screen Controller..")
    print("Version:", version)
    print("Author: Nov30th, HOHO``")
    print("Initializing device..")
    await open_device_async(1241, 64769)  # 异步打开设备

    if global_device:
        send_task = asyncio.create_task(periodic_send_data())
        refresh_task = asyncio.create_task(periodic_refresh_screen())
        await sends_testing_background(loading=True)
        # send_task.cancel()  # 取消周期性发送任务
        # read input line
        await asyncio.sleep(99999)


if __name__ == "__main__":
    asyncio.run(main())
