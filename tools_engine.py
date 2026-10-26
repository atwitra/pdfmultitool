import os
import io
import re
from typing import List, Tuple, Optional, Any
from pypdf import PdfReader, PdfWriter
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color


class PDFToolsEngine:
    """
    Kumpulan mesin utilitas PDF offline lengkap setara iLovePDF:
    - Merge PDF
    - Split PDF / Extract Pages
    - Remove Pages
    - Rotate PDF
    - Images to PDF
    - PDF to Images / Markdown
    - Protect & Unlock PDF
    - Add Watermark
    - Add Page Numbers
    - Compress PDF
    """

    @staticmethod
    def get_pdf_info(file_path: str) -> dict:
        reader = PdfReader(file_path)
        return {
            "total_pages": len(reader.pages),
            "size_kb": os.path.getsize(file_path) / 1024,
            "filename": os.path.basename(file_path)
        }

    @staticmethod
    def render_page_thumbnail(file_path: str, page_number_1based: int, max_size=(160, 220), scale: float = 0.35) -> Optional[Image.Image]:
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_path)
            idx = page_number_1based - 1
            if 0 <= idx < len(pdf):
                page = pdf[idx]
                pil_img = page.render(scale=scale).to_pil()
                if max_size:
                    pil_img.thumbnail(max_size, Image.Resampling.LANCZOS)
                return pil_img
        except Exception as e:
            print("Thumbnail error:", e)
        return None

    @staticmethod
    def split_pdf_bundles(file_path: str, output_dir: str, ranges: List[Any], merge_all_ranges: bool = False, custom_names: Optional[List[str]] = None, progress_callback=None) -> List[str]:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        created_files = []

        # Normalisasi list halaman untuk setiap bundle
        bundle_page_lists: List[List[int]] = []
        for r in ranges:
            if isinstance(r, (tuple, list)) and len(r) == 2 and isinstance(r[0], int) and isinstance(r[1], int) and not isinstance(r, set):
                s, e = r[0], r[1]
                if s > e:
                    s, e = e, s
                bundle_page_lists.append([p for p in range(s, e + 1) if 1 <= p <= total_pages])
            else:
                bundle_page_lists.append(sorted([p for p in r if 1 <= p <= total_pages]))

        if merge_all_ranges:
            writer = PdfWriter()
            for page_list in bundle_page_lists:
                for p in page_list:
                    writer.add_page(reader.pages[p - 1])
            out_file = os.path.join(output_dir, f"{base_name}_merged_bundles.pdf")
            with open(out_file, "wb") as f:
                writer.write(f)
            created_files.append(out_file)
            if progress_callback:
                progress_callback(1, 1, os.path.basename(out_file))
        else:
            total_bundles = len(bundle_page_lists)
            for b_idx, page_list in enumerate(bundle_page_lists, start=1):
                if not page_list:
                    continue
                writer = PdfWriter()
                for p in page_list:
                    writer.add_page(reader.pages[p - 1])

                custom_name = custom_names[b_idx - 1] if custom_names and len(custom_names) >= b_idx and custom_names[b_idx - 1] else None
                if custom_name:
                    if not custom_name.lower().endswith(".pdf"):
                        custom_name += ".pdf"
                    file_name = custom_name
                else:
                    if len(page_list) > 1 and page_list[-1] - page_list[0] + 1 == len(page_list):
                        p_str = f"{page_list[0]}-{page_list[-1]}"
                    else:
                        p_str = "_".join(str(p) for p in page_list[:6])
                        if len(page_list) > 6:
                            p_str += f"_plus{len(page_list)-6}"
                    file_name = f"{base_name}_bundle_{b_idx}_hal_{p_str}.pdf"

                out_file = os.path.join(output_dir, file_name)
                with open(out_file, "wb") as f:
                    writer.write(f)
                created_files.append(out_file)
                if progress_callback:
                    progress_callback(b_idx, total_bundles, file_name)

        return created_files

    @staticmethod
    def parse_page_range(range_str: str, max_pages: int) -> List[int]:
        """
        Mengurai string halaman seperti '1, 3-5, 8' menjadi index 0-based.
        Contoh: '1, 3-5' -> [0, 2, 3, 4]
        """
        pages = set()
        parts = [p.strip() for p in range_str.split(",") if p.strip()]
        for part in parts:
            if "-" in part:
                sub = part.split("-")
                start = int(sub[0].strip())
                end = int(sub[1].strip())
                for p in range(start, end + 1):
                    if 1 <= p <= max_pages:
                        pages.add(p - 1)
            else:
                p = int(part)
                if 1 <= p <= max_pages:
                    pages.add(p - 1)
        return sorted(list(pages))

    # ================= 1. GABUNG PDF (MERGE) =================
    @staticmethod
    def merge_pdfs(file_paths: List[str], output_path: str, progress_callback=None) -> str:
        writer = PdfWriter()
        total_files = len(file_paths)

        for idx, file_path in enumerate(file_paths, start=1):
            reader = PdfReader(file_path)
            for page in reader.pages:
                writer.add_page(page)
            if progress_callback:
                progress_callback(idx, total_files, os.path.basename(file_path))

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 2. PISAHKAN PDF (SPLIT / EXTRACT) =================
    @staticmethod
    def split_pdf(file_path: str, output_dir: str, split_mode: str = "all", range_str: str = "", progress_callback=None) -> List[str]:
        """
        split_mode:
        - 'all': Setiap halaman dipisah jadi file PDF terpisah.
        - 'range': Mengekstrak rentang halaman tertentu (misal: '1-3, 5').
        """
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        created_files = []

        if split_mode == "all":
            for idx, page in enumerate(reader.pages, start=1):
                writer = PdfWriter()
                writer.add_page(page)
                out_file = os.path.join(output_dir, f"{base_name}_hal_{idx:03d}.pdf")
                with open(out_file, "wb") as f:
                    writer.write(f)
                created_files.append(out_file)
                if progress_callback:
                    progress_callback(idx, total_pages, f"Halaman {idx}")
        else:
            page_indices = PDFToolsEngine.parse_page_range(range_str, total_pages)
            if not page_indices:
                raise ValueError("Rentang halaman tidak valid!")

            writer = PdfWriter()
            for idx in page_indices:
                writer.add_page(reader.pages[idx])

            out_file = os.path.join(output_dir, f"{base_name}_extracted.pdf")
            with open(out_file, "wb") as f:
                writer.write(f)
            created_files.append(out_file)

        return created_files

    # ================= 3. HAPUS HALAMAN (REMOVE PAGES) =================
    @staticmethod
    def remove_pages(file_path: str, pages_to_remove_str: str, output_path: str) -> str:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        remove_indices = set(PDFToolsEngine.parse_page_range(pages_to_remove_str, total_pages))

        writer = PdfWriter()
        kept = 0
        for idx, page in enumerate(reader.pages):
            if idx not in remove_indices:
                writer.add_page(page)
                kept += 1

        if kept == 0:
            raise ValueError("Tidak dapat menghapus seluruh halaman dokumen!")

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 4. PUTAR PDF (ROTATE) =================
    @staticmethod
    def rotate_pdf(file_path: str, angle: int, output_path: str, pages_str: Optional[str] = None) -> str:
        """
        angle: 90, 180, atau 270 (searah jarum jam).
        """
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        target_indices = None
        if pages_str and pages_str.strip():
            target_indices = set(PDFToolsEngine.parse_page_range(pages_str, total_pages))

        writer = PdfWriter()
        for idx, page in enumerate(reader.pages):
            if target_indices is None or idx in target_indices:
                page.rotate(angle)
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 5. GAMBAR KE PDF (JPG/PNG TO PDF) =================
    @staticmethod
    def images_to_pdf(image_paths: List[str], output_path: str, progress_callback=None) -> str:
        if not image_paths:
            raise ValueError("Tidak ada gambar yang dipilih!")

        pil_images = []
        total = len(image_paths)

        for idx, img_path in enumerate(image_paths, start=1):
            im = Image.open(img_path)
            # Pastikan mode RGB (bukan RGBA atau Palette)
            if im.mode != "RGB":
                im = im.convert("RGB")
            pil_images.append(im)
            if progress_callback:
                progress_callback(idx, total, os.path.basename(img_path))

        first_img = pil_images[0]
        other_imgs = pil_images[1:] if len(pil_images) > 1 else []

        first_img.save(output_path, "PDF", resolution=100.0, save_all=True, append_images=other_imgs)
        return output_path

    # ================= 6. PDF KE MARKDOWN / TEKS =================
    @staticmethod
    def pdf_to_markdown(file_path: str, output_path: str) -> str:
        reader = PdfReader(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]

        md_content = [f"# Dokumen: {base_name}\n\n", f"*Total Halaman: {len(reader.pages)}*\n\n---\n\n"]

        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            md_content.append(f"## Halaman {idx}\n\n")
            md_content.append(text.strip() + "\n\n---\n\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(md_content)
        return output_path

    # ================= 7. KUNCI / PROTECT PASSWORD =================
    @staticmethod
    def protect_pdf(file_path: str, user_pwd: str, output_path: str, owner_pwd: Optional[str] = None) -> str:
        reader = PdfReader(file_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(user_password=user_pwd, owner_password=owner_pwd or user_pwd)
        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 8. BUKA / UNLOCK PASSWORD =================
    @staticmethod
    def unlock_pdf(file_path: str, password: str, output_path: str) -> str:
        reader = PdfReader(file_path)
        if reader.is_encrypted:
            result = reader.decrypt(password)
            if result == 0:
                raise ValueError("Password salah! Dokumen tidak dapat dibuka.")

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 9. TAMBAH WATERMARK TEKS =================
    @staticmethod
    def add_watermark(file_path: str, watermark_text: str, output_path: str, opacity: float = 0.25, font_size: int = 42) -> str:
        reader = PdfReader(file_path)
        writer = PdfWriter()

        for page in reader.pages:
            page_box = page.mediabox
            width = float(page_box.width)
            height = float(page_box.height)

            # Buat overlay watermark menggunakan ReportLab di memori
            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(width, height))
            can.setFont("Helvetica-Bold", font_size)
            can.setFillColor(Color(0.5, 0.5, 0.5, alpha=opacity))

            # Hitung posisi tengah dan rotasi 45 derajat
            can.saveState()
            can.translate(width / 2.0, height / 2.0)
            can.rotate(45)
            can.drawCentredString(0, 0, watermark_text)
            can.restoreState()
            can.save()

            packet.seek(0)
            watermark_pdf = PdfReader(packet)
            watermark_page = watermark_pdf.pages[0]

            page.merge_page(watermark_page)
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 10. TAMBAH NOMOR HALAMAN =================
    @staticmethod
    def add_page_numbers(file_path: str, output_path: str, format_str: str = "Halaman {n} dari {total}", font_size: int = 10) -> str:
        reader = PdfReader(file_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)

        for idx, page in enumerate(reader.pages, start=1):
            page_box = page.mediabox
            width = float(page_box.width)
            height = float(page_box.height)

            text = format_str.replace("{n}", str(idx)).replace("{total}", str(total_pages))

            packet = io.BytesIO()
            can = canvas.Canvas(packet, pagesize=(width, height))
            can.setFont("Helvetica", font_size)
            can.setFillColor(Color(0.2, 0.2, 0.2, alpha=0.9))

            # Posisi: Bawah tengah, margin 25pt
            can.drawCentredString(width / 2.0, 25, text)
            can.save()

            packet.seek(0)
            num_pdf = PdfReader(packet)
            num_page = num_pdf.pages[0]

            page.merge_page(num_page)
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)
        return output_path

    # ================= 11. COMPRESS PDF =================
    @staticmethod
    def compress_pdf(file_path: str, output_path: str) -> Tuple[int, int, float]:
        """
        Kompresi PDF lossless & stream pengurangan ukuran.
        Mengembalikan (original_bytes, new_bytes, saving_pct).
        """
        orig_size = os.path.getsize(file_path)
        reader = PdfReader(file_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        for page in writer.pages:
            page.compress_content_streams()

        writer.add_metadata(reader.metadata or {})

        with open(output_path, "wb") as f:
            writer.write(f)

        new_size = os.path.getsize(output_path)
        pct = max(0.0, (orig_size - new_size) / orig_size * 100.0) if orig_size > 0 else 0.0
        return orig_size, new_size, pct
