"""
web_client.py
Web Client Gateway untuk aplikasi Chat, File Transfer, dan Video Streaming.
Menghubungkan browser (melalui Socket.IO) ke server TCP socket (server.py).

Cara menjalankan:
    python web_client.py
    Lalu buka http://127.0.0.1:8080 (atau http://IP_KOMPUTER:8080 dari perangkat lain) di browser.
"""

import os
import socket
import threading
import time
import base64
import json
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit, disconnect
import protocol

app = Flask(__name__)
app.config['SECRET_KEY'] = 'netsuite-secret!'
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100000000)

# Simpan socket TCP per ID session Socket.IO (sid)
# Format: { sid: { "socket": sock, "stop_event": threading.Event, "email": str } }
client_connections = {}
conn_lock = threading.Lock()

TCP_SERVER_HOST = os.environ.get("TCP_SERVER_HOST", "127.0.0.1")
TCP_SERVER_PORT = int(os.environ.get("TCP_SERVER_PORT", "5050"))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download/<path:filename>')
def download_file(filename):
    # Preview inline for images, PDFs, and text; download directly for others
    lower_name = filename.lower()
    inline = lower_name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.txt'))
    return send_from_directory('server_storage', filename, as_attachment=not inline)

def tcp_listener(sid, sock, stop_event):
    """Mendengarkan data TCP dari server dan meneruskannya ke browser via Socket.IO."""
    print(f"[WEB-GATEWAY] Listener thread aktif untuk sesi {sid}")
    while not stop_event.is_set():
        try:
            msg = protocol.recv_msg(sock)
            if msg is None:
                socketio.emit('connection_lost', {'reason': 'Koneksi ke server TCP terputus.'}, to=sid)
                break
            
            # Teruskan pesan langsung ke browser client yang bersangkutan
            socketio.emit('server_message', msg, to=sid)
        except Exception as e:
            if not stop_event.is_set():
                socketio.emit('connection_lost', {'reason': str(e)}, to=sid)
            break
            
    cleanup_session(sid)

def cleanup_session(sid):
    """Membersihkan koneksi TCP dan menghentikan thread listener."""
    with conn_lock:
        if sid in client_connections:
            conn_info = client_connections[sid]
            conn_info["stop_event"].set()
            try:
                conn_info["socket"].close()
            except:
                pass
            del client_connections[sid]
            print(f"[WEB-GATEWAY] Sesi {sid} berhasil dibersihkan.")

