"""
server.py
Server multi-client untuk aplikasi Chat, File Transfer, dan Video Streaming
dengan autentikasi email OTP.

Arsitektur: Multi-threaded TCP server. Setiap client yang connect ditangani
oleh satu thread terpisah (thread-per-connection model). Semua fitur
(chat, file transfer, video streaming) dimultipleks melalui satu koneksi
socket per client menggunakan protokol pesan JSON ber-framing (lihat
protocol.py).

Alur autentikasi:
    1. Client kirim AUTH_REQUEST {email}
    2. Server generate OTP & kirim ke email (auth_email.py) -> balas AUTH_SENT
    3. Client kirim AUTH_VERIFY {email, code}
    4. Server verifikasi -> balas AUTH_OK atau AUTH_FAIL
    5. Setelah AUTH_OK, client dapat mengirim CHAT, FILE_META/FILE_CHUNK,
       dan VIDEO_FRAME. Server menolak (ERROR) permintaan dari client yang
       belum terautentikasi.
"""

import base64
import logging
import os
import socket
import threading
import time

import auth_email
import cv2
import numpy as np
import protocol

HOST = "0.0.0.0"
PORT = 5050

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                     datefmt="%H:%M:%S")
log = logging.getLogger("server")

SERVER_STORAGE_DIR = "server_storage"
SERVER_VIDEOS_DIR = "server_videos"

os.makedirs(SERVER_STORAGE_DIR, exist_ok=True)
os.makedirs(SERVER_VIDEOS_DIR, exist_ok=True)

# active_streams: { conn_socket: threading.Event() }
active_streams_lock = threading.Lock()
active_streams = {}

def ensure_sample_video():
    """Membuat file video contoh (sample.mp4) di server jika belum ada."""
    sample_path = os.path.join(SERVER_VIDEOS_DIR, "sample.mp4")
    if not os.path.exists(sample_path):
        log.info("Membuat file video contoh (sample.mp4) di server...")
        try:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            # 10 fps, 320x240, 100 frame (10 detik)
            writer = cv2.VideoWriter(sample_path, fourcc, 10.0, (320, 240))
            for i in range(100):
                frame = np.zeros((240, 320, 3), dtype=np.uint8)
                # Gradien dinamis
                color = (int(i * 2.5) % 256, int((100 - i) * 2.5) % 256, int(i * 5) % 256)
                frame[:] = color
                cv2.putText(
                    frame, 
                    f"SERVER STREAM - FRAME {i+1}", 
                    (15, 120), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.6, 
                    (255, 255, 255), 
                    2
                )
                writer.write(frame)
            writer.release()
            log.info("File video contoh (sample.mp4) sukses dibuat.")
        except Exception as e:
            log.error(f"Gagal membuat video contoh: {e}")

def stream_video_to_client(conn, filepath, stop_event):
    """Membaca file video dari disk server dan mengirimkannya ke client."""
    log.info(f"Mulai streaming {filepath} ke client...")
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            protocol.send_msg(conn, {"type": "ERROR", "text": f"Gagal membuka video: {os.path.basename(filepath)}"})
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        delay = 1.0 / fps

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                break  # Video selesai

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                try:
                    # Kirim frame dengan sender "SERVER"
                    protocol.send_msg(conn, {
                        "type": "VIDEO_FRAME",
                        "from": "SERVER",
                        "data_b64": base64.b64encode(buf).decode()
                    })
                except OSError:
                    break  # Client putus
            time.sleep(delay)

        cap.release()
    except Exception as e:
        log.error(f"Error streaming video ke client: {e}")
    finally:
        try:
            protocol.send_msg(conn, {"type": "STREAM_STOP", "from": "SERVER"})
        except OSError:
            pass
        # Hapus event dari active_streams
        with active_streams_lock:
            if conn in active_streams:
                del active_streams[conn]
        log.info(f"Streaming {filepath} selesai/dihentikan.")

# clients: { conn_socket: {"email": str, "authenticated": bool} }
clients_lock = threading.Lock()
clients = {}


