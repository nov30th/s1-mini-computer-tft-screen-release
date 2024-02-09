#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``
import asyncio
import base64
import json
import os
import sys
import time
# noinspection PyUnresolvedReferences
from sys import exit

import aiohttp
# import cv2
import hid
import numpy as np
import psutil
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from PIL import Image, ImageDraw, ImageFont
from proxmoxer import ProxmoxAPI
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

# Disable InsecureRequestWarning
disable_warnings(InsecureRequestWarning)

# 全局变量来存储设备实例
global_device = None
# 控制是否发送背景数据的标志
is_sending_background = False
version = "0.0.1"

network_latest_recv = 0
network_latest_recv_snapshot_at = 0
network_latest_sent = 0
network_latest_sent_snapshot_at = 0

device_opened = False

prev_net_stats = {}  # 保存前一次的网络流量状态

image_type = ""


def verify_image(image_path, signature_base64):
    # 读取公钥
    with open("keys/public.pem", "rb") as pub_file:
        public_key = RSA.import_key(pub_file.read())

    # calc public.pem md5 hash
    with open("keys/public.pem", "rb") as pub_file:
        pub_data = pub_file.read()
        pub_md5 = SHA256.new(pub_data).hexdigest()
        if pub_md5 != '9d2cc7c5a47584db70975feccb9dd526d5e39fee8809fa1836c24e134f1fcf47':
            return False
        # print(f"public.pem md5: {pub_md5}")

    # 读取图片数据
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()

    # 生成摘要
    hash = SHA256.new(image_data)

    # 验证签名
    try:
        signature = base64.b64decode(signature_base64)
        verifier = pkcs1_15.new(public_key)
        verifier.verify(hash, signature)
        return True
    except (ValueError, TypeError):
        return False


def load_image_file(filename: str):
    if not os.path.exists("images/load_data.txt"):
        print("Error: images/load_data.txt not found.")
        sys.exit(1)
    with open("images/load_data.txt", "r") as load_data_file:
        for line in load_data_file:
            image_uuid, image_name, signature_base64 = line.strip().split("|")
            if image_name == filename:
                image_path = os.path.join("images", image_name)
                # verify image
                result = verify_image(image_path, signature_base64)
                if result:
                    return Image.open(rf"images/{image_name}")

    print(rf"{filename} image not found")
    time.sleep(5)
    exit(1)


def get_text_dimensions(text_string, font):
    ascent, descent = font.getmetrics()
    text_width = font.getmask(text_string).getbbox()[2]
    text_height = font.getmask(text_string).getbbox()[3] + descent
    return text_width, text_height


def alpha_composite(background, foreground, alpha):
    return foreground * (alpha / 255.0) + background * (1 - alpha / 255.0)


def add_text_only(image, text, position, color=(255, 255, 255, 255)):
    draw = ImageDraw.Draw(image, 'RGBA')
    font = ImageFont.truetype('fonts/JetBrainsMono-Regular-2.ttf', 18)
    draw.text(position, text, fill=color, font=font)
    return image


def add_border_only(image, start_position, end_position):
    alpha_value = 160
    image_array = np.array(image)
    for y in range(start_position[1], end_position[1]):
        for x in range(start_position[0], end_position[0]):
            bg_color = image_array[y, x, :3]
            fg_color = np.array([0, 0, 0])
            composite_color = alpha_composite(bg_color, fg_color, alpha_value)
            image_array[y, x, :3] = composite_color.astype(np.uint8)
    image = Image.fromarray(image_array)
    return image


def add_text_and_border(image, text, position, padding):
    font = ImageFont.truetype('fonts/JetBrainsMono-Regular-2.ttf', 15)
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


async def fetch_status(proxmox, node_name, item, item_type, prev_net_stats):
    """异步获取VM或CT的状态信息，并计算网速"""
    if item_type == 'lxc':
        status = proxmox.nodes(node_name).lxc(item['vmid']).status.current.get()
    else:  # qemu
        status = proxmox.nodes(node_name).qemu(item['vmid']).status.current.get()

    vmid = status['vmid']
    netin = status['netin']
    netout = status['netout']
    # 计算网速
    if vmid in prev_net_stats:
        calc_time = prev_net_stats[vmid]['calc_time']
        netin_speed = (netin - prev_net_stats[vmid]['netin']) / (time.time() - calc_time)
        netout_speed = (netout - prev_net_stats[vmid]['netout']) / (time.time() - calc_time)
        if netin_speed < 0 or netout_speed < 0:
            netin_speed, netout_speed = 0, 0
    else:
        netin_speed, netout_speed = 0, 0  # 首次检查，无法计算网速

    # 更新当前状态以用于下一次计算
    prev_net_stats[vmid] = {'netin': netin, 'netout': netout, 'calc_time': time.time()}

    net_speed = netin_speed + netout_speed
    return status, net_speed


