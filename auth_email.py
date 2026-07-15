"""
auth_email.py
Modul autentikasi berbasis Password dengan verifikasi OTP saat pendaftaran akun baru.

Mode kerja OTP:
- MOCK_EMAIL = True  -> OTP tidak benar-benar dikirim ke email, tetapi dicetak
                        ke konsol server. Berguna untuk testing/development
                        tanpa perlu kredensial SMTP asli.
- MOCK_EMAIL = False -> OTP dikirim sungguhan melalui SMTP (mis. Gmail SMTP)
                        menggunakan kredensial pada environment variable:
                        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
"""

import os
import random
import smtplib
import ssl
import time
import json
import hashlib
from email.message import EmailMessage

MOCK_EMAIL = os.environ.get("MOCK_EMAIL", "false").lower() == "true"
OTP_TTL_SECONDS = 300  # OTP berlaku 5 menit

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "hafidz.student.gunadarma@gmail.com")   # Masukkan email Anda di sini
SMTP_PASS = os.environ.get("SMTP_PASS", "aeeleztjpydimjvd")      # Masukkan App Password Gmail Anda di sini

USERS_DB_PATH = "users.json"

# Penyimpanan OTP sementara: { email: (kode_otp, waktu_kadaluarsa) }
_otp_store = {}


def load_users() -> dict:
    """Membaca user database dari file users.json."""
    if not os.path.exists(USERS_DB_PATH):
        return {}
    try:
        with open(USERS_DB_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(users_data: dict) -> None:
    """Menyimpan user database ke file users.json."""
    try:
        with open(USERS_DB_PATH, "w") as f:
            json.dump(users_data, f, indent=4)
    except Exception as e:
        print(f"[AUTH] Gagal menyimpan user database: {e}")


def hash_password(password: str, salt: str = None) -> tuple:
    """Melakukan hashing password menggunakan SHA-256 dengan salt."""
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.sha256()
    h.update((password + salt).encode("utf-8"))
    return h.hexdigest(), salt


def generate_otp(email: str) -> str:
    """Membuat kode OTP 6 digit untuk sebuah email dan menyimpannya."""
    code = f"{random.randint(0, 999999):06d}"
    expiry = time.time() + OTP_TTL_SECONDS
    _otp_store[email] = (code, expiry)
    return code


def send_otp_email(email: str, code: str) -> None:
    """Mengirim OTP ke email tujuan (atau mencetak ke konsol jika MOCK_EMAIL)."""
    if MOCK_EMAIL:
        print(f"[MOCK-EMAIL] Kode OTP untuk {email} adalah: {code} "
              f"(berlaku {OTP_TTL_SECONDS//60} menit)")
        return

    msg = EmailMessage()
    msg["Subject"] = "Kode Verifikasi Pendaftaran - Aplikasi Jaringan"
    msg["From"] = SMTP_USER
    msg["To"] = email
    msg.set_content(
        f"Terima kasih telah mendaftar!\n\n"
        f"Kode verifikasi (OTP) pendaftaran Anda adalah: {code}\n"
        f"Kode ini berlaku selama {OTP_TTL_SECONDS//60} menit.\n"
        f"Jangan berikan kode ini kepada siapa pun."
    )

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def verify_otp(email: str, code: str) -> bool:
    """Memverifikasi kode OTP yang dimasukkan pengguna."""
    entry = _otp_store.get(email)
    if not entry:
        return False
    stored_code, expiry = entry
    if time.time() > expiry:
        del _otp_store[email]
        return False
    if stored_code == code:
        del _otp_store[email]  # OTP sekali pakai
        return True
    return False


def register_user(email: str, password: str) -> bool:
    """
    Mendaftarkan user baru dengan status is_verified = False.
    Mengembalikan True jika sukses mendaftarkan (atau mengupdate user yang belum terverifikasi).
    Mengembalikan False jika email sudah terdaftar dan terverifikasi.
    """
    users = load_users()
    if email in users and users[email].get("is_verified", False):
        return False

    # Hash password baru
    pwd_hash, salt = hash_password(password)
    users[email] = {
        "password_hash": pwd_hash,
        "salt": salt,
        "is_verified": False
    }
    save_users(users)

    # Kirim verifikasi OTP
    code = generate_otp(email)
    send_otp_email(email, code)
    return True


def verify_registration(email: str, code: str) -> bool:
    """
    Memverifikasi pendaftaran menggunakan kode OTP.
    Mengaktifkan akun (is_verified = True) jika kode cocok.
    """
    if verify_otp(email, code):
        users = load_users()
        if email in users:
            users[email]["is_verified"] = True
            save_users(users)
            return True
    return False


def authenticate_user(email: str, password: str) -> bool:
    """
    Memverifikasi kecocokan email dan password, serta memastikan akun sudah terverifikasi.
    """
    users = load_users()
    if email not in users:
        return False

    user_info = users[email]
    if not user_info.get("is_verified", False):
        return False

    stored_hash = user_info["password_hash"]
    salt = user_info["salt"]
    pwd_hash, _ = hash_password(password, salt)
    return pwd_hash == stored_hash


def peek_otp(email: str):
    """Hanya untuk keperluan automated-testing: melihat OTP tanpa menghapusnya."""
    entry = _otp_store.get(email)
    return entry[0] if entry else None
