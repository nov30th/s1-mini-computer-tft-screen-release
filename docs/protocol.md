# AceMagic S1 front panel protocol notes

Everything here was measured on a real S1 (Intel N100, Proxmox VE 8.4).

## TFT screen

| | |
|---|---|
| USB ID | `04d9:fd01` (Holtek) |
| Interface | **1**, one interrupt OUT endpoint `0x02` (64-byte packets) |
| Resolution | 320 x 170, landscape is the native frame |
| Pixel format | RGB565, **big-endian** (byte-swapped) |
| Packet size | 4104 bytes = 8-byte header + 4096 data, zero padded |

Interface 1 has no IN endpoint, so the kernel's `usbhid` never binds it and there is
no `/dev/hidraw` node for it. Talk to it through usbfs/libusb: claim interface 1 and
write to endpoint `0x02`.

### Full frame

320 x 170 x 2 = 108800 bytes, sent as 26 chunks of 4096 bytes plus one of 2304:

```
55 A3 <kind> <seq> <offset u16 LE> <length u16 LE> <data...>

kind   F0 = first chunk, F1 = middle chunks, F2 = last chunk
seq    1 .. 27 (0x1B)
offset (seq-1) * 4096, truncated to 16 bits (wraps at seq 17)
length 0x1000, last chunk 0x0900

e.g. 55 A3 F0 01 00 00 00 10 ...
     55 A3 F1 02 00 10 00 10 ...
     55 A3 F2 1B 00 A0 00 09 ...
```

### Timing (important)

* Sending one frame takes about **2.1 - 2.4 s** (the panel consumes ~80 ms per packet).
* After the last chunk the panel is **busy for about 6.5 s** and NAKs every write.
  A write in that window simply waits; with a short timeout it fails.
* So one full frame costs ~9 s end to end. `s1screen` refreshes every 10 s by default
  and uses a 10 s write timeout, so it never has to retry.

### Other commands (not used by s1screen)

s1screen does not need these.

| Bytes | Meaning |
|---|---|
| `55 A1 F1 01` / `55 A1 F1 02` | orientation of the firmware's own pages (landscape / portrait) |
| `55 A1 F2 HH MM SS` | set the firmware clock / keep-alive |
| `55 A2 xL xH yL yH W H <pixels>` | partial update of a W x H rectangle (W*H <= 2048) |

Commands sent during the busy window above time out, which is why s1screen sends
no heartbeat or other commands - full frames only.

Raw packets captured during the 2024 reverse engineering are in `tools/captures/`
(179 packets, all `55 ..` screen packets of 4104 bytes).

## LED strip

| | |
|---|---|
| USB ID | `1a86:7523` (CH340 USB serial) on an **internal, fixed** USB port |
| Serial | 10000 baud, 8N1, bytes written one by one with ~5 ms gaps |

```
FA <mode> <brightness> <speed> <checksum>

mode       01 rainbow, 02 breathing, 03 colour cycle, 04 off, 05 auto
brightness 1..5 on the wire, 1 = brightest (s1screen config uses 1..5 with 5 = brightest)
speed      1..5 on the wire, 1 = fastest
checksum   (FA + mode + brightness + speed) & 0xFF

e.g. off:          FA 04 05 05 08
     breathing 3/3: FA 02 03 03 02
```

The S1 can also have external CH340 adapters plugged in (Zigbee sticks, 4G modems
show up as `ttyUSB*` too). `s1screen` only auto-selects a CH340 whose USB port is
reported as `fixed` by the kernel (`/sys/bus/usb/devices/<port>/removable`).
If that CH340 is passed through to a VM, the host cannot drive the LED strip.