async def load_image_pve(loading=False):
    height = 170
    width = 320
    with open("config.json", "r") as f:
        config = json.load(f)
    proxmox = ProxmoxAPI(config['proxmox_host'], user=config['proxmox_user'], password=config['proxmox_password'],
                         verify_ssl=False)

    nodes = proxmox.nodes.get()
    running_items = []

    for node in nodes:
        node_name = node['node']
        # 获取该节点上的所有CT和VM
        containers = proxmox.nodes(node_name).lxc.get()
        virtual_machines = proxmox.nodes(node_name).qemu.get()

        # 异步获取所有CT和VM的状态
        # 异步获取所有CT和VM的状态，并计算网速
        tasks = [fetch_status(proxmox, node_name, item, 'lxc', prev_net_stats) for item in containers if
                 item['status'] == 'running']
        tasks += [fetch_status(proxmox, node_name, vm, 'qemu', prev_net_stats) for vm in virtual_machines if
                  vm['status'] == 'running']
        results = await asyncio.gather(*tasks)

        # 处理状态信息，提取所需数据
        for status, net_speed in results:
            mem_usage_rate = (status['mem'] / status['maxmem']) if 'mem' in status else None
            net_speed_str = f"{net_speed / 1024 / 8:.0f}k" if net_speed < 1024 * 1024 * 8 else f"{net_speed / 1024 / 1024 / 8:.0f}m"
            running_items.append({'id': status['vmid'], 'name': status.get('name', ''), 'cpu_usage': status['cpu'],
                                  'mem_usage_rate': mem_usage_rate, 'net_speed': net_speed_str})

    # 按CPU使用率排序并输出前5个
    sorted_items = sorted(running_items, key=lambda x: x['cpu_usage'], reverse=True)[:5]
    for item in sorted_items:
        print(f"ID: {item['id']}, Name: {item['name']}, CPU Usage: {item['cpu_usage']:.0%}, "
              f"Memory Usage: {item['mem_usage_rate']:.0%}, Net Speed: {item['net_speed']}")

    level = 0
    # if any cpu is over 80%, show warn.png
    for item in sorted_items:
        if item['cpu_usage'] > 0.95:
            level = 2
            break
        if item['cpu_usage'] > 0.85:
            level = 1
            break
    if level == 2:
        image = load_image_file("error.png").convert('RGBA')
    elif level == 1:
        image = load_image_file("warn.png").convert('RGBA')
    else:
        image = load_image_file("init.png").convert('RGBA')

    # rotate the image 90 degrees
    # image = image.rotate(90, expand=True)

    start_x = 30
    item_y = 20
    per_start_y = width // 5

    #
    # text = "PVE Status"
    # text_position = (50, 50)
    # padding = 5
    # image = add_text_and_border(image, text, text_position, padding)

    image = add_border_only(image, (2, start_x - 2), (width - 2, start_x + 2 + len(sorted_items) * item_y))

    for i, item in enumerate(sorted_items):
        text = f"{item['name'][:10]}"
        text_position = (5, start_x + i * item_y)
        image = add_text_only(image, text, text_position)

        text = f"{item['cpu_usage']:.0%}"
        text_position = (5 + per_start_y * 2, start_x + i * item_y)
        if item['cpu_usage'] > 0.8:
            image = add_text_only(image, text, text_position, (255, 0, 0, 255))
        elif item['cpu_usage'] > 0.5:
            image = add_text_only(image, text, text_position, (255, 255, 0, 255))
        else:
            image = add_text_only(image, text, text_position)

        text = f"{item['mem_usage_rate']:.0%}"
        text_position = (5 + per_start_y * 3, start_x + i * item_y)
        if item['mem_usage_rate'] > 0.95:
            image = add_text_only(image, text, text_position, (255, 0, 0, 255))
        elif item['mem_usage_rate'] > 0.8:
            image = add_text_only(image, text, text_position, (255, 255, 0, 255))
        else:
            image = add_text_only(image, text, text_position)

        text = f"{item['net_speed']}"
        text_position = (5 + per_start_y * 4, start_x + i * item_y)
        image = add_text_only(image, text, text_position)

    # google generate_204
    try:
        # timeout 3s
        async with aiohttp.ClientSession() as session:
            async with session.get("http://clients3.google.com/generate_204", timeout=3) as response:
                if response.status == 204:
                    text = "Google"
                    x = width // 2 // 3
                    text_position = (x, height - 30)
                    image = add_text_only(image, text, text_position, (0, 255, 0, 255))
                else:
                    text = "Google"
                    x = width // 2 // 3
                    text_position = (x, height - 30)
                    image = add_text_only(image, text, text_position, (255, 0, 0, 255))
                    print("Google connection failed")
    except:
        text = "Google"
        x = width // 2 // 3
        text_position = (x, height - 30)
        image = add_text_only(image, text, text_position, (255, 0, 0, 255))
        print("Google connection failed")

    # baidu
    try:
        # timeout 3s
        async with aiohttp.ClientSession() as session:
            async with session.get("http://captive.apple.com/", timeout=3) as response:
                if response.status == 200:
                    text = "Apple"
                    x = width // 2 // 3 + width // 2
                    text_position = (x, height - 30)
                    image = add_text_only(image, text, text_position, (0, 255, 0, 255))
                else:
                    text = "Apple"
                    x = width // 2 // 3 + width // 2
                    text_position = (x, height - 30)
                    image = add_text_only(image, text, text_position, (255, 0, 0, 255))
                    print("Baidu connection failed")
    except:
        text = "Apple"
        x = width // 2 // 3 + width // 2
        text_position = (x, height - 30)
        image = add_text_only(image, text, text_position, (255, 0, 0, 255))
        print("Baidu connection failed")

    image_array = np.array(image)

    return image_array


