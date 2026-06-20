# Jarvis OTA Lite
# Minimal firmware for ESP32-C3 — just Wi-Fi, heartbeat, and OTA server.
# No audio hardware required. Use this to test OTA flashing on any board.

from machine import Pin, reset
import network
import time
import urequests
import socket
import os

OTA_PORT = 8080
LED_PIN  = 2

# --- Configuration ---
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
BACKEND   = "http://PI_API_IP:8000"

led = Pin(LED_PIN, Pin.OUT)

def blink(n, on_ms=80, off_ms=80):
    for _ in range(n):
        led.value(1); time.sleep_ms(on_ms)
        led.value(0); time.sleep_ms(off_ms)

def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start > 20:
                raise RuntimeError("Wi-Fi timeout")
            time.sleep(0.2)
    print("Wi-Fi connected:", wlan.ifconfig())
    return wlan

def send_heartbeat(device_id):
    try:
        body = '{"device_id":"' + device_id + '","name":"ESP32-C3-OTA"}'
        headers = {"Content-Type": "application/json"}
        r = urequests.post(BACKEND + "/devices/heartbeat", data=body, headers=headers)
        r.close()
        print("Heartbeat sent")
        blink(2, 50, 50)
    except Exception as e:
        print("Heartbeat failed:", e)

def ota_server():
    addr = socket.getaddrinfo("0.0.0.0", OTA_PORT)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    s.settimeout(1.0)
    print("OTA server on port", OTA_PORT)
    return s

def handle_ota(conn):
    try:
        raw = b""
        content_length = None
        while True:
            chunk = conn.recv(256)
            if not chunk:
                conn.close(); return
            raw += chunk
            blank = raw.find(b"\r\n\r\n")
            if blank != -1:
                head = raw[:blank].decode()
                for line in head.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":")[1].strip())
                break
            if len(raw) > 4096:
                conn.send(b"HTTP/1.0 413 Header Too Large\r\n\r\n")
                conn.close(); return

        if "POST /ota" not in head:
            conn.send(b"HTTP/1.0 405 Method Not Allowed\r\n\r\n")
            conn.close(); return

        if content_length is None or content_length <= 0 or content_length > 524288:
            conn.send(b"HTTP/1.0 400 Bad Request\r\n\r\n")
            conn.close(); return

        body_start = blank + 4
        body = raw[body_start:]
        while len(body) < content_length:
            chunk = conn.recv(512)
            if not chunk: break
            body += chunk

        tmp = "ota_tmp.py"
        with open(tmp, "w") as f:
            f.write(body.decode() if isinstance(body, bytes) else body)
        if "main.py" in os.listdir():
            os.remove("main.py")
        os.rename(tmp, "main.py")

        conn.send(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
        conn.send(b'{"status":"ok","message":"Firmware updated. Rebooting..."}')
        conn.close()
        print("OTA: firmware written, rebooting...")
        time.sleep(1)
        reset()
    except Exception as e:
        try:
            conn.send(b"HTTP/1.0 500 Internal Server Error\r\n\r\n")
            conn.send(str(e).encode())
        except:
            pass
        conn.close()
        print("OTA error:", e)

wlan = wifi_connect()
mac = wlan.config("mac")
device_id = "".join("{:02x}".format(b) for b in mac)
send_heartbeat(device_id)
ota_sock = ota_server()
led.value(1)  # solid ON = ready
print("OTA Lite ready. Device ID:", device_id)

while True:
    try:
        conn, addr = ota_sock.accept()
        print("OTA connection from", addr)
        handle_ota(conn)
    except OSError:
        pass
    time.sleep_ms(100)
