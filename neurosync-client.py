import network
import time
import uasyncio as asyncio
from machine import Pin, PWM

SSID = "neurolamp"
PASSWORD = "meowmeowlol"

ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid=SSID, password=PASSWORD)

while not ap.active():
    time.sleep(0.1)

print("lamp active")

red = PWM(Pin(15), freq=1000)
green = PWM(Pin(12), freq=1000)
blue = PWM(Pin(13), freq=1000)

def set_color(r, g, b):
    red.duty_u16(max(0, min(255, r)) * 257)
    green.duty_u16(max(0, min(255, g)) * 257)
    blue.duty_u16(max(0, min(255, b)) * 257)

async def handle_client(reader, writer):
    print("server connected")
    try:
        while True:
            data = await reader.readline()
            if not data:
                break
            try:
                r, g, b = map(int, data.decode().strip().split(","))
                set_color(r, g, b)
                print(f"[{r}, {g}, {b}]", end="\r")
            except Exception:
                await writer.awrite(b"error")
    finally:
        await writer.aclose()
        print("disconnected from server")

async def main():
    server = await asyncio.start_server(handle_client, "0.0.0.0", 8765)
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
