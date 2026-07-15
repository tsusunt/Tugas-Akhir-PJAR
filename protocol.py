"""
protocol.py
Modul framing pesan untuk komunikasi client-server.

Setiap pesan dikirim dalam format:
    [4 byte panjang pesan (big-endian)] + [payload JSON dalam bytes UTF-8]

Payload JSON berbentuk dict, minimal memiliki key "type" yang menandakan
jenis pesan, contoh:
    {"type": "AUTH_REQUEST", "email": "user@example.com"}
    {"type": "CHAT", "from": "a@x.com", "text": "halo"}
    {"type": "FILE_META", "filename": "a.txt", "size": 1234, "target": "all"}
    {"type": "FILE_CHUNK", "data_b64": "..."}
    {"type": "VIDEO_FRAME", "from": "a@x.com", "data_b64": "..."}
"""

import json
import struct

HEADER_SIZE = 4  # 4 byte unsigned int untuk panjang payload


def send_msg(sock, message: dict) -> None:
    """Mengirim dict sebagai pesan JSON ber-framing panjang lewat socket."""
    payload = json.dumps(message).encode("utf-8")
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def _recv_exact(sock, n: int) -> bytes:
    """Membaca tepat n byte dari socket, atau None jika koneksi tertutup."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_msg(sock) -> dict:
    """Menerima satu pesan JSON dari socket. Mengembalikan None jika koneksi
    tertutup oleh lawan bicara."""
    header = _recv_exact(sock, HEADER_SIZE)
    if header is None:
        return None
    (length,) = struct.unpack(">I", header)
    payload = _recv_exact(sock, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))
