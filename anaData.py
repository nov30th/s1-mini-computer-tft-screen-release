#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``
import os

# os.mkdir("dataset")

with open("newfilfe.bin", "rb") as f:
    index = 1
    while True:
        data = f.read(4104)
        if not data:
            break
        if data[0] != 0x55:
            print("Error: Data does not start with 0x55")
            break
        # put data into data set
        with open("dataset/" + str(index) + ".bin", "wb") as f2:
            f2.write(data)
            index += 1
