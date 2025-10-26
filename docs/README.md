# Dokumentasi Teknis Lengkap

Dokumen ini menjelaskan arsitektur, asumsi, dan cara reproduksi demo HeyPico Maps LLM. Tujuannya
agar HR maupun penguji dapat menilai kualitas solusi serta menjalankan sistem tanpa langkah yang
terlewat.

## 1. Gambaran Arsitektur

```
┌─────────────────────┐  Prompt + Koordinat  ┌────────────────────┐
│ demo/index-llm.html │ ───────────────────▶ │ FastAPI Backend    │
│ (Frontend Statis)   │                      │ (/api/llm/places) │
└─────────────────────┘                      ├────────────────────┤
                                             │ 1. LLM Intent      │
                                             │ 2. Cache + Rate    │
                                             │ 3. Google Maps API │
                                             └────────┬───────────┘
                                                     │
                                                     ▼
                                          ┌────────────────────┐
                                          │ Google Maps APIs   │
                                          │ (Places, Directions│
                                          │  Embed)            │
                                          └────────────────────┘
```

- **Frontend**: Halaman statis `demo/index-llm.html` yang dikonsumsi melalui browser. File ini
  menangani input prompt, menampilkan daftar tempat, iframe embed, dan tautan directions.
- **Backend**: FastAPI, layanan LLM lokal, rate limiter, serta DiskCache.
- **Eksternal**: Google Maps API untuk hasil pencarian, embed map, dan directions.

## 2. Komponen Utama

| Komponen | Deskripsi |
| --- | --- |
| `src/services/llm_service.py` | Memuat model Hugging Face lokal dan mengekstrak intent JSON dari prompt. Ada fallback heuristik bila LLM gagal. |
| `src/routes/llm_places.py` | Endpoint utama. Menggabungkan intent, memanggil Google Maps Text Search, membangun URL embed & direction, menerapkan caching. |
| `src/services/maps_client.py` | (terdapat dalam repo) Abstraksi pemanggilan Google Maps API dengan retry & error handling. |
| `src/main.py` | Inisialisasi aplikasi, middleware CORS, SlowAPI limiter, serta health check. |
| `demo/` | Halaman HTML demo (`index-llm.html`) beserta aset pendukung. |

## 3. Alur Sequence `POST /api/llm/places`

1. Terima payload `{ prompt, user_lat?, user_lng? }`.
2. Jalankan `extract_intent_from_prompt` untuk mendapatkan struktur `{query, location, radius_m}`.
3. Bangun cache key berdasarkan intent + koordinat user. Bila cache hit, langsung return.
4. Jika user mengirim koordinat → gunakan `text_search` dengan parameter `lat`, `lng`, dan `radius`.
   Jika tidak → gunakan query teks `"<query> near <location>"`.
5. Normalisasi hasil Places menjadi maksimal 5 item (nama, alamat, koordinat, place_id, maps_url).
6. Bangun `embed_url` dengan prioritas: koordinat spesifik → fallback query.
7. Bangun `directions_url` dengan origin user (jika ada) atau lokasi dari intent.
8. Simpan hasil ke cache dengan TTL (`CACHE_TTL_SECONDS`).

## 4. Keamanan & Kualitas

- **Rate Limiting**: SlowAPI default `RATE_LIMIT_PER_MINUTE=30`. Bisa diatur via env.
- **Caching**: DiskCache di folder `.cache`. Membantu menghemat kuota Google Maps.
- **LLM Safety**: Prompt diarahkan agar hanya menghasilkan JSON. Bila gagal, heuristik regex
  memastikan sistem tetap berjalan.
- **API Key Handling**: Key hanya dibaca dari environment. README menjelaskan cara pembatasan.
- **Logging**: Peringatan dicatat untuk input koordinat invalid atau error Maps API.

## 5. Asumsi Penting

1. Pengguna akhir menjalankan demo utama melalui halaman statis `demo/index-llm.html`.
2. Open WebUI hanya diperlukan bila evaluator ingin menguji integrasi opsional yang tersedia.
3. Koordinat pengguna bersifat opsional. Bila tidak ada, sistem mengandalkan teks lokasi.
4. LLM lokal bisa diganti dengan model lain asalkan kompatibel dengan pipeline
   `text-generation` Hugging Face.
5. Penguji memiliki Google Maps API key sendiri saat menjalankan demo.

## 6. Cara Replikasi Demo

1. Ikuti instruksi `Setup Cepat` pada README utama untuk menjalankan backend.
2. Dari folder repo, jalankan server statis untuk menyajikan halaman demo:

   ```bash
   python -m http.server 3000 --directory demo
   ```

3. Buka `http://localhost:3000/index-llm.html` lalu kirim prompt contoh:
   ```json
   {
     "prompt": "tolong carikan ramen enak radius 2000 meter dekat blok m",
     "user_lat": -6.244098,
     "user_lng": 106.800644
   }
   ```
4. Halaman akan memanggil backend, menampilkan daftar tempat, dan mengisi iframe `embed_url`.
   Tombol **Open Directions** membuka `directions_url` di tab baru.
5. Validasi bahwa rate limit bekerja (HTTP 429) dengan mengirim >30 request/menit dari IP yang sama.
6. Untuk melihat caching, kirim prompt yang sama dua kali; request kedua lebih cepat dan tidak
   mengurangi kuota API.
7. (Opsional) Bila ingin mencoba Open WebUI, ikuti instruksi tambahan pada `webui/README.md`. Ini
   tidak diperlukan untuk demo utama.

## 7. Screenshot Demo

![Demo Open]
127.0.0.1_5500_index-llm.html.png
Screenshot 2025-10-27 011429.png
127.0.0.1_8000_docs.png

## 8. Pengujian & Observabilitas

- **Pengujian Manual**: Dilakukan dengan cURL dan halaman `demo/index-llm.html` untuk memverifikasi
  intent extraction, hasil Places, serta URL embed/directions. Open WebUI digunakan sebagai uji
  tambahan opsional.
- **Pengujian Otomatis**: Belum disiapkan karena keterbatasan kredensial API dalam CI. Disarankan
  menambahkan test unit untuk `llm_service` (dengan mocking pipeline) dan `maps_client` (dengan
  VCR/response mocking).
- **Monitoring**: Saat deploy, gunakan Cloud Logging/Stackdriver untuk request outbound dan set
  alert penggunaan API key.

## 9. Langkah Lanjut yang Direkomendasikan

1. **Autentikasi Backend** – Tambahkan API key internal/JWT agar endpoint tidak bisa dipakai umum.
2. **Model Orchestration** – Gunakan model yang lebih akurat (misal Mistral Instruct) atau tambahkan
   few-shot prompt untuk meningkatkan kualitas intent.
3. **Front-End Enhancements** – Bangun UI React/Next.js kecil untuk menampilkan peta embed langsung
   tanpa tergantung pada WebUI.
4. **Observability** – Pasang OpenTelemetry untuk tracing request LLM ↔ Maps API.

Dokumentasi ini memastikan HR dan penguji memahami struktur sistem, alasan desain, dan cara
mengoperasikan solusi secara end-to-end.