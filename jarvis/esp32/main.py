# Jarvis ESP32 Client
# MicroPython firmware for ESP32-C3
# Flow: button press -> record I2S mic -> POST /voice to Pi API -> play WAV reply

from machine import Pin, I2S
import network
import time
import urequests

# ---------------------------------------------------------------------------
# Configuration - update these before flashing
# ---------------------------------------------------------------------------

WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASS = "YOUR_WIFI_PASSWORD"
BACKEND   = "http://PI_API_IP:8000"  # Raspberry Pi running jarvis backend

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
    return wlan.ifconfig()


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def record_pcm(seconds=RECORD_SECONDS):
    """Record raw 16-bit 16kHz mono PCM from INMP441."""
    print("Recording...")
    led.value(1)
    total  = seconds * RATE * 2  # bytes
    buf    = bytearray(BUF_SIZE)
    chunks = []
    got    = 0
    while got < total:
        n = mic.readinto(buf)
        if n:
            chunks.append(bytes(buf[:n]))
            got += n
    led.value(0)
    print("Recorded", got, "bytes")
    return b"".join(chunks)


def play_wav(wav_bytes):
    """
    Play WAV audio returned from the backend.
    Strips the 44-byte WAV header and writes raw PCM to the I2S speaker.
    """
    print("Playing reply...")
    led.value(1)
    pcm = wav_bytes[44:]  # skip WAV header
    pos = 0
    chunk = BUF_SIZE
    while pos < len(pcm):
        end = min(pos + chunk, len(pcm))
        spk.write(pcm[pos:end])
        pos = end
    led.value(0)
    print("Playback done")


# ---------------------------------------------------------------------------
# Backend call
# ---------------------------------------------------------------------------

def voice_round_trip(pcm_bytes):
    """
    POST raw PCM to /voice on the Pi API.
    Returns WAV bytes of the TTS reply.
    """
    print("Sending to backend...")
    boundary = b"----JarvisBoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="audio.raw"\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        + pcm_bytes
        + b"\r\n--" + boundary + b"--\r\n"
    )
    headers = {
        "Content-Type": "multipart/form-data; boundary=----JarvisBoundary",
        "Content-Length": str(len(body)),
    }
    r = urequests.post(BACKEND + "/voice", data=body, headers=headers)
    if r.status_code != 200:
        print("Backend error:", r.status_code, r.text)
        r.close()
        return None
    wav = r.content
    r.close()
    print("Received", len(wav), "bytes from backend")
    return wav


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

wifi_connect()
print("Jarvis ready. Hold button to speak.")

while True:
    if not btn.value():       # button pressed (active LOW)
        time.sleep_ms(50)     # debounce
        if not btn.value():
            pcm = record_pcm(RECORD_SECONDS)
            wav = voice_round_trip(pcm)
            if wav:
                play_wav(wav)
            # wait for button release
            while not btn.value():
                time.sleep_ms(20)
    time.sleep_ms(20)