def broadcast(message: dict, exclude_conn=None, target_email=None):
    """Mengirim pesan ke semua client terautentikasi, atau ke satu
    target_email tertentu bila ditentukan."""
    with clients_lock:
        for conn, info in list(clients.items()):
            if not info.get("authenticated"):
                continue
            if conn is exclude_conn:
                continue
            if target_email and info.get("email") != target_email:
                continue
            try:
                protocol.send_msg(conn, message)
            except OSError:
                pass


def handle_client(conn: socket.socket, addr):
    log.info(f"Koneksi baru dari {addr}")
    with clients_lock:
        clients[conn] = {"email": None, "authenticated": False}

    incoming_files_server = {}
    try:
        while True:
            msg = protocol.recv_msg(conn)
            if msg is None:
                break

            mtype = msg.get("type")
            info = clients[conn]

            # ---------- AUTENTIKASI ----------
            if mtype == "REGISTER_REQ":
                email = msg.get("email")
                password = msg.get("password")
                if auth_email.register_user(email, password):
                    code = auth_email.peek_otp(email)
                    resp_payload = {"type": "REGISTER_OTP_SENT", "email": email}
                    if auth_email.MOCK_EMAIL:
                        resp_payload["mock_otp"] = code
                    protocol.send_msg(conn, resp_payload)
                    log.info(f"Permintaan registrasi untuk {email}, OTP dikirim")
                else:
                    protocol.send_msg(conn, {"type": "REGISTER_FAIL", "text": "Email sudah terdaftar dan terverifikasi."})
                    log.info(f"Registrasi gagal untuk {email}: Email sudah terdaftar")

            elif mtype == "REGISTER_VERIFY":
                email = msg.get("email")
                code = msg.get("code")
                if auth_email.verify_registration(email, code):
                    protocol.send_msg(conn, {"type": "REGISTER_SUCCESS", "email": email})
                    log.info(f"Registrasi sukses untuk {email}")
                else:
                    protocol.send_msg(conn, {"type": "REGISTER_VERIFY_FAIL", "text": "Kode OTP salah atau kadaluarsa."})
                    log.info(f"Verifikasi registrasi gagal untuk {email}")

            elif mtype == "LOGIN_REQ":
                email = msg.get("email")
                password = msg.get("password")
                if auth_email.authenticate_user(email, password):
                    info["authenticated"] = True
                    info["email"] = email
                    protocol.send_msg(conn, {"type": "LOGIN_OK", "email": email})
                    log.info(f"{email} berhasil login")
                    broadcast({"type": "SYSTEM",
                               "text": f"{email} bergabung ke chat"},
                              exclude_conn=conn)
                else:
                    protocol.send_msg(conn, {"type": "LOGIN_FAIL", "text": "Email/password salah atau akun belum diverifikasi."})
                    log.info(f"Login gagal untuk {email}")

            # ---------- WAJIB SUDAH LOGIN UNTUK FITUR DI BAWAH ----------
            elif not info.get("authenticated"):
                protocol.send_msg(conn, {"type": "ERROR",
                                          "text": "Anda belum login/terverifikasi"})

            # ---------- CHAT ----------
            elif mtype == "CHAT":
                text = msg.get("text")
                sender = info["email"]
                log.info(f"[CHAT] {sender}: {text}")
                broadcast({"type": "CHAT", "from": sender, "text": text},
                          exclude_conn=conn)

            # ---------- FILE TRANSFER (simpan di server & relay ke target / semua) ----------
            elif mtype in ("FILE_META", "FILE_CHUNK", "FILE_END"):
                # 1. Simpan di disk server
                filename = msg.get("filename")
                if filename:
                    filename = os.path.basename(filename)
                    if mtype == "FILE_META":
                        incoming_files_server[filename] = {
                            "size": msg.get("size"),
                            "chunks": []
                        }
                        log.info(f"[FILE-SERVER] Menerima '{filename}' ({msg.get('size')} bytes) untuk disimpan di server...")
                    elif mtype == "FILE_CHUNK" and filename in incoming_files_server:
                        data = base64.b64decode(msg["data_b64"])
                        incoming_files_server[filename]["chunks"].append(data)
                    elif mtype == "FILE_END" and filename in incoming_files_server:
                        full_data = b"".join(incoming_files_server[filename]["chunks"])
                        save_path = os.path.join(SERVER_STORAGE_DIR, filename)
                        with open(save_path, "wb") as f:
                            f.write(full_data)
                        log.info(f"[FILE-SERVER] File '{filename}' sukses disimpan di server -> {save_path}")
                        protocol.send_msg(conn, {
                            "type": "SYSTEM",
                            "text": f"File '{filename}' sukses disimpan di server_storage/"
                        })
                        del incoming_files_server[filename]

                # 2. Relay ke target (tetap jalan seperti semula)
                target = msg.get("target", "all")
                sender = info["email"]
                out = dict(msg)
                out["from"] = sender
                if target == "all":
                    broadcast(out, exclude_conn=conn)
                else:
                    broadcast(out, target_email=target)

            # ---------- VIDEO STREAMING (relay frame) ----------
            elif mtype == "VIDEO_FRAME":
                sender = info["email"]
                target = msg.get("target", "all")
                out = {"type": "VIDEO_FRAME", "from": sender,
                       "data_b64": msg.get("data_b64")}
                if target == "all":
                    broadcast(out, exclude_conn=conn)
                else:
                    broadcast(out, target_email=target)

            elif mtype == "STREAM_STOP":
                sender = info["email"]
                broadcast({"type": "STREAM_STOP", "from": sender},
                          exclude_conn=conn)

            # ---------- VIDEO STREAMING DARI SERVER (REQUEST) ----------
            elif mtype == "STREAM_REQ":
                filename = msg.get("filename", "sample.mp4")
                filename = os.path.basename(filename)
                video_path = os.path.join(SERVER_VIDEOS_DIR, filename)

                if not os.path.isfile(video_path):
                    protocol.send_msg(conn, {"type": "ERROR", "text": f"File video '{filename}' tidak ditemukan di server."})
                    continue

                # Hentikan stream yang sedang berjalan untuk client ini (jika ada)
                with active_streams_lock:
                    if conn in active_streams:
                        active_streams[conn].set()
                        time.sleep(0.2)

                    stop_event = threading.Event()
                    active_streams[conn] = stop_event

                threading.Thread(
                    target=stream_video_to_client,
                    args=(conn, video_path, stop_event),
                    daemon=True
                ).start()

            elif mtype == "STREAM_STOP_REQ":
                with active_streams_lock:
                    if conn in active_streams:
                        active_streams[conn].set()
                        time.sleep(0.1)

            elif mtype == "LIST_VIDEOS_REQ":
                try:
                    files = [f for f in os.listdir(SERVER_VIDEOS_DIR) 
                             if os.path.isfile(os.path.join(SERVER_VIDEOS_DIR, f))
                             and f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.3gp', '.webm'))]
                except Exception:
                    files = []
                protocol.send_msg(conn, {"type": "LIST_VIDEOS_RESP", "videos": files})

            elif mtype == "LIST_FILES_REQ":
                try:
                    files = []
                    for f in os.listdir(SERVER_STORAGE_DIR):
                        fpath = os.path.join(SERVER_STORAGE_DIR, f)
                        if os.path.isfile(fpath):
                            files.append({
                                "filename": f,
                                "size": os.path.getsize(fpath)
                            })
                except Exception:
                    files = []
                protocol.send_msg(conn, {"type": "LIST_FILES_RESP", "files": files})

            else:
                protocol.send_msg(conn, {"type": "ERROR",
                                          "text": f"Tipe pesan tidak dikenal: {mtype}"})

    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        # Hentikan stream aktif jika ada
        with active_streams_lock:
            if conn in active_streams:
                active_streams[conn].set()
        
        with clients_lock:
            email = clients[conn].get("email") if conn in clients else None
            if conn in clients:
                del clients[conn]
        conn.close()
        log.info(f"Koneksi {addr} ({email}) ditutup")
        if email:
            broadcast({"type": "SYSTEM", "text": f"{email} keluar dari chat"})


def main():
    ensure_sample_video()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)
    log.info(f"Server berjalan di {HOST}:{PORT}")

    try:
        server_sock.settimeout(1.0)  # Check for KeyboardInterrupt every second
        while True:
            try:
                conn, addr = server_sock.accept()
                conn.settimeout(None)  # Reset timeout for client connection
                t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        log.info("Server dihentikan")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
