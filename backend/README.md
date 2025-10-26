# HeyPico Maps Backend

Backend FastAPI yang menangani integrasi LLM lokal dan Google Maps API. Seluruh rahasia disimpan di
`.env` (lihat `.env.example`).

## Konfigurasi Environment

Salin `.env.example` menjadi `.env` lalu isi nilai berikut:

| Variabel | Deskripsi |
| --- | --- |
| `LOCAL_LLM_MODEL_NAME` | Nama model Hugging Face untuk ekstraksi intent (default `sshleifer/tiny-gpt2`). |
| `GOOGLE_MAPS_API_KEY` | API key Google Maps yang dibatasi untuk backend (aktifkan Places, Directions, Embed). |
| `RATE_LIMIT_PER_MINUTE` | Batas rate limit per IP. Default `30`. |
| `CACHE_TTL_SECONDS` | TTL cache hasil Places dalam detik. Default `600`. |
| `USER_SEARCH_RADIUS_METERS` | Radius default (meter) jika user mengirim koordinat. Default `3000`. |

**Rekomendasi keamanan**

- Restrict API key pada Google Cloud ke fitur *Places API*, *Maps Embed API*, dan *Directions API*.
- Tambahkan pembatasan IP pada API key agar hanya backend yang dapat menggunakannya.
- Jangan pernah mengirim API key ke klien atau menyimpannya di repositori publik.

## Menjalankan Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Saat startup Anda akan melihat log pemuatan model LLM lokal dan device yang digunakan.

## Endpoint Penting

- `POST /api/llm/places` — menerima body `{ "prompt": "...", "user_lat?": float, "user_lng?": float }`
  dan mengembalikan intent pencarian, hasil Places, `embed_url`, serta `directions_url`.
- `GET /api/places` — proxy ke Google Places Text Search dengan parameter query manual.
- `GET /api/directions` — menghasilkan rute Google Maps berdasarkan origin & destination.
- `GET /api/health` — status aplikasi.

## (Opsional) Integrasi Open WebUI

> Demo utama menggunakan halaman statis `demo/index-llm.html`. Langkah berikut hanya diperlukan
> bila Anda ingin mencoba backend melalui Open WebUI.

1. Buka Open WebUI → **Settings** → **Tools** → **Add Tool**.
2. Isi:
   - **Name**: `places`
   - **Method**: `POST`
   - **URL**: `http://<HOST_BACKEND>/api/llm/places`
   - **Description**: `Cari tempat via prompt; kembalikan embed map + directions.`
3. Simpan. Ketika pengguna mengirim prompt di chat, pilih tool `places` untuk mengirim `{ "prompt": "<teks user>" }` ke backend.
4. Tampilkan `embed_url` (misal sebagai tautan atau iframe jika didukung) dan `directions_url` sebagai tautan rute di UI.

Cache Places dan rate limit berjalan otomatis di backend berdasarkan konfigurasi environment.