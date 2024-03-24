#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``
import asyncio

import aiohttp
from aiohttp_socks import ProxyConnector
proxy_host = ""
proxy_port = "1081"
proxy_user = ""
proxy_password = ""
async def main():
    if proxy_host and proxy_port:
        connector = ProxyConnector.from_url(f'socks5://{proxy_user}:{proxy_password}@{proxy_host}:{proxy_port}')
    else:
        connector = None
    # timeout 3s

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get("https://www.google.com/", timeout=3) as response:
            if response.status == 200:
                print("Apple connection success")
            else:
                print("Apple connection failed")

asyncio.run(main())