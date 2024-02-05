#!/usr/bin/env python
# -*-coding:utf-8 -*-
# @Author  : Nov30th, HOHO``


import base64
import os
import uuid

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15

# 确保密钥和pre_sign目录存在
os.makedirs("keys", exist_ok=True)
os.makedirs("pre_sign", exist_ok=True)


def generate_keys():
    if not os.path.isdir("keys"):
        os.makedirs("keys")
    if not os.path.isdir("private_keys"):
        os.makedirs("private_keys")
    key = RSA.generate(2048)
    private_key = key.export_key()
    public_key = key.publickey().export_key()

    with open("private_keys/private.pem", "wb") as priv_file:
        priv_file.write(private_key)

    with open("keys/public.pem", "wb") as pub_file:
        pub_file.write(public_key)


# 检查是否需要生成密钥
if not (os.path.exists("private_keys/private.pem") and os.path.exists("keys/public.pem")):
    generate_keys()


def sign_image(image_path):
    # 读取私钥
    with open("private_keys/private.pem", "rb") as priv_file:
        private_key = RSA.import_key(priv_file.read())

    # 读取图片数据
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()

    # 生成UUID
    image_uuid = str(uuid.uuid4())

    # 生成摘要
    hash = SHA256.new(image_data)

    # 签名
    signer = pkcs1_15.new(private_key)
    signature = signer.sign(hash)
    signature_base64 = base64.b64encode(signature).decode('utf-8')

    return image_uuid, signature_base64


# 对pre_sign文件夹下的所有图片进行签名
sign_results = []
for image_name in os.listdir("images"):
    if image_name.lower().endswith(('.png', '.jpg', '.jpeg')):
        image_path = os.path.join("images", image_name)
        image_uuid, signature_base64 = sign_image(image_path)
        sign_results.append(f"{image_uuid}|{image_name}|{signature_base64}\n")

# 保存签名结果
with open("images/load_data.txt", "w") as load_data_file:
    load_data_file.writelines(sign_results)

print("所有图片已签名，结果保存在load_data.txt文件中。")