async def load_image_pve_vertically(loading=False):
    height = 320
    width = 170
    with open("config.json", "r") as f:
        config = json.load(f)
    proxmox = ProxmoxAPI(config['proxmox_host'], user=config['proxmox_user'], password=config['proxmox_password'],
                         verify_ssl=False)

    nodes = proxmox.nodes.get()
    running_items = []

    for node in nodes:
        node_name = node['node']
        # 获取该节点上的所有CT和VM
        containers = proxmox.nodes(node_name).lxc.get()
        virtual_machines = proxmox.nodes(node_name).qemu.get()

        # 异步获取所有CT和VM的状态
        # 异步获取所有CT和VM的状态，并计算网速
        tasks = [fetch_status(proxmox, node_name, item, 'lxc', prev_net_stats) for item in containers if
                 item['status'] == 'running']
        tasks += [fetch_status(proxmox, node_name, vm, 'qemu', prev_net_stats) for vm in virtual_machines if
                  vm['status'] == 'running']
        results = await asyncio.gather(*tasks)

        # 处理状态信息，提取所需数据
        for status, net_speed in results:
            mem_usage_rate = (status['mem'] / status['maxmem']) if 'mem' in status else None
            net_speed_str = f"{net_speed / 1024 / 8:.0f}k" if net_speed < 1024 * 1024 * 8 else f"{net_speed / 1024 / 1024 / 8:.0f}m"
            running_items.append({'id': status['vmid'], 'name': status.get('name', ''), 'cpu_usage': status['cpu'],
                                  'mem_usage_rate': mem_usage_rate, 'net_speed': net_speed_str})

    # 按CPU使用率排序并输出前5个
    sorted_items = sorted(running_items, key=lambda x: x['cpu_usage'], reverse=True)[:5]
    for item in sorted_items:
        print(f"ID: {item['id']}, Name: {item['name']}, CPU Usage: {item['cpu_usage']:.0%}, "
              f"Memory Usage: {item['mem_usage_rate']:.0%}, Net Speed: {item['net_speed']}")

    level = 0
    # if any cpu is over 80%, show warn.png
    for item in sorted_items:
        if item['cpu_usage'] > 0.95:
            level = 2
            break
        if item['cpu_usage'] > 0.85:
            level = 1
            break
    if level == 2:
        image = load_image_file("error_shu.png").convert('RGBA')
    elif level == 1:
        image = load_image_file("warn_shu.png").convert('RGBA')
    else:
        image = load_image_file("init_shu.png").convert('RGBA')

    # rotate the image 90 degrees
    # image = image.rotate(90, expand=True)

    start_x = 30
    item_y = 50
    per_start_y = 25
    per_start_x = width // 3

    #
    # text = "PVE Status"
    # text_position = (50, 50)
    # padding = 5
    # image = add_text_and_border(image, text, text_position, padding)

    image = add_border_only(image, (2, start_x - 2), (width - 2, start_x + 2 + len(sorted_items) * item_y))

    for i, item in enumerate(sorted_items):
        text = f"{item['name'][:10]}"
        text_position = (5, start_x + i * item_y)
        image = add_text_only(image, text, text_position)

        text = f"{item['cpu_usage']:.0%}"
        text_position = (5, start_x + i * item_y + per_start_y)
        image = add_text_only(image, text, text_position)

        text = f"{item['mem_usage_rate']:.0%}"
        text_position = (5 + per_start_x, start_x + i * item_y + per_start_y)
        image = add_text_only(image, text, text_position)

        text = f"{item['net_speed']}"
        text_position = (5 + per_start_x * 2, start_x + i * item_y + per_start_y)
        image = add_text_only(image, text, text_position)

    # for i, item in enumerate(sorted_items):
    #     text = f"{item['name'][:10]}"
    #     text_position = (5, start_x + i * item_y)
    #     image = add_text_only(image, text, text_position)
    #
    #     text = f"{item['cpu_usage']:.0%}"
    #     text_position = (5 + per_start_y * 2, start_x + i * item_y)
    #     if item['cpu_usage'] > 0.8:
    #         image = add_text_only(image, text, text_position, (255, 0, 0, 255))
    #     elif item['cpu_usage'] > 0.5:
    #         image = add_text_only(image, text, text_position, (255, 255, 0, 255))
    #     else:
    #         image = add_text_only(image, text, text_position)
    #
    #     text = f"{item['mem_usage_rate']:.0%}"
    #     text_position = (5 + per_start_y * 3, start_x + i * item_y)
    #     if item['mem_usage_rate'] > 0.95:
    #         image = add_text_only(image, text, text_position, (255, 0, 0, 255))
    #     elif item['mem_usage_rate'] > 0.8:
    #         image = add_text_only(image, text, text_position, (255, 255, 0, 255))
    #     else:
    #         image = add_text_only(image, text, text_position)
    #
    #     text = f"{item['net_speed']}"
    #     text_position = (5 + per_start_y * 4, start_x + i * item_y)
    #     image = add_text_only(image, text, text_position)

    # google generate_204
    try:
        # timeout 3s
        async with aiohttp.ClientSession() as session:
            async with session.get("http://clients3.google.com/generate_204", timeout=3) as response:
                if response.status == 204:
                    text = "Google"
                    x = width // 2 // 4
                    text_position = (x, height - 25)
                    image = add_text_only(image, text, text_position, (0, 255, 0, 255))
                else:
                    text = "Google"
                    x = width // 2 // 4
                    text_position = (x, height - 25)
                    image = add_text_only(image, text, text_position, (255, 0, 0, 255))
                    print("Google connection failed")
    except:
        text = "Google"
        x = width // 2 // 4
        text_position = (x, height - 25)
        image = add_text_only(image, text, text_position, (255, 0, 0, 255))
        print("Google connection failed")

    # baidu
    try:
        # timeout 3s
        async with aiohttp.ClientSession() as session:
            async with session.get("http://captive.apple.com/", timeout=3) as response:
                if response.status == 200:
                    text = "Apple"
                    x = width // 2 // 3 + width // 2.5
                    text_position = (x, height - 25)
                    image = add_text_only(image, text, text_position, (0, 255, 0, 255))
                else:
                    text = "Apple"
                    x = width // 2 // 3 + width // 2.5
                    text_position = (x, height - 25)
                    image = add_text_only(image, text, text_position, (255, 0, 0, 255))
                    print("Baidu connection failed")
    except:
        text = "Apple"
        x = width // 2 // 3 + width // 2.5
        text_position = (x, height - 25)
        image = add_text_only(image, text, text_position, (255, 0, 0, 255))
        print("Baidu connection failed")

    current_machine_cpu = psutil.cpu_percent() / 100
    current_machine_memory = psutil.virtual_memory().percent / 100
    print(f"Current machine CPU: {current_machine_cpu:.0%}, Memory: {current_machine_memory:.0%}")

    cpu_current_machine = f"CPU:{current_machine_cpu:.0%}"
    memory_current_machine = f"MEM:{current_machine_memory:.0%}"
    text_position = (5, height - 50)
    if current_machine_cpu > 0.85:
        image = add_text_only(image, cpu_current_machine, text_position, (255, 0, 0, 255))
    if current_machine_cpu > 0.7:
        image = add_text_only(image, cpu_current_machine, text_position, (255, 255, 0, 255))
    else:
        image = add_text_only(image, cpu_current_machine, text_position)

    text_position = (width // 2, height - 50)
    if current_machine_memory > 0.92:
        image = add_text_only(image, memory_current_machine, text_position, (255, 0, 0, 255))
    if current_machine_memory > 0.7:
        image = add_text_only(image, memory_current_machine, text_position, (255, 255, 0, 255))
    else:
        image = add_text_only(image, memory_current_machine, text_position, (255, 255, 255, 180))

    # rotate the image 90 degrees 逆时针
    image = image.rotate(90, expand=True)

    image_array = np.array(image)

    return image_array


def load_image(loading=False):
    if loading:
        # # if not found the image, show error
        # if not os.path.exists("images/init.png"):
        #     print("Error: init.png not found.")
        #     sys.exit(1)
        image = load_image_file("init.png").convert('RGBA')
        text = "Still under development"
        text2 = "Demo version"
        text_position = (50, 50)
        text_position2 = (70, 110)
        padding = 5
        image = add_text_and_border(image, text, text_position, padding)
        image = add_text_and_border(image, text2, text_position2, padding)
    else:
        cpu = get_cpu_usage()
        memory = get_memory_usage()
        disk = get_disk_usage()

        if memory > 90 or disk > 90:
            image_filename = "error.png"
        else:
            if cpu > 80 or memory > 80 or disk > 80:
                image_filename = "warn.png"
            else:
                image_filename = "init.png"

        image = load_image_file(image_filename).convert('RGBA')

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
        cpu_icon = load_image_file('cpuicon.png').resize((30, 30))
        memory_icon = load_image_file('memoryicon.png').resize((30, 30))
        disk_icon = load_image_file('diskicon.png').resize((30, 30))
        network_icon = load_image_file('networkicon.png').resize((30, 30))

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
    target_device_info = next((device for device in devices if device['vendor_id'] == vendor_id and device['product_id'] == product_id and device['interface_number'] == 1), None)

    if target_device_info:
        try:
            path = target_device_info['path']

            device = hid.device()
            device.open_path(path)
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
        print(
            "Error opening device. Run into debug mode, image will be shown.")  # # list all hid usb devices  # print(hid.enumerate())  # await asyncio.sleep(10)  # sys.exit(1)
    else:
        global device_opened
        device_opened = True
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
            device.write(data_with_report_id)  # print("Data sent successfully.")
        except IOError as e:
            # print(f"Error sending data: {e}")
            pass


def hex_string_to_byte_array_normal(hex_string):
    # Remove spaces and convert to bytes
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    return byte_data


async def periodic_refresh_screen():
    while True:
        await asyncio.sleep(8)
        await sends_testing_background()


async def periodic_send_data():
    global is_sending_background
    while True:
        if not is_sending_background and global_device is not None:
            pre_end_data = "55 a1 f2 "
            current_hour = int(time.strftime("%H"))
            current_minute = int(time.strftime("%M"))
            current_second = int(time.strftime("%S"))
            pre_end_data += format(current_hour, '02x') + " " + format(current_minute, '02x') + " " + format(
                current_second, '02x')
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
    try:
        # print("Sending background data...")
        # 你的sends_testing_background逻辑
        # 请在这里添加相应的异步发送数据代码

        # org_image_array = load_image(loading)
        if image_type == "shu":
            org_image_array = await load_image_pve_vertically(loading)
        else:
            org_image_array = await load_image_pve(loading)

        is_sending_background = True

        pre_end_data = "55 a1 f2 00 00 00"
        data_to_send = hex_string_to_byte_array_with_00(pre_end_data)
        send_data(global_device, data_to_send)

        if device_opened:
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
        else:
            # plot the image if the device is not opened
            Image.fromarray(org_image_array).show()

            # cv2.destroyAllWindows()
            # org_image_array = cv2.cvtColor(org_image_array, cv2.COLOR_RGB2BGR)
            # cv2.imshow("Image", org_image_array)
            # cv2.waitKey(0)  # Add this line


    except Exception as e:
        print(f"Error sending background data: {e}")
    finally:
        is_sending_background = False  # print("Background data sent successfully.")


# 获取网卡的每秒流量
def get_network_traffic():
    net_io = psutil.net_io_counters(pernic=True)
    traffic_details = {}
    for interface, io_counters in net_io.items():
        traffic_details[interface] = {'sent': io_counters.bytes_sent, 'recv': io_counters.bytes_recv}
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

    # reads the config.json file and finds the "image_type"
    with open("config.json", "r") as f:
        config = json.load(f)
        global image_type
        image_type = config['image_type']

    if global_device:
        send_task = asyncio.create_task(periodic_send_data())
    refresh_task = asyncio.create_task(periodic_refresh_screen())
    await sends_testing_background(loading=True)
    # send_task.cancel()  # 取消周期性发送任务
    # read input line
    await asyncio.sleep(99999)


if __name__ == "__main__":
    asyncio.run(main())
