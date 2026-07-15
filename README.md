# Aplikasi Multi-Fitur Pemrograman Jaringan
### Tugas Akhir Pemrograman Jaringan (PJAR) - Universitas Gunadarma

Sistem komunikasi *client-server* terdistribusi yang menghubungkan **Web Browser** di sisi frontend ke **Raw TCP Socket Server** di sisi backend menggunakan **Web Gateway (Flask-SocketIO)** sebagai perantaranya.

---

## 📁 Struktur Direktori

```text
pjarr/
├── auth_email.py       # Logika otentikasi akun & pengiriman OTP (SMTP Gmail)
├── protocol.py         # Custom TCP socket framing protocol (length-prefixed)
├── server.py           # Backend TCP Socket Server (Multithreaded)
├── web_client.py       # Web Gateway/Bridge Server (Flask & Socket.IO)
├── requirements.txt    # File dependensi Python
├── users.json          # Database lokal user terdaftar (Password SHA-256 + Salt)
├── templates/
│   └── index.html      # Antarmuka Web Klien (Dark Mode & Glassmorphism)
├── server_storage/     # Folder penyimpanan file hasil transfer
└── server_videos/      # Folder penyimpanan file video untuk streaming
```

---

## 🌟 Fitur Utama

1. **💬 Chatting Real-Time**: Kirim-terima pesan teks antar-klien dengan metode broadcast.
2. **📂 File Sharing**: Kirim file secara chunk (60 KB) dari browser ke server, preview gambar langsung di chat, dan unduh file dari server via HTTP.
3. **🎥 Video Streaming**: Streaming video `.mp4` dari server (menggunakan OpenCV untuk pemrosesan frame) ke tag `<img>` di browser klien.
4. **🔑 Otentikasi OTP**: Sistem login dengan registrasi OTP 6-digit yang dikirim secara otomatis ke email klien menggunakan SMTP Gmail.

---

## 🛠️ Instalasi & Cara Menjalankan

### 1. Instalasi Dependensi
Instal semua library yang dibutuhkan melalui terminal:
```bash
pip install -r requirements.txt
pip install Flask Flask-SocketIO eventlet
```

### 2. Konfigurasi SMTP Email
Buka file [auth_email.py](file:///c:/main%20storage/DocumentsPC/!kuliah/S%208/tugas/pemrog%20jaringan/ta/M13_Hafidz%20Alfiansyah_50422636_4IA06_tugas%20akhir%20PJAR/pjarr/auth_email.py) dan perbarui kredensial SMTP Gmail Anda pada baris 28-29:
```python
SMTP_USER = "email_anda@gmail.com"
SMTP_PASS = "app_password_gmail_anda"
```

### 3. Menjalankan Aplikasi
Jalankan kedua file server berikut di dua terminal terpisah:

* **Terminal 1 (TCP Server):**
  ```bash
  python server.py
  ```
* **Terminal 2 (Web Gateway):**
  ```bash
  python web_client.py
  ```

Setelah kedua server berjalan, buka browser dan akses alamat:
```text
http://127.0.0.1:8080
```
*(Atau `http://IP_KOMPUTER_HOST:8080`).*

---

## 👤 Pembuat / Author

* **Nama**: Hafidz Alfiansyah
* **NPM**: 50422636
* **Kelas**: 4IA06
* **Mata Kuliah**: Pemrograman Jaringan (Tugas Akhir)
* **Institusi**: Universitas Gunadarma
