#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``
import base64
import os

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15


def verify_image(image_path, signature_base64):
    # 读取公钥
    with open("keys/public.pem", "rb") as pub_file:
        public_key = RSA.import_key(pub_file.read())

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


# 示例用法（请根据实际情况调整）
# 假设load_data.txt中的格式为uuid|image_name|signature_base64
with open("images/load_data.txt", "r") as load_data_file:
    for line in load_data_file:
        image_uuid, image_name, signature_base64 = line.strip().split("|")
        image_path = os.path.join("images", image_name)
        result = verify_image(image_path, signature_base64)
        print(f"图片 {image_name} 验证结果：{'匹配' if result else '不匹配'}")
