#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

from proxmoxer import ProxmoxAPI

proxmox = ProxmoxAPI('127.0.0.1', user='root@pam', password='123456', verify_ssl=False)

# 获取所有节点
nodes = proxmox.nodes.get()

# 遍历节点获取CT和VM信息
for node in nodes:
    node_name = node['node']
    # 获取该节点上的所有CT
    containers = proxmox.nodes(node_name).lxc.get()
    for ct in containers:
        print(f"CT ID: {ct['vmid']}, Name: {ct['name']}")

    # 获取该节点上的所有VM
    virtual_machines = proxmox.nodes(node_name).qemu.get()
    for vm in virtual_machines:
        print(f"VM ID: {vm['vmid']}, Name: {vm['name']}")

    # 以获取CT信息为例
    for ct in containers:
        status = proxmox.nodes(node_name).lxc(ct['vmid']).status.current.get()
        print(f"CT {ct['vmid']} Status: {status}")

    # 同理，获取VM状态信息
    for vm in virtual_machines:
        status = proxmox.nodes(node_name).qemu(vm['vmid']).status.current.get()
        print(f"VM {vm['vmid']} Status: {status}")
