# DIVA ESP32 Client
# MicroPython firmware for ESP32-C3
# Flow: button press -> record I2S mic -> POST /voice to Pi API -> play WAV reply

from machine import Pin, I2S, reset
import network
import time
import urequests
import ujson
import socket
import os

OTA_PORT = 8080

# ---------------------------------------------------------------------------
# Configuration - update these before flashing
# ---------------------------------------------------------------------------

WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
BACKEND   = "http://PI_API_IP:8000"  # Raspberry Pi running DIVA backend

# ---------------------------------------------------------------------------
# Pin map (ESP32-C3 breadboard test)
# ---------------------------------------------------------------------------

MIC_SCK  = 4   # INMP441 SCK
MIC_WS   = 5   # INMP441 WS
MIC_SD   = 6   # INMP441 SD

SPK_BCLK = 7   # MAX98357A BCLK
SPK_LRC  = 8   # MAX98357A LRC
SPK_DIN  = 10  # MAX98357A DIN

BTN_PIN  = 3   # Push-to-talk button (active LOW)
LED_PIN  = 2   # Status LED

# ---------------------------------------------------------------------------
# Audio config
# ---------------------------------------------------------------------------

RATE           = 16000
BITS           = 16
BUF_SIZE       = 1024
RECORD_SECONDS = 5

# ---------------------------------------------------------------------------
# Hardware init
# ---------------------------------------------------------------------------

led = Pin(LED_PIN, Pin.OUT)
btn = Pin(BTN_PIN, Pin.IN, Pin.PULL_UP)

mic = I2S(
    0,
    sck=Pin(MIC_SCK),
    ws=Pin(MIC_WS),
    sd=Pin(MIC_SD),
    mode=I2S.RX,
    bits=BITS,
    format=I2S.MONO,
    rate=RATE,
    ibuf=BUF_SIZE * 8,
)

spk = I2S(
    1,
    sck=Pin(SPK_BCLK),
    ws=Pin(SPK_LRC),
    sd=Pin(SPK_DIN),
    mode=I2S.TX,
    bits=16,
    format=I2S.MONO,
    rate=RATE,
    ibuf=BUF_SIZE * 8,
)


# ---------------------------------------------------------------------------
# LED helpers
#
#   led_recording()   solid ON  – mic is active, capturing audio
#   led_processing()  fast blink – waiting on network / backend pipeline
#   led_speaking()    solid ON  – speaker is playing back the reply
#   led_error()       3× rapid flashes – something went wrong
#   led_idle()        OFF
# ---------------------------------------------------------------------------

def led_idle():
    led.value(0)


def led_recording():
    led.value(1)


def led_speaking():
    led.value(1)


def led_processing():
    """Fast blink to indicate the backend is working.
    Called in a tight loop while blocking on urequests.post().
    Because MicroPython is single-threaded this is a one-shot blink
    before the blocking call; repeated blinking requires async refactor."""
    for _ in range(6):
        led.value(1)
        time.sleep_ms(100)
        led.value(0)
        time.sleep_ms(100)


def led_error():
    """Three rapid flashes to indicate an error state."""
    for _ in range(3):
        led.value(1)
        time.sleep_ms(80)
        led.value(0)
        time.sleep_ms(80)
    led.value(0)


# ---------------------------------------------------------------------------
# Wi-Fi
# ---------------------------------------------------------------------------

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


def ota_server():
    """Start a simple OTA HTTP server on port OTA_PORT.
    Accepts POST /ota with firmware source code in the body.
    Writes to main.py and resets the device."""
    addr = socket.getaddrinfo("0.0.0.0", OTA_PORT)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    s.settimeout(0.5)
    print("OTA server on port", OTA_PORT)
    return s


