#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``

binary_file_name = "raw20240203"
bytes = open(binary_file_name, "rb").read()

# reads the every 128 bytes, if next byte is 0x55, then append next 4104 bytes which including 0x55 to a new file
# if next byte is not 0x55, then read next 128 bytes and repeat the process

i = 0
with open("newfilfe.bin", "wb") as f:
    while i < len(bytes):
        current_value = bytes[i]
        if bytes[i] == 0x55:
            f.write(bytes[i:i + 4104])
            print("found 0x55 at", i)
            i += 4104
        else:
            if bytes[i] == 0:
                print("ERROR found 0x00 at", i)
                exit(-1)
            # bytes[i] value is current block size, skip it
            if bytes[i] == 128:
                i += 128
            else:
                i += bytes[i] + 2