@socketio.on('connect')
def handle_connect():
    print(f"[WEB-GATEWAY] Browser terhubung: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"[WEB-GATEWAY] Browser terputus: {request.sid}")
    cleanup_session(request.sid)

@socketio.on('register_request')
def handle_register_request(data):
    sid = request.sid
    host = TCP_SERVER_HOST
    port = TCP_SERVER_PORT
    email = data.get('email')
    password = data.get('password')
    
    # Bersihkan sesi lama jika ada
    cleanup_session(sid)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        sock.settimeout(None)
        
        # Kirim REGISTER_REQ ke server TCP
        protocol.send_msg(sock, {"type": "REGISTER_REQ", "email": email, "password": password})
        resp = protocol.recv_msg(sock)
        
        if resp and resp.get("type") == "REGISTER_OTP_SENT":
            stop_event = threading.Event()
            with conn_lock:
                client_connections[sid] = {
                    "socket": sock,
                    "stop_event": stop_event,
                    "email": email
                }
            emit('register_otp_sent', {
                "email": email,
                "mock_otp": resp.get("mock_otp")
            })
        else:
            reason = resp.get("text", "Pendaftaran gagal.") if resp else "Koneksi ditutup oleh server"
            emit('error_message', {"text": f"Gagal mendaftar. {reason}"})
            sock.close()
    except Exception as e:
        emit('error_message', {"text": f"Koneksi gagal: {str(e)}"})

@socketio.on('register_verify')
def handle_register_verify(data):
    sid = request.sid
    code = data.get('code')
    
    with conn_lock:
        if sid not in client_connections:
            emit('error_message', {"text": "Sesi registrasi tidak ditemukan. Silakan daftar ulang."})
            return
        conn_info = client_connections[sid]
        sock = conn_info["socket"]
        email = conn_info["email"]
        
    try:
        # Kirim verifikasi ke server TCP
        protocol.send_msg(sock, {"type": "REGISTER_VERIFY", "email": email, "code": code})
        resp = protocol.recv_msg(sock)
        
        if resp and resp.get("type") == "REGISTER_SUCCESS":
            emit('register_success', {"email": email, "text": "Pendaftaran berhasil! Silakan login dengan akun Anda."})
            cleanup_session(sid)  # Bersihkan socket registrasi sementara
        else:
            reason = resp.get("text", "Kode OTP salah atau kadaluarsa.") if resp else "Verifikasi registrasi gagal"
            emit('register_verify_fail', {"text": reason})
    except Exception as e:
        emit('error_message', {"text": f"Koneksi terputus saat verifikasi: {str(e)}"})
        cleanup_session(sid)

@socketio.on('login_request')
def handle_login_request(data):
    sid = request.sid
    host = TCP_SERVER_HOST
    port = TCP_SERVER_PORT
    email = data.get('email')
    password = data.get('password')
    
    # Bersihkan sesi lama jika ada
    cleanup_session(sid)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        sock.settimeout(None)
        
        # Kirim LOGIN_REQ ke server TCP
        protocol.send_msg(sock, {"type": "LOGIN_REQ", "email": email, "password": password})
        resp = protocol.recv_msg(sock)
        
        if resp and resp.get("type") == "LOGIN_OK":
            stop_event = threading.Event()
            with conn_lock:
                client_connections[sid] = {
                    "socket": sock,
                    "stop_event": stop_event,
                    "email": email
                }
            emit('auth_ok', {"email": email})
            # Mulai thread listening TCP di background untuk sesi login aktif
            t = threading.Thread(
                target=tcp_listener, 
                args=(sid, sock, stop_event),
                daemon=True
            )
            t.start()
        else:
            reason = resp.get("text", "Email atau password salah.") if resp else "Koneksi ditutup oleh server"
            emit('auth_fail', {"text": reason})
            sock.close()
    except Exception as e:
        emit('error_message', {"text": f"Koneksi gagal: {str(e)}"})

@socketio.on('send_chat')
def handle_send_chat(data):
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {"type": "CHAT", "text": data.get("text")})

@socketio.on('send_file_meta')
def handle_file_meta(data):
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {
                "type": "FILE_META", 
                "filename": data.get("filename"),
                "size": data.get("size"),
                "target": data.get("target", "all")
            })

@socketio.on('send_file_chunk')
def handle_file_chunk(data):
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {
                "type": "FILE_CHUNK", 
                "filename": data.get("filename"),
                "data_b64": data.get("data_b64"),
                "target": data.get("target", "all")
            })

@socketio.on('send_file_end')
def handle_file_end(data):
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {
                "type": "FILE_END", 
                "filename": data.get("filename"),
                "target": data.get("target", "all")
            })

@socketio.on('request_server_stream')
def handle_request_server_stream(data):
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {"type": "STREAM_REQ", "filename": data.get("filename")})

@socketio.on('stop_server_stream')
def handle_stop_server_stream(data=None):
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {"type": "STREAM_STOP_REQ"})

@socketio.on('get_server_videos')
def handle_get_server_videos():
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {"type": "LIST_VIDEOS_REQ"})

@socketio.on('get_server_files')
def handle_get_server_files():
    sid = request.sid
    with conn_lock:
        if sid in client_connections:
            sock = client_connections[sid]["socket"]
            protocol.send_msg(sock, {"type": "LIST_FILES_REQ"})


if __name__ == '__main__':
    # Jalankan agar bisa diakses oleh IP lokal komputer di port 8080
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)
