#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

import asyncio
# reads config.json for proxmox
import json
import time

from proxmoxer import ProxmoxAPI


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


async def main():
    with open("config.json", "r") as f:
        config = json.load(f)
    proxmox = ProxmoxAPI(config['proxmox_host'], user=config['proxmox_user'], password=config['proxmox_password'],
                         verify_ssl=False)
    prev_net_stats = {}  # 保存前一次的网络流量状态

    while True:  # 持续监控
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
                net_speed_str = f"{net_speed / 1024:.0f}k" if net_speed < 1024 * 1024 else f"{net_speed / 1024 / 1024:.0f}m"
                running_items.append({
                    'id': status['vmid'],
                    'name': status.get('name', ''),
                    'cpu_usage': status['cpu'],
                    'mem_usage_rate': mem_usage_rate,
                    'net_speed': net_speed_str
                })

        # 按CPU使用率排序并输出前5个
        sorted_items = sorted(running_items, key=lambda x: x['cpu_usage'], reverse=True)[:5]
        for item in sorted_items:
            print(f"ID: {item['id']}, Name: {item['name']}, CPU Usage: {item['cpu_usage']:.0%}, "
                  f"Memory Usage: {item['mem_usage_rate']:.0%}, Net Speed: {item['net_speed']}")

        await asyncio.sleep(5)  # 每5秒刷新一次


if __name__ == "__main__":
    asyncio.run(main())
