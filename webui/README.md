# Integrasi Open WebUI (Opsional)

> **Catatan:** Demo utama solusi ini menggunakan halaman statis `demo/index-llm.html`. Dokumen ini
> hanya diperlukan jika Anda ingin mengevaluasi backend melalui Open WebUI sebagai eksperimen
> tambahan.

Folder ini berisi panduan menambahkan tool `places` ke Open WebUI agar dapat memanggil backend
HeyPico Maps LLM.

## Konfigurasi Tool

1. Buka Open WebUI → **Settings → Tools → Add Tool**.
2. Isi data berikut:
   - **Name**: `places`
   - **Method**: `POST`
   - **URL**: `http://<HOST_BACKEND>:8000/api/llm/places`
   - **Description**: `Cari tempat via prompt; kembalikan embed & directions URL.`
3. Simpan konfigurasi.

## Contoh Payload

```json
{
  "prompt": "Cari coffee shop instagramable radius 2km di Senopati",
  "user_lat": -6.244098,
  "user_lng": 106.800644
}
```

- `prompt` wajib berisi teks minimal 3 karakter.
- `user_lat` dan `user_lng` opsional, namun bila tersedia hasil directions akan lebih akurat.

## Menampilkan Hasil di UI

- Gunakan `response.embed_url` untuk membuat iframe:
  ```html
  <iframe src="{{ response.embed_url }}" width="600" height="450" style="border:0;" allowfullscreen></iframe>
  ```
- Tampilkan tombol/tautan menuju `response.directions_url` agar pengguna bisa membuka Google Maps
  langsung dengan rute yang sudah diisi.
- Daftar `response.places` memuat maksimal 5 tempat. Masing-masing memuat `name`, `address`, dan
  `maps_url` untuk fallback jika iframe tidak tersedia.

## Error Handling

- HTTP 429 → pengguna melewati rate limit. Tampilkan pesan agar mencoba lagi nanti.
- HTTP 502 (`maps_api_error`) → backend gagal menghubungi Google Maps. Cek kuota & API key.
- HTTP 500 (`internal_error`) → log backend untuk detail. Biasanya disebabkan konfigurasi salah.

Panduan ini memastikan integrasi ke Open WebUI dapat dilakukan dengan cepat oleh tim HR/penguji.