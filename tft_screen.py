import time

import hid

is_loading_background = False


def enumerate_devices():
    devices = hid.enumerate()
    if not devices:
        print("No HID devices found.")
        return []
    print("Available HID devices:")
    for index, device in enumerate(devices):
        print(f"{index + 1}: {device['product_string']} - Vendor ID: {device['vendor_id']}, Product ID: {device['product_id']}")
    return devices


def open_first_device(devices):
    if devices:
        first_device_info = devices[0]
        try:
            device = hid.device()
            device.open(first_device_info['vendor_id'], first_device_info['product_id'])
            print(f"Opened device {first_device_info['vendor_id']}:{first_device_info['product_id']} - {first_device_info['product_string']}")
            return device
        except IOError as e:
            print(f"Could not open the device {first_device_info['vendor_id']}:{first_device_info['product_id']}. Error: {e}")
            return None
    else:
        print("No HID devices available to open.")
        return None


def hex_string_to_byte_array(hex_string, total_length=4104):
    # Remove spaces and convert to bytes
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    # Calculate the number of bytes to add to make the data reach the desired length
    bytes_to_add = total_length - len(byte_data)
    if bytes_to_add > 0:
        # Append the necessary number of 0x00 bytes
        byte_data += bytes([0xff]) * bytes_to_add
    return byte_data


def hex_string_to_byte_array_with_00(hex_string, total_length=4104):
    # Remove spaces and convert to bytes
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    # Calculate the number of bytes to add to make the data reach the desired length
    bytes_to_add = total_length - len(byte_data)
    if bytes_to_add > 0:
        # Append the necessary number of 0x00 bytes
        byte_data += bytes([0x00]) * bytes_to_add
    return byte_data


def hex_string_to_byte_array_normal(hex_string):
    # Remove spaces and convert to bytes
    byte_data = bytes.fromhex(hex_string.replace(" ", ""))
    return byte_data


def send_data(device, data):
    if device:
        try:
            # Add report ID at the beginning if needed. Here we assume report ID 0.
            data_with_report_id = [0] + list(data)
            device.write(data_with_report_id)
            print("Data sent successfully.")
        except IOError as e:
            print(f"Error sending data: {e}")


def main():
    devices = enumerate_devices()
    if devices:
        device = open_first_device(devices)
        if device:

            # Example data to send as a hex string #width 168
            # 55 a2 X 00 Y 00 chang kuan
            # 55 a2 X 00 Y 00 50
            # 55 A1 F1 02
            # 55 A1 F2 15 17 11 xintiao ? clean?
            # 55 A3 F1 01 to 55 A3 F1 1A beijing
            # 55 A3 F0 01 00 00 00 10                           Uｐ......
            # 55 A3 F1 11 00 00 00 10                           Uｑ......

            #  55 A3 F1 08 00 70 shizhong xiao 1 08 weizhi 00 10
            # 55 A1 F2 15 17 0A                                  U◎....

            # send_bin_file_content(device)

            sends_testing_background(device)

            # sends the data in dataset folder which from 13.bin to 38.bin
            # package_bin(device)
            # package_bin2(device)

            time.sleep(2)
            device.close()
        else:
            print("Failed to open device.")
    else:
        print("No devices to open.")


def package_bin(device):
    for i in range(12, 40):
        with open("dataset/" + str(i) + ".bin", "rb") as f:
            data = f.read(4104)
            if data[0] != 0x55:
                print("Error: Data does not start with 0x55")
                break
            send_data(device, data)


def package_bin2(device):
    for i in range(45, 77):
        with open("dataset/" + str(i) + ".bin", "rb") as f:
            data = f.read(4104)
            if data[0] != 0x55:
                print("Error: Data does not start with 0x55")
                break
            send_data(device, data)


def sends_testing_background(device):
    pre_end_data = "55 a1 f2 0f 19 38"
    data_to_send = hex_string_to_byte_array_with_00(pre_end_data)
    pre_end_data = "55 a1 f2 0f 19 39"
    data_to_send = hex_string_to_byte_array_with_00(pre_end_data)
    send_data(device, data_to_send)

    # reads the image.bin
    image_array = open("image.bin", "rb").read()

    for x in range(0, 26):
        x_str = format(x + 1, '02x')
        second_str = format(x % 16, 'x')
        pre_str = '0' if x == 0 else '1'
        # pre_str = str(int((x+1)/16))
        hex_data = "55 A3 F" + pre_str + " " + x_str + " 00 " + second_str + "0 00 10"
        print(hex_data)
        # adds top 4096 bytes of image_array after hex_data, and removes the 4096 bytes from image_array
        if len(image_array) >= 4096:
            hex_data = hex_data + " " + image_array[:4096].hex()
            image_array = image_array[4096:]
        hex_string_to_byte_array(hex_data)
        data_to_send = hex_string_to_byte_array(hex_data)
        send_data(device, data_to_send)
    pre_end_data = "55 A3 F2 1B 00 A0 00 09"
    # # adds 1664 0xFF after pre_end_data
    # pre_end_data = pre_end_data + " FF" * 1664
    # # add 320 0x42 0x08 after pre_end_data
    # pre_end_data = pre_end_data + " 42 08" * 320
    if len(image_array) > 4096:
        print("ERROR! image_array too large for end")
        exit(1)
    pre_end_data = pre_end_data + " " + image_array.hex()
    data_to_send = hex_string_to_byte_array_with_00(pre_end_data)
    send_data(device, data_to_send)
    end_data = "55 A1 F1 01"
    data_to_send = hex_string_to_byte_array(end_data)
    send_data(device, data_to_send)
    # send_data(device, data_to_send)
    # end_data = "55 a1 f3 0f 1a 01 00"
    # send_data(device, data_to_send)
    end_data = "55 a1 f2 0f 1a 01 00"
    send_data(device, data_to_send)


def send_bin_file_content(device):
    # reads newfilfe.bin and sends the data to the device, each 4104 bytes at a time
    # make sure the each begin is 0x55, otherwise show errors
    with open("newfilfe.bin", "rb") as f:
        while True:
            data = f.read(4104)
            if not data:
                break
            if data[0] != 0x55:
                print("Error: Data does not start with 0x55")
                break
            send_data(device, data)


if __name__ == "__main__":
    main()