def handle_ota(conn):
    """Read an OTA request, write firmware, and reset.
    Uses Content-Length header to read exact payload size.
    Supports both text (MicroPython source) and binary firmware."""
    try:
        raw = b""
        content_length = None
        # Read until we have the full headers
        while True:
            chunk = conn.recv(256)
            if not chunk:
                conn.close()
                return
            raw += chunk
            blank = raw.find(b"\r\n\r\n")
            if blank != -1:
                # Parse Content-Length from headers
                head = raw[:blank].decode()
                for line in head.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":")[1].strip())
                break
            if len(raw) > 4096:  # header too large
                conn.send(b"HTTP/1.0 413 Header Too Large\r\n\r\n")
                conn.close()
                return

        if "POST /ota" not in head:
            conn.send(b"HTTP/1.0 405 Method Not Allowed\r\n\r\n")
            conn.close()
            return

        if content_length is None or content_length <= 0:
            conn.send(b"HTTP/1.0 400 Bad Request\r\n\r\n")
            conn.close()
            return

        if content_length > 524288:  # 512KB max
            conn.send(b"HTTP/1.0 413 Payload Too Large\r\n\r\n")
            conn.close()
            return

        # Read the remaining body
        body_start = blank + 4
        body = raw[body_start:]
        while len(body) < content_length:
            chunk = conn.recv(512)
            if not chunk:
                break
            body += chunk

        # Determine if this is source code or binary firmware
        # If it looks like Python source, write as .py; else write as binary
        is_source = b"def " in body or b"import " in body or body.startswith(b"#")

        if is_source:
            tmp = "ota_tmp.py"
            with open(tmp, "w") as f:
                f.write(body.decode() if isinstance(body, bytes) else body)
            if "main.py" in os.listdir():
                os.remove("main.py")
            os.rename(tmp, "main.py")
        else:
            tmp = "ota_tmp.bin"
            with open(tmp, "wb") as f:
                f.write(body)
            # For raw binary, note it was saved but can't replace running firmware
            # (full OTA firmware update via esptool should be done separately)
            pass

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


def send_heartbeat(device_id):
    """Register this device with the backend."""
    try:
        body = '{"device_id":"' + device_id + '","name":"ESP32-C3"}'
        headers = {"Content-Type": "application/json"}
        r = urequests.post(BACKEND + "/devices/heartbeat", data=body, headers=headers)
        r.close()
        print("Heartbeat sent")
    except Exception as e:
        print("Heartbeat failed:", e)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def record_pcm(seconds=RECORD_SECONDS):
    """Record raw 16-bit 16kHz mono PCM from INMP441."""
    print("Recording...")
    led_recording()
    total  = seconds * RATE * 2  # bytes
    buf    = bytearray(BUF_SIZE)
    chunks = []
    got    = 0
    while got < total:
        n = mic.readinto(buf)
        if n:
            chunks.append(bytes(buf[:n]))
            got += n
    led_idle()
    print("Recorded", got, "bytes")
    return b"".join(chunks)


def play_wav(wav_bytes):
    """
    Play WAV audio returned from the backend.
    Strips the 44-byte WAV header and writes raw PCM to the I2S speaker.
    """
    print("Playing reply...")
    led_speaking()
    pcm = wav_bytes[44:]  # skip WAV header
    pos = 0
    chunk = BUF_SIZE
    while pos < len(pcm):
        end = min(pos + chunk, len(pcm))
        spk.write(pcm[pos:end])
        pos = end
    led_idle()
    print("Playback done")


# ---------------------------------------------------------------------------
# Backend call
# ---------------------------------------------------------------------------

def voice_round_trip(pcm_bytes):
    """
    POST raw PCM to /voice on the Pi API.
    Returns WAV bytes of the TTS reply, or None on error.
    """
    print("Sending to backend...")
    led_processing()
    boundary = b"----DIVABoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="audio.raw"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + pcm_bytes
        + b"\r\n--" + boundary + b"--\r\n"
    )
    headers = {
        "Content-Type": "multipart/form-data; boundary=----DIVABoundary",
        "Content-Length": str(len(body)),
    }
    r = urequests.post(BACKEND + "/voice", data=body, headers=headers)
    if r.status_code != 200:
        print("Backend error:", r.status_code, r.text)
        r.close()
        led_error()
        return None
    wav = r.content
    r.close()
    led_idle()
    print("Received", len(wav), "bytes from backend")
    return wav


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

wlan = wifi_connect()
mac = wlan.config("mac")
device_id = "".join("{:02x}".format(b) for b in mac)
send_heartbeat(device_id)
ota_sock = ota_server()
print("DIVA ready. Hold button to speak.")

while True:
    # Check for OTA update requests
    try:
        conn, addr = ota_sock.accept()
        print("OTA connection from", addr)
        handle_ota(conn)
    except OSError:
        pass  # timeout, no connection

    # Check push-to-talk button
    if not btn.value():
        time.sleep_ms(50)
        if not btn.value():
            pcm = record_pcm(RECORD_SECONDS)
            wav = voice_round_trip(pcm)
            if wav:
                play_wav(wav)
            else:
                led_error()
            while not btn.value():
                time.sleep_ms(20)
    time.sleep_ms(20)
