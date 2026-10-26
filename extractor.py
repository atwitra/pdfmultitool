import os
import re
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pypdf import PdfReader


def sanitize_filename(name: str) -> str:
    """Membersihkan karakter yang dilarang pada sistem file Windows."""
    # Dilarang: \ / : * ? " < > |
    cleaned = re.sub(r'[\/\\:*?"<>|]', '', name)
    # Hapus spasi berlebih dan titik di akhir nama file
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().rstrip('.')
    return cleaned


class PDFExtractor:
    def __init__(self):
        self.history_file = "rename_history.json"

    def extract_fields_from_pdf(self, file_path: str, custom_keyword: Optional[str] = None, regex_pattern: Optional[str] = None) -> Dict[str, str]:
        """
        Membaca halaman pertama/seluruh dokumen PDF dan mengekstrak field:
        nama, kelas, nisn, sekolah, nomor_urut, dll.
        """
        data = {
            "nama": "",
            "kelas": "",
            "nisn": "",
            "sekolah": "",
            "custom": "",
            "nomor_urut": ""
        }
        
        # Ekstrak nomor urut dari nama file lama jika ada (misal: XII J-1 -> 1, atau 01 -> 1)
        base_name = os.path.basename(file_path)
        m_num = re.search(r'[-_\s](\d+)\.pdf$', base_name, re.IGNORECASE) or re.search(r'^(\d+)[-_\s]', base_name)
        if m_num:
            data["nomor_urut"] = m_num.group(1).zfill(2)

        try:
            reader = PdfReader(file_path)
            if len(reader.pages) == 0:
                return data
            
            # Ambil teks dari halaman pertama (biasanya data identitas ada di hal 1)
            text = reader.pages[0].extract_text() or ""
            
            # Jika ada regex kustom
            if regex_pattern:
                m_custom = re.search(regex_pattern, text)
                if m_custom:
                    data["custom"] = m_custom.group(1).strip() if m_custom.groups() else m_custom.group(0).strip()

            # Jika ada kata kunci kustom (misal "Nomor:", "Invoice:", "Kepada:")
            if custom_keyword:
                kw_escaped = re.escape(custom_keyword.rstrip(':'))
                pattern = rf"{kw_escaped}\s*[:\-]?\s*([^\n\r]+)"
                m_kw = re.search(pattern, text, re.IGNORECASE)
                if m_kw:
                    data["custom"] = m_kw.group(1).strip()

            # Ekstraksi otomatis standar:
            # 1. Nama
            m_nama = re.search(r'Nama(?:\s+Lengkap)?\s*\n?\s*:\s*([^\n\r]+)', text, re.IGNORECASE)
            if m_nama:
                data["nama"] = m_nama.group(1).strip()
            
            # 2. Kelas
            m_kelas = re.search(r'Kelas\s*\n?\s*:\s*([^\n\r]+)', text, re.IGNORECASE)
            if m_kelas:
                data["kelas"] = m_kelas.group(1).strip()

            # 3. NIS / NISN
            m_nisn = re.search(r'NIS(?:N)?\s*(?:/\s*NISN)?\s*\n?\s*:\s*([^\n\r]+)', text, re.IGNORECASE)
            if m_nisn:
                data["nisn"] = m_nisn.group(1).strip()

            # 4. Nama Sekolah / Lembaga
            m_sekolah = re.search(r'Nama\s+Sekolah\s*\n?\s*:\s*([^\n\r]+)', text, re.IGNORECASE)
            if m_sekolah:
                data["sekolah"] = m_sekolah.group(1).strip()

        except Exception as e:
            data["error"] = str(e)

        return data

    def build_new_filename(self, template: str, old_filename: str, fields: Dict[str, str], index: int = 1) -> str:
        """
        Menyusun nama file baru berdasarkan template format.
        Contoh template:
        - "{nama}.pdf"
        - "{nomor_urut} - {nama}.pdf"
        - "{kelas} - {nama}.pdf"
        - "{custom}.pdf"
        """
        filename_without_ext = os.path.splitext(old_filename)[0]
        
        # Fallback values
        nama = fields.get("nama") or fields.get("custom") or filename_without_ext
        kelas = fields.get("kelas") or ""
        nisn = fields.get("nisn") or ""
        sekolah = fields.get("sekolah") or ""
        nomor_urut = fields.get("nomor_urut") or str(index).zfill(2)
        custom = fields.get("custom") or ""
        
        # Replace template placeholders
        result = template
        result = result.replace("{nama}", sanitize_filename(nama))
        result = result.replace("{kelas}", sanitize_filename(kelas))
        result = result.replace("{nisn}", sanitize_filename(nisn))
        result = result.replace("{sekolah}", sanitize_filename(sekolah))
        result = result.replace("{nomor_urut}", sanitize_filename(nomor_urut))
        result = result.replace("{custom}", sanitize_filename(custom))
        result = result.replace("{nama_asli}", sanitize_filename(filename_without_ext))
        
        # Pastikan berakhiran .pdf
        if not result.lower().endswith(".pdf"):
            result += ".pdf"

        # Bersihkan karakter terlarang sekali lagi
        base = os.path.splitext(result)[0]
        ext = os.path.splitext(result)[1]
        clean_base = sanitize_filename(base)
        
        if not clean_base:
            clean_base = f"Dokumen_{index}"
            
        return clean_base + ext

    def scan_folder(self, folder_path: str, template: str, custom_keyword: Optional[str] = None, regex_pattern: Optional[str] = None, progress_callback=None) -> List[Dict]:
        """
        Scan seluruh file PDF di folder dan menghasilkan daftar mapping preview.
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError("Folder tidak ditemukan")

        all_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
        
        # Urutkan berdasarkan angka jika ada
        def sort_key(f):
            m = re.search(r'(\d+)\.pdf$', f, re.IGNORECASE)
            return int(m.group(1)) if m else f
        
        try:
            all_files.sort(key=sort_key)
        except Exception:
            all_files.sort()

        results = []
        seen_names = {}
        total = len(all_files)

        for idx, filename in enumerate(all_files, start=1):
            file_path = os.path.join(folder_path, filename)
            fields = self.extract_fields_from_pdf(file_path, custom_keyword, regex_pattern)
            
            raw_new_name = self.build_new_filename(template, filename, fields, index=idx)
            
            # Cek status
            detected_label = fields.get("custom") or fields.get("nama") or "(Tidak terdeteksi)"
            status = "Siap"
            if not fields.get("nama") and not fields.get("custom"):
                status = "Data Kosong"

            # Tangani duplikat
            base, ext = os.path.splitext(raw_new_name)
            if raw_new_name in seen_names:
                seen_names[raw_new_name] += 1
                final_new_name = f"{base} ({seen_names[raw_new_name]}){ext}"
                status = "Duplikat (Diberi Nomor)"
            else:
                seen_names[raw_new_name] = 1
                final_new_name = raw_new_name

            item = {
                "no": idx,
                "old_name": filename,
                "detected": detected_label,
                "fields": fields,
                "new_name": final_new_name,
                "status": status,
                "full_path": file_path
            }
            results.append(item)

            if progress_callback:
                progress_callback(idx, total, filename)

        return results

    def execute_rename(self, folder_path: str, items: List[Dict], progress_callback=None) -> Tuple[int, int, List[str]]:
        """
        Menjalankan proses rename file dan menyimpan history untuk fitur Undo.
        """
        success_count = 0
        fail_count = 0
        errors = []
        history_records = []

        total = len(items)
        for idx, item in enumerate(items, start=1):
            old_path = os.path.join(folder_path, item["old_name"])
            new_path = os.path.join(folder_path, item["new_name"])

            if old_path == new_path:
                success_count += 1
                continue

            try:
                # Jika target sudah ada dan bukan file yang sama
                if os.path.exists(new_path):
                    # Ubah nama target sementara jika tabrakan
                    raise FileExistsError(f"File dengan nama '{item['new_name']}' sudah ada di folder.")

                os.rename(old_path, new_path)
                success_count += 1
                history_records.append({
                    "old_name": item["old_name"],
                    "new_name": item["new_name"],
                    "old_path": old_path,
                    "new_path": new_path
                })
            except Exception as e:
                fail_count += 1
                errors.append(f"{item['old_name']}: {str(e)}")

            if progress_callback:
                progress_callback(idx, total, item["new_name"])

        # Simpan ke file history untuk Undo
        if history_records:
            history_data = {
                "timestamp": datetime.now().isoformat(),
                "folder": folder_path,
                "records": history_records
            }
            try:
                with open(os.path.join(folder_path, self.history_file), "w", encoding="utf-8") as f:
                    json.dump(history_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return success_count, fail_count, errors

    def undo_last_rename(self, folder_path: str) -> Tuple[int, int, str]:
        """
        Mengembalikan nama file ke nama sebelumnya berdasarkan file history.
        """
        hist_path = os.path.join(folder_path, self.history_file)
        if not os.path.exists(hist_path):
            return 0, 0, "File riwayat rename (rename_history.json) tidak ditemukan di folder ini."

        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)

            records = history_data.get("records", [])
            success = 0
            fails = 0

            for rec in records:
                current_path = rec["new_path"]
                original_path = rec["old_path"]

                if os.path.exists(current_path):
                    try:
                        os.rename(current_path, original_path)
                        success += 1
                    except Exception:
                        fails += 1
                else:
                    fails += 1

            # Hapus file history jika selesai
            os.remove(hist_path)
            return success, fails, f"Berhasil mengembalikan {success} file."
        except Exception as e:
            return 0, 0, f"Gagal membaca history: {str(e)}"
