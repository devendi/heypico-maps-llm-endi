# HeyPico Maps LLM – Technical Test Submission

HeyPico Maps LLM adalah prototipe end-to-end untuk memenuhi tes teknis HeyPico.ai. Sistem ini
menyediakan backend FastAPI yang menggabungkan Large Language Model (LLM) lokal dengan Google
Maps API agar pengguna cukup mengetikkan prompt natural language untuk menemukan tempat, melihat
peta ter-embed, dan membuka rute arah.

## Highlight Fitur

- **LLM Intent Extraction Lokal** – Menggunakan model Hugging Face yang dijalankan lokal untuk
  mengekstrak `query`, `location`, dan `radius` dari prompt pengguna.
- **Integrasi Google Maps Lengkap** – Menggunakan Places API (Text Search), Directions API, dan
  Maps Embed API. Response mengembalikan daftar tempat, URL embed peta, dan URL directions.
- **Rate Limiting & Cache** – SlowAPI membatasi request per IP; DiskCache menyimpan hasil Places
  untuk mempercepat response dan menghemat kuota API.
- **Demo Frontend Statis** – File `demo/index-llm.html` sudah disiapkan untuk menampilkan prompt,
  hasil rekomendasi, embed map, dan tombol directions secara langsung tanpa perlu Open WebUI.
- **Keamanan Kunci API** – Variabel environment wajib diisi. README menjelaskan praktik terbaik
  untuk membatasi akses Google Maps API Key.

## Struktur Repositori

```
backend/       ← FastAPI + layanan LLM & Google Maps
demo/          ← Halaman statis `index-llm.html` untuk menjalankan demo end-to-end
webui/         ← (Opsional) Definisi tool bila ingin mencoba Open WebUI
docs/          ← Dokumentasi arsitektur + bukti demo
```

## Persyaratan Sistem

- Python 3.11+
- Akses internet untuk mengunduh model Hugging Face & memanggil Google Maps API
- API key Google Maps (aktifkan Places API, Directions API, Maps Embed API)
- Opsional: GPU dengan CUDA jika ingin akselerasi inferensi LLM lokal

## Setup Cepat

1. **Clone repository** dan masuk ke folder `backend`.
2. **Buat virtualenv** dan instal dependensi:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Konfigurasi environment** dengan menyalin `.env.example` → `.env` dan isi variabel berikut:

   | Variable | Keterangan |
   | --- | --- |
   | `GOOGLE_MAPS_API_KEY` | API key yang dibatasi untuk backend saja. |
   | `LOCAL_LLM_MODEL_NAME` | (Opsional) Nama model Hugging Face. Default: `sshleifer/tiny-gpt2`. |
   | `RATE_LIMIT_PER_MINUTE` | (Opsional) Batas request per IP. Default: `30`. |
   | `CACHE_TTL_SECONDS` | (Opsional) TTL cache hasil Places. Default: `600`. |
   | `USER_SEARCH_RADIUS_METERS` | (Opsional) Radius default bila user mengirim koordinat. |

4. **Jalankan backend**:

   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000
   ```

5. **Endpoint kesehatan** tersedia di `GET /api/health`.

## Alur Kerja

1. Pengguna menulis prompt (contoh: “Cari coffee shop nyaman untuk kerja“).
2. Endpoint `POST /api/llm/places` memanggil LLM lokal untuk mengekstrak intent terstruktur.
3. Backend memanggil Google Places Text Search, kemudian membangun URL embed dan directions.
4. Response mengandung:
   - `intent` terstruktur (query, location, radius)
   - `places` (maks 5 tempat teratas dengan koordinat dan URL Google Maps)
   - `embed_url` (bisa langsung di-iframe)
   - `directions_url` (bisa dibuka di tab baru)

Jika pengguna menyertakan koordinat (`user_lat`, `user_lng`), backend menggunakan posisi tersebut
untuk pencarian dan rute, bukan sekadar teks lokasi.

## Menjalankan Demo Frontend (`demo/index-llm.html`)

1. Pastikan backend FastAPI sudah berjalan pada `http://localhost:8000` (atau host lain sesuai
   kebutuhan).
2. Dari folder repositori ini, jalankan server statis sederhana untuk menyajikan file HTML demo:

   ```bash
   python -m http.server 3000 --directory demo
   ```

3. Buka `http://localhost:3000/index-llm.html` di browser. Halaman ini menyediakan input prompt,
   daftar hasil rekomendasi, dan iframe Google Maps yang membaca data langsung dari backend.
4. Klik tombol **Open Directions** pada salah satu hasil untuk membuka rute di tab baru.

> **Catatan**: File `demo/index-llm.html` merupakan jalur utama demo resmi. Folder `webui/` hanya
> disertakan bila evaluator ingin mencoba integrasi opsional dengan Open WebUI.

### (Opsional) Integrasi dengan Open WebUI

1. Jalankan Open WebUI sesuai dokumentasi resmi.
2. Masuk ke **Settings → Tools → Add Tool** dan isi:
   - **Name**: `places`
   - **Method**: `POST`
   - **URL**: `http://<alamat-backend>/api/llm/places`
   - **Description**: `Cari tempat via prompt; hasilkan embed dan directions URL.`
3. Saat chat, pilih tool `places` atau biarkan agent otomatis memanggilnya.
4. Tampilkan `embed_url` dalam iframe (jika UI mendukung) dan `directions_url` sebagai tombol atau
   tautan menuju Google Maps.

Detail tambahan tersedia di `webui/README.md` bila Anda ingin mengeksplorasi opsi opsional ini.

## Praktik Keamanan Google Maps API

- Restrict API key ke **HTTP referrers** atau **IP Address** server backend.
- Aktifkan hanya API yang dibutuhkan: Places API, Directions API, Maps Embed API.
- Monitoring penggunaan melalui Google Cloud Console dan set kuota harian untuk mencegah
  penyalahgunaan.
- Jangan commit `.env` atau API key ke repositori publik.

## Dokumentasi Tambahan

- Detail arsitektur, diagram sequence, asumsi, dan screenshot demo tersedia di `docs/README.md`.
- Panduan menjalankan halaman demo statis ada di bagian "Menjalankan Demo Frontend" di README ini.
- Backend API secara mendalam (service layer, caching, pengamanan) dibahas di `backend/README.md`.

## Rencana Pengembangan Lanjutan

- Mengganti model LLM default ke model instruksi ringan (misalnya `NousResearch/Hermes-2-Pro`) untuk
  meningkatkan akurasi intent.
- Menambahkan autentikasi (API key atau JWT) pada backend sebelum di-deploy publik.
- Menambah observability (OpenTelemetry + logging terstruktur) untuk memantau pemakaian.
- Unit test untuk layanan LLM & Maps client ketika kredensial testing tersedia.

Dokumentasi ini disiapkan agar HR dan penguji dapat memahami solusi secara menyeluruh dan langsung
mereproduksi demo lokal menggunakan repositori ini.