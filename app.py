import os
import sys
import ctypes
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Dict, Optional, Tuple, Set, Any
import customtkinter as ctk
from PIL import Image

from extractor import PDFExtractor, sanitize_filename
from tools_engine import PDFToolsEngine

# Set Explicit AppUserModelID di Windows agar taskbar menampilkan icon aplikasi, bukan icon Python
if sys.platform.startswith("win"):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("andre.smartpdfsuite.app.1.0")
    except Exception:
        pass


def get_resource_path(relative_path: str) -> str:
    """Mendapatkan path absolut ke resource, kompatibel dengan mode dev maupun PyInstaller bundle."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


# Konfigurasi Tampilan
ctk.set_appearance_mode("System")  # "Dark", "Light", atau "System"
ctk.set_default_color_theme("blue")


# ================= MODAL PRATINJAU DETAIL HALAMAN (ZOOM WINDOW) =================
class PageZoomModal(ctk.CTkToplevel):
    def __init__(self, parent, file_path: str, page_num: int, total_pages: int):
        super().__init__(parent)
        self.file_path = file_path
        self.current_page = page_num
        self.total_pages = total_pages
        self.scale = 1.3

        self.title(f"🔍 Pratinjau Detail: Halaman {self.current_page} dari {self.total_pages}")
        self.geometry("880x920")
        self.minsize(720, 720)

        # Center on parent
        self.transient(parent)
        self.after(100, self.lift)
        try:
            ico_file = get_resource_path("icon.ico")
            if os.path.exists(ico_file):
                self.after(150, lambda: self.iconbitmap(ico_file))
        except Exception:
            pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header Bar
        header = ctk.CTkFrame(self, corner_radius=8, fg_color=("gray90", "gray17"))
        header.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # Prev / Next Nav
        nav_box = ctk.CTkFrame(header, fg_color="transparent")
        nav_box.grid(row=0, column=0, padx=10, pady=8, sticky="w")

        self.prev_btn = ctk.CTkButton(nav_box, text="◀ Sebelumnya", width=110, height=32, command=self._prev_page)
        self.prev_btn.pack(side="left", padx=2)

        self.page_lbl = ctk.CTkLabel(nav_box, text=f"Halaman {self.current_page} / {self.total_pages}", font=ctk.CTkFont(size=14, weight="bold"))
        self.page_lbl.pack(side="left", padx=14)

        self.next_btn = ctk.CTkButton(nav_box, text="Berikutnya ▶", width=110, height=32, command=self._next_page)
        self.next_btn.pack(side="left", padx=2)

        # Zoom Controls
        zoom_box = ctk.CTkFrame(header, fg_color="transparent")
        zoom_box.grid(row=0, column=2, padx=10, pady=8, sticky="e")

        ctk.CTkButton(zoom_box, text="🔍-", width=38, height=32, command=self._zoom_out).pack(side="left", padx=2)
        self.zoom_lbl = ctk.CTkLabel(zoom_box, text="130%", width=50, font=ctk.CTkFont(weight="bold"))
        self.zoom_lbl.pack(side="left", padx=2)
        ctk.CTkButton(zoom_box, text="🔍+", width=38, height=32, command=self._zoom_in).pack(side="left", padx=2)

        close_btn = ctk.CTkButton(zoom_box, text="✕ Tutup", width=75, height=32, fg_color=("gray75", "gray30"), text_color=("black", "white"), command=self.destroy)
        close_btn.pack(side="left", padx=(10, 0))

        # Scrollable Viewport
        self.scroll_frame = ctk.CTkScrollableFrame(self, corner_radius=8, fg_color=("gray95", "gray14"))
        self.scroll_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        self.img_label = ctk.CTkLabel(self.scroll_frame, text="")
        self.img_label.pack(expand=True, pady=12)

        # Keyboard Navigation
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Left>", lambda e: self._prev_page())
        self.bind("<Right>", lambda e: self._next_page())

        self._render_page()

    def _render_page(self):
        self.page_lbl.configure(text=f"Halaman {self.current_page} / {self.total_pages}")
        self.prev_btn.configure(state="normal" if self.current_page > 1 else "disabled")
        self.next_btn.configure(state="normal" if self.current_page < self.total_pages else "disabled")
        self.zoom_lbl.configure(text=f"{int(self.scale * 100)}%")

        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(self.file_path)
            idx = self.current_page - 1
            if 0 <= idx < len(pdf):
                page = pdf[idx]
                pil_img = page.render(scale=self.scale).to_pil()
                ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                self.img_label.configure(image=ctk_img, text="")
        except Exception as e:
            self.img_label.configure(image=None, text=f"Gagal memuat halaman: {str(e)}")

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._render_page()

    def _next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._render_page()

    def _zoom_in(self):
        if self.scale < 2.5:
            self.scale = round(self.scale + 0.25, 2)
            self._render_page()

    def _zoom_out(self):
        if self.scale > 0.75:
            self.scale = round(self.scale - 0.25, 2)
            self._render_page()


class SmartPDFSuiteApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Smart PDF Suite - All-in-One Offline PDF Tools")
        self.geometry("1200x800")
        self.minsize(1040, 700)

        # Pasang Icon Aplikasi pada Window & Taskbar
        self._set_app_icon()

        # Engine
        self.extractor = PDFExtractor()
        self.tools = PDFToolsEngine()
        self.scanned_items = []
        self.current_folder = ""

        # Cache Thumbnail
        self.thumb_cache: Dict[str, Optional[ctk.CTkImage]] = {}

        # State Split Bundle & Visual (Accumulated Grouped Space - Exact Click Order)
        self.split_current_file = ""
        self.split_total_pages = 0
        self.bundle_groups: List[Dict[str, Any]] = []  # List of {"id": int, "name": str, "pages": List[int]}
        self.active_bundle_idx: int = 0
        self.selected_pages: Set[int] = set()

        # Caches & Persistent Views (Zero-Blink & 0ms Submenu Switch)
        self.cached_page_cards: Dict[int, ctk.CTkFrame] = {}
        self.cached_page_card_labels: Dict[int, ctk.CTkLabel] = {}
        self.cached_card_bundled: Dict[int, bool] = {}
        self.card_current_grid: Dict[int, Tuple[int, int]] = {}
        self.visual_grid_frame: Optional[ctk.CTkFrame] = None

        # Persistent visual banners (No destruction!)
        self.visual_banner_all: Optional[ctk.CTkFrame] = None
        self.visual_banner_pages: Optional[ctk.CTkFrame] = None
        self.visual_banner_empty_bundle: Optional[ctk.CTkFrame] = None
        self.visual_banner_loose: Optional[Dict[str, Any]] = None
        self.bundle_banners_cache: List[Dict[str, Any]] = []
        self.banner_current_grid: Dict[int, int] = {}
        self.loose_banner_grid: Optional[int] = None

        # Persistent sidebar containers (0ms instant switching, no destruction!)
        self.sidebar_frame_custom: Optional[ctk.CTkFrame] = None
        self.sidebar_frame_pages: Optional[ctk.CTkFrame] = None
        self.sidebar_frame_all: Optional[ctk.CTkFrame] = None
        self.sidebar_bundle_cards_cache: List[Dict[str, Any]] = []
        self.sidebar_empty_bundle_card: Optional[ctk.CTkFrame] = None
        self.sidebar_bundle_cards_container: Optional[ctk.CTkFrame] = None
        self.sel_pages_lbl = None

        # Layout Utama
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_tabview()

    def _set_app_icon(self):
        """Memasang icon aplikasi pada titlebar dan taskbar."""
        try:
            ico_file = get_resource_path("icon.ico")
            if os.path.exists(ico_file):
                self.iconbitmap(ico_file)
        except Exception:
            pass
        try:
            png_file = get_resource_path("icon.png")
            if os.path.exists(png_file):
                self._app_icon_photo = tk.PhotoImage(file=png_file)
                self.iconphoto(False, self._app_icon_photo)
        except Exception:
            pass

    # ================= HEADER =================
    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "gray17"))
        header_frame.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        # Logo Brand Header
        try:
            logo_png = get_resource_path("icon.png")
            if os.path.exists(logo_png):
                pil_logo = Image.open(logo_png)
                self.header_brand_logo = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(42, 42))
                logo_lbl = ctk.CTkLabel(title_box, image=self.header_brand_logo, text="")
                logo_lbl.pack(side="left", padx=(0, 12))
        except Exception:
            pass

        text_box = ctk.CTkFrame(title_box, fg_color="transparent")
        text_box.pack(side="left")

        title_lbl = ctk.CTkLabel(
            text_box,
            text="Smart PDF Suite",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            text_box,
            text="Smart Renamer, Interactive Split, Watermark & More. by Atwitraaa",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=("gray40", "gray60")
        )
        subtitle_lbl.pack(anchor="w")

        # Theme Switcher
        theme_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_box.grid(row=0, column=1, padx=16, pady=8, sticky="e")

        theme_lbl = ctk.CTkLabel(theme_box, text="Tema:", font=ctk.CTkFont(size=12))
        theme_lbl.pack(side="left", padx=(0, 6))

        self.theme_menu = ctk.CTkOptionMenu(
            theme_box,
            values=["System", "Dark", "Light"],
            command=self._change_theme,
            width=100
        )
        self.theme_menu.set("System")
        self.theme_menu.pack(side="left")

    # ================= TABVIEW UTAMA =================
    def _build_tabview(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")

        tab_renamer = self.tabview.add("🏷️ Smart Renamer")
        tab_split = self.tabview.add("✂️ Split & Bundle (Visual)")
        tab_merge = self.tabview.add("📑 Gabung PDF (Merge)")
        tab_pages = self.tabview.add("🗑️ Halaman & Rotasi")
        tab_convert = self.tabview.add("🔄 Konversi & Kompresi")
        tab_security = self.tabview.add("🛡️ Keamanan & Watermark")

        self._build_renamer_tab(tab_renamer)
        self._build_split_visual_tab(tab_split)
        self._build_merge_tab(tab_merge)
        self._build_pages_rotate_tab(tab_pages)
        self._build_convert_compress_tab(tab_convert)
        self._build_security_tab(tab_security)

    # ================= THUMBNAIL HELPER =================
    def _get_thumbnail(self, file_path: str, page_num: int, max_size=(120, 165)) -> Optional[ctk.CTkImage]:
        key = f"{file_path}_{page_num}_{max_size}"
        if key not in self.thumb_cache:
            pil_img = PDFToolsEngine.render_page_thumbnail(file_path, page_num, max_size=max_size)
            if pil_img:
                self.thumb_cache[key] = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            else:
                self.thumb_cache[key] = None
        return self.thumb_cache[key]

    def _open_page_zoom_modal(self, page_num: int):
        if not self.split_current_file or not os.path.exists(self.split_current_file):
            return
        PageZoomModal(self, self.split_current_file, page_num, self.split_total_pages)

    # ================= TAB 1: SMART RENAMER =================
    def _build_renamer_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        # Folder Picker
        top_frame = ctk.CTkFrame(parent, corner_radius=8)
        top_frame.grid(row=0, column=0, padx=8, pady=6, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        f_lbl = ctk.CTkLabel(top_frame, text="Folder PDF:", font=ctk.CTkFont(weight="bold"))
        f_lbl.grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")

        self.folder_entry = ctk.CTkEntry(top_frame, placeholder_text="Pilih folder yang berisi berkas PDF...", height=32)
        self.folder_entry.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        b_btn = ctk.CTkButton(top_frame, text="📂 Cari Folder", width=120, height=32, command=self._browse_folder)
        b_btn.grid(row=0, column=2, padx=4, pady=8)

        op_btn = ctk.CTkButton(top_frame, text="📁 Explorer", width=95, height=32, fg_color="transparent", border_width=1, command=self._open_in_explorer)
        op_btn.grid(row=0, column=3, padx=(4, 12), pady=8)

        # Aturan & Template
        rule_frame = ctk.CTkFrame(parent, corner_radius=8, fg_color=("gray95", "gray14"))
        rule_frame.grid(row=1, column=0, padx=8, pady=4, sticky="ew")
        rule_frame.grid_columnconfigure(1, weight=1)
        rule_frame.grid_columnconfigure(3, weight=1)

        m_lbl = ctk.CTkLabel(rule_frame, text="Mode Ekstraksi:", font=ctk.CTkFont(size=12, weight="bold"))
        m_lbl.grid(row=0, column=0, padx=(12, 6), pady=6, sticky="w")

        self.mode_var = ctk.StringVar(value="Rapor / Nama Siswa")
        self.mode_menu = ctk.CTkOptionMenu(
            rule_frame,
            variable=self.mode_var,
            values=["Rapor / Nama Siswa", "Kata Kunci Kustom", "Regex Lanjutan"],
            command=self._on_mode_change,
            width=160
        )
        self.mode_menu.grid(row=0, column=1, padx=6, pady=6, sticky="w")

        self.custom_entry = ctk.CTkEntry(rule_frame, placeholder_text="Kata kunci (contoh: 'Nomor:' atau 'Kepada:')", width=240, state="disabled")
        self.custom_entry.grid(row=0, column=2, padx=6, pady=6, sticky="w")

        tpl_lbl = ctk.CTkLabel(rule_frame, text="Format Nama:", font=ctk.CTkFont(size=12, weight="bold"))
        tpl_lbl.grid(row=1, column=0, padx=(12, 6), pady=(0, 6), sticky="w")

        self.tpl_var = ctk.StringVar(value="{nama}.pdf")
        self.tpl_entry = ctk.CTkEntry(rule_frame, textvariable=self.tpl_var, placeholder_text="Contoh: {nama}.pdf", width=260)
        self.tpl_entry.grid(row=1, column=1, columnspan=2, padx=6, pady=(0, 6), sticky="ew")

        tags_box = ctk.CTkFrame(rule_frame, fg_color="transparent")
        tags_box.grid(row=1, column=3, padx=10, pady=(0, 6), sticky="e")
        for tag in ["{nama}", "{nomor_urut}", "{kelas}", "{custom}"]:
            btn = ctk.CTkButton(tags_box, text=tag, width=65, height=24, font=ctk.CTkFont(size=11), fg_color=("gray85", "gray22"), text_color=("gray10", "gray90"), command=lambda t=tag: self._insert_tag(t))
            btn.pack(side="left", padx=2)

        # Table Pratinjau
        tbl_container = ctk.CTkFrame(parent, corner_radius=8)
        tbl_container.grid(row=2, column=0, padx=8, pady=6, sticky="nsew")
        tbl_container.grid_columnconfigure(0, weight=1)
        tbl_container.grid_rowconfigure(1, weight=1)

        fbar = ctk.CTkFrame(tbl_container, fg_color="transparent")
        fbar.grid(row=0, column=0, padx=10, pady=(8, 4), sticky="ew")
        fbar.grid_columnconfigure(0, weight=1)

        self.stats_lbl = ctk.CTkLabel(fbar, text="Pratinjau Hasil: 0 berkas", font=ctk.CTkFont(weight="bold"))
        self.stats_lbl.grid(row=0, column=0, sticky="w")

        self.search_entry = ctk.CTkEntry(fbar, placeholder_text="🔍 Cari berkas...", width=200, height=28)
        self.search_entry.grid(row=0, column=1, sticky="e")
        self.search_entry.bind("<KeyRelease>", self._filter_table)

        tw = ctk.CTkFrame(tbl_container, fg_color="transparent")
        tw.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="nsew")
        tw.grid_columnconfigure(0, weight=1)
        tw.grid_rowconfigure(0, weight=1)

        columns = ("no", "old_name", "detected", "new_name", "status")
        self.tree = ttk.Treeview(tw, columns=columns, show="headings", style="Custom.Treeview")
        self.tree.heading("no", text="No")
        self.tree.heading("old_name", text="Nama Berkas Asli")
        self.tree.heading("detected", text="Data Terdeteksi")
        self.tree.heading("new_name", text="Usulan Nama Baru")
        self.tree.heading("status", text="Status")

        self.tree.column("no", width=40, anchor="center")
        self.tree.column("old_name", width=240)
        self.tree.column("detected", width=180)
        self.tree.column("new_name", width=280)
        self.tree.column("status", width=120, anchor="center")

        sy = ttk.Scrollbar(tw, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(tw, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Double-1>", self._on_double_click_cell)

        # Footer Actions
        footer = ctk.CTkFrame(parent, corner_radius=8)
        footer.grid(row=3, column=0, padx=8, pady=(4, 8), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        st_box = ctk.CTkFrame(footer, fg_color="transparent")
        st_box.grid(row=0, column=0, padx=10, pady=8, sticky="ew")
        st_box.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(st_box, text="Siap. Silakan pilih folder dan klik 'Pindai & Pratinjau'.", anchor="w", font=ctk.CTkFont(size=12))
        self.status_lbl.grid(row=0, column=0, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(st_box)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.progress_bar.set(0)

        act_box = ctk.CTkFrame(footer, fg_color="transparent")
        act_box.grid(row=0, column=1, padx=10, pady=8, sticky="e")

        self.undo_btn = ctk.CTkButton(act_box, text="↩️ Undo", width=100, height=34, fg_color=("gray75", "gray25"), text_color=("black", "white"), command=self._undo_rename)
        self.undo_btn.pack(side="left", padx=3)

        self.scan_btn = ctk.CTkButton(act_box, text="🔍 Pindai & Pratinjau", width=150, height=34, fg_color=("#1976D2", "#1565C0"), command=self._start_scan)
        self.scan_btn.pack(side="left", padx=3)

        self.execute_btn = ctk.CTkButton(act_box, text="⚡ Eksekusi Rename", width=150, height=34, fg_color=("#2E7D32", "#1B5E20"), command=self._start_rename)
        self.execute_btn.pack(side="left", padx=3)

    # ================= TAB 2: VISUAL SPLIT & BUNDLE (DENGAN CLICK & ZOOM) =================
    def _build_split_visual_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)  # Visual preview area (Left)
        parent.grid_columnconfigure(1, weight=0, minsize=330)  # Range sidebar (Right fixed width, no resizing!)
        parent.grid_rowconfigure(1, weight=1)

        # Top Bar: File Picker & Info
        top_bar = ctk.CTkFrame(parent, corner_radius=8)
        top_bar.grid(row=0, column=0, columnspan=2, padx=8, pady=(6, 4), sticky="ew")
        top_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top_bar, text="Berkas PDF:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")
        self.split_path_entry = ctk.CTkEntry(top_bar, placeholder_text="Pilih file PDF yang ingin di-split bundle...", height=32)
        self.split_path_entry.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        ctk.CTkButton(top_bar, text="📂 Pilih PDF", width=110, height=32, command=self._browse_split_visual_file).grid(row=0, column=2, padx=4, pady=8)

        self.split_info_lbl = ctk.CTkLabel(top_bar, text="Belum ada file dipilih", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12))
        self.split_info_lbl.grid(row=0, column=3, padx=(6, 14), pady=8)

        # LEFT: Visual Preview Canvas Area
        left_preview_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray14"))
        left_preview_frame.grid(row=1, column=0, padx=(8, 4), pady=4, sticky="nsew")
        left_preview_frame.grid_columnconfigure(0, weight=1)
        left_preview_frame.grid_rowconfigure(1, weight=1)

        # Header Area Visual
        preview_header = ctk.CTkFrame(left_preview_frame, fg_color="transparent")
        preview_header.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")

        ctk.CTkLabel(preview_header, text="🖼️ Pratinjau Visual Halaman", font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        # Scrollable container for visual bundle cards / grid
        self.visual_bundles_container = ctk.CTkScrollableFrame(left_preview_frame, corner_radius=8, fg_color=("white", "gray18"))
        self.visual_bundles_container.grid(row=1, column=0, padx=12, pady=(4, 12), sticky="nsew")
        self.visual_bundles_container.grid_columnconfigure(0, weight=1)

        # Placeholder
        self.visual_placeholder = ctk.CTkLabel(
            self.visual_bundles_container,
            text="Silakan pilih berkas PDF untuk menampilkan pratinjau halaman visual.",
            font=ctk.CTkFont(size=13),
            text_color=("gray50", "gray50")
        )
        self.visual_placeholder.pack(pady=60)

        # RIGHT: Sidebar Controls (Fixed 330px width: zero resizing across submenus!)
        sidebar = ctk.CTkFrame(parent, width=330, corner_radius=10)
        sidebar.grid(row=1, column=1, padx=(4, 8), pady=4, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(sidebar, text="⚙️ Pengaturan Split", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=14, pady=(12, 4), sticky="w")

        # 3 Mode Split Buttons
        mode_btn_frame = ctk.CTkFrame(sidebar, fg_color=("gray85", "gray20"), corner_radius=8)
        mode_btn_frame.grid(row=1, column=0, padx=10, pady=6, sticky="ew")
        mode_btn_frame.grid_columnconfigure(0, weight=1)
        mode_btn_frame.grid_columnconfigure(1, weight=1)
        mode_btn_frame.grid_columnconfigure(2, weight=1)

        self.split_visual_mode_var = ctk.StringVar(value="custom")

        self.btn_mode_custom = ctk.CTkButton(
            mode_btn_frame,
            text="[0-0] Bundle",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#1976D2", "#1565C0"),
            command=lambda: self._set_split_visual_mode("custom")
        )
        self.btn_mode_custom.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        self.btn_mode_click_pages = ctk.CTkButton(
            mode_btn_frame,
            text="☑️ Halaman",
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            command=lambda: self._set_split_visual_mode("pages")
        )
        self.btn_mode_click_pages.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

        self.btn_mode_all = ctk.CTkButton(
            mode_btn_frame,
            text="📄 Semua",
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            text_color=("gray10", "gray90"),
            command=lambda: self._set_split_visual_mode("all")
        )
        self.btn_mode_all.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

        # Dynamic Content Container (Scrollable)
        self.sidebar_content_frame = ctk.CTkScrollableFrame(sidebar, corner_radius=8, fg_color=("gray95", "gray14"))
        self.sidebar_content_frame.grid(row=2, column=0, padx=10, pady=6, sticky="nsew")
        self.sidebar_content_frame.grid_columnconfigure(0, weight=1)

        # 3 Persistent Submenu Views (0ms Instant Switch without widget destruction)
        self.sidebar_frame_custom = ctk.CTkFrame(self.sidebar_content_frame, fg_color="transparent")
        self.sidebar_frame_custom.grid_columnconfigure(0, weight=1)

        self.sidebar_frame_pages = ctk.CTkFrame(self.sidebar_content_frame, fg_color="transparent")
        self.sidebar_frame_pages.grid_columnconfigure(0, weight=1)

        self.sidebar_frame_all = ctk.CTkFrame(self.sidebar_content_frame, fg_color="transparent")
        self.sidebar_frame_all.grid_columnconfigure(0, weight=1)

        self._build_sidebar_custom_subview(self.sidebar_frame_custom)
        self._build_sidebar_pages_subview(self.sidebar_frame_pages)
        self._build_sidebar_all_subview(self.sidebar_frame_all)

        self.sidebar_frame_custom.pack(fill="both", expand=True)

        # Add Range Button (Hanya tampil pada mode custom)
        self.add_range_btn = ctk.CTkButton(
            sidebar,
            text="➕ Tambah Range / Bundle",
            height=34,
            fg_color="transparent",
            border_width=1.5,
            border_color=("#E53935", "#EF5350"),
            text_color=("#E53935", "#EF5350"),
            font=ctk.CTkFont(weight="bold"),
            command=self._add_bundle_group
        )
        self.add_range_btn.grid(row=3, column=0, padx=12, pady=4, sticky="ew")

        # Option: Merge all ranges into 1 PDF
        self.merge_ranges_var = ctk.BooleanVar(value=False)
        self.merge_ranges_cb = ctk.CTkCheckBox(
            sidebar,
            text="Gabungkan hasil jadi 1 file",
            variable=self.merge_ranges_var,
            font=ctk.CTkFont(size=12)
        )
        self.merge_ranges_cb.grid(row=4, column=0, padx=14, pady=(4, 6), sticky="w")

        # Action Button (Red CTA, just like iLovePDF!)
        self.execute_split_btn = ctk.CTkButton(
            sidebar,
            text="⚡ Split PDF Sekarang ➜",
            height=44,
            fg_color=("#E53935", "#D32F2F"),
            hover_color=("#C62828", "#B71C1C"),
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._execute_visual_split_bundles
        )
        self.execute_split_btn.grid(row=5, column=0, padx=12, pady=(4, 14), sticky="ew")

    def _browse_split_visual_file(self):
        path = filedialog.askopenfilename(title="Pilih Berkas PDF untuk Split", filetypes=[("Berkas PDF", "*.pdf")])
        if not path:
            return

        self.split_current_file = os.path.normpath(path)
        self.split_path_entry.delete(0, tk.END)
        self.split_path_entry.insert(0, self.split_current_file)

        try:
            info = self.tools.get_pdf_info(self.split_current_file)
            self.split_total_pages = info["total_pages"]
            self.split_info_lbl.configure(text=f"Total: {self.split_total_pages} Halaman | {info['size_kb']:.1f} KB")

            self.selected_pages.clear()
            self._reset_split_ranges()
        except Exception as e:
            messagebox.showerror("Error Membaca PDF", f"Gagal membaca PDF: {str(e)}")

    # ================= SUBMENU VIEWS (PERSISTENT & 0ms SWITCHING) =================
    def _build_sidebar_custom_subview(self, parent: ctk.CTkFrame):
        self.sidebar_empty_bundle_card = ctk.CTkFrame(parent, corner_radius=8, fg_color=("white", "gray22"))
        ctk.CTkLabel(self.sidebar_empty_bundle_card, text="📦 Belum Ada Bundle", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            self.sidebar_empty_bundle_card,
            text="Seluruh halaman saat ini berstatus lepas.\n\nKlik kartu halaman di sebelah kiri atau klik '+ Tambah Range / Bundle' untuk mulai mengelompokkan halaman menjadi bundle.",
            font=ctk.CTkFont(size=11),
            wraplength=200,
            justify="left",
            text_color=("gray40", "gray60")
        ).pack(anchor="w", padx=10, pady=(2, 8))
        self.sidebar_empty_bundle_card.pack(fill="x", pady=6, padx=2)

        self.sidebar_bundle_cards_container = ctk.CTkFrame(parent, fg_color="transparent")
        self.sidebar_bundle_cards_container.pack(fill="both", expand=True)
        self.sidebar_bundle_cards_cache = []

    def _build_sidebar_pages_subview(self, parent: ctk.CTkFrame):
        info_card = ctk.CTkFrame(parent, corner_radius=8, fg_color=("white", "gray22"))
        info_card.pack(fill="x", pady=4, padx=2)

        ctk.CTkLabel(info_card, text="📄 Halaman Terpilih:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))

        self.sel_pages_lbl = ctk.CTkLabel(
            info_card,
            text="Belum ada halaman dipilih.\nKlik kartu halaman di sebelah kiri.",
            font=ctk.CTkFont(size=11),
            justify="left",
            text_color=("gray50", "gray50")
        )
        self.sel_pages_lbl.pack(anchor="w", padx=10, pady=(2, 8))

        btn_row = ctk.CTkFrame(info_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(btn_row, text="Pilih Semua", width=85, height=26, font=ctk.CTkFont(size=11), command=self._select_all_pages).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="Reset", width=65, height=26, font=ctk.CTkFont(size=11), fg_color="gray40", command=self._clear_selected_pages).pack(side="left", padx=2)

    def _build_sidebar_all_subview(self, parent: ctk.CTkFrame):
        all_card = ctk.CTkFrame(parent, corner_radius=8, fg_color=("white", "gray22"))
        all_card.pack(fill="x", pady=4, padx=2)
        ctk.CTkLabel(all_card, text="Mode Ekstrak Seluruh Halaman", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))
        self.all_mode_desc_lbl = ctk.CTkLabel(
            all_card,
            text="Setiap halaman akan disimpan menjadi berkas PDF mandiri (1 file per halaman).",
            font=ctk.CTkFont(size=11),
            wraplength=200,
            justify="left",
            text_color=("gray40", "gray60")
        )
        self.all_mode_desc_lbl.pack(anchor="w", padx=10, pady=(2, 8))

    def _update_sidebar_custom_view(self):
        if not self.bundle_groups:
            if not self.sidebar_empty_bundle_card.winfo_ismapped():
                self.sidebar_empty_bundle_card.pack(fill="x", pady=6, padx=2)
            for c in self.sidebar_bundle_cards_cache:
                if c["frame"].winfo_ismapped():
                    c["frame"].pack_forget()
            return

        if self.sidebar_empty_bundle_card.winfo_ismapped():
            self.sidebar_empty_bundle_card.pack_forget()

        for idx, b in enumerate(self.bundle_groups):
            is_active = (idx == self.active_bundle_idx)
            b_pages = b["pages"]  # list of pages in exact click order!

            if idx >= len(self.sidebar_bundle_cards_cache):
                card_f = ctk.CTkFrame(self.sidebar_bundle_cards_container, corner_radius=8)
                top_row = ctk.CTkFrame(card_f, fg_color="transparent")
                top_row.pack(fill="x", padx=8, pady=(6, 2))

                title_l = ctk.CTkLabel(top_row, text="", font=ctk.CTkFont(weight="bold", size=12))
                title_l.pack(side="left")

                del_b = ctk.CTkButton(
                    top_row,
                    text="🗑️",
                    width=28,
                    height=24,
                    fg_color="transparent",
                    hover_color=("gray85", "gray30"),
                    text_color="red"
                )
                del_b.pack(side="right")

                info_b = ctk.CTkFrame(card_f, fg_color="transparent")
                info_b.pack(fill="x", padx=8, pady=(0, 6))

                pages_l = ctk.CTkLabel(info_b, text="", font=ctk.CTkFont(size=11), wraplength=190, justify="left")
                pages_l.pack(anchor="w")

                act_b = ctk.CTkButton(
                    info_b,
                    text="Jadikan Target (+)",
                    height=22,
                    font=ctk.CTkFont(size=10),
                    fg_color=("gray85", "gray30"),
                    hover_color=("#1976D2", "#1565C0"),
                    text_color=("gray10", "gray90")
                )
                act_b.pack(anchor="w", pady=(4, 0))

                self.sidebar_bundle_cards_cache.append({
                    "frame": card_f,
                    "title_lbl": title_l,
                    "del_btn": del_b,
                    "pages_lbl": pages_l,
                    "act_btn": act_b,
                    "is_active": None,
                    "cached_pages": None
                })

            item = self.sidebar_bundle_cards_cache[idx]

            # 1. Update active styling only if active state changed!
            if item.get("is_active") != is_active:
                item["frame"].configure(
                    fg_color=("white", "gray22"),
                    border_width=2 if is_active else 1,
                    border_color=("#1976D2", "#1565C0") if is_active else ("gray70", "gray35")
                )
                if is_active:
                    item["act_btn"].pack_forget()
                else:
                    item["act_btn"].configure(command=lambda i=idx: self._set_active_bundle(i))
                    item["act_btn"].pack(anchor="w", pady=(4, 0))
                item["is_active"] = is_active

            # 2. Update title only if text changed
            title_prefix = "🏷️ [AKTIF] " if is_active else "🏷️ "
            new_title = f"{title_prefix}{b['name']} ({len(b_pages)} Hal)"
            if item["title_lbl"].cget("text") != new_title:
                item["title_lbl"].configure(
                    text=new_title,
                    text_color=("#1565C0", "#90CAF9") if is_active else ("gray15", "gray90")
                )

            item["del_btn"].configure(command=lambda i=idx: self._delete_bundle_group(i))

            # 3. Update page list text only if pages list changed
            if item.get("cached_pages") != b_pages:
                if b_pages:
                    pages_str = self._format_page_list(b_pages)
                    item["pages_lbl"].configure(
                        text=f"Urutan: {pages_str}",
                        text_color=("#1976D2", "#42A5F5") if is_active else ("gray40", "gray60")
                    )
                else:
                    item["pages_lbl"].configure(text="Belum ada halaman", text_color=("gray50", "gray50"))
                item["cached_pages"] = list(b_pages)

            if not item["frame"].winfo_ismapped():
                item["frame"].pack(fill="x", pady=4, padx=2)

        for j in range(len(self.bundle_groups), len(self.sidebar_bundle_cards_cache)):
            if self.sidebar_bundle_cards_cache[j]["frame"].winfo_ismapped():
                self.sidebar_bundle_cards_cache[j]["frame"].pack_forget()

    def _reset_split_ranges(self):
        self._reset_bundle_groups()

    def _reset_bundle_groups(self):
        self.bundle_groups.clear()
        self.active_bundle_idx = 0
        self.selected_pages.clear()
        self._init_page_cards_cache()
        self._relayout_visual_grid()
        self._update_sidebar_custom_view()

    def _set_split_visual_mode(self, mode: str):
        self.split_visual_mode_var.set(mode)
        # Style buttons
        self.btn_mode_custom.configure(
            fg_color=("#1976D2", "#1565C0") if mode == "custom" else "transparent",
            text_color="white" if mode == "custom" else ("gray10", "gray90")
        )
        self.btn_mode_click_pages.configure(
            fg_color=("#1976D2", "#1565C0") if mode == "pages" else "transparent",
            text_color="white" if mode == "pages" else ("gray10", "gray90")
        )
        self.btn_mode_all.configure(
            fg_color=("#1976D2", "#1565C0") if mode == "all" else "transparent",
            text_color="white" if mode == "all" else ("gray10", "gray90")
        )

        # 0ms Instant Switch without widget destruction
        self.sidebar_frame_custom.pack_forget()
        self.sidebar_frame_pages.pack_forget()
        self.sidebar_frame_all.pack_forget()

        if mode == "custom":
            self.sidebar_frame_custom.pack(fill="both", expand=True)
            self.add_range_btn.grid()
            self.merge_ranges_cb.grid()
            self.execute_split_btn.configure(text="⚡ Split PDF (Bundle) Sekarang ➜")
        elif mode == "pages":
            self.sidebar_frame_pages.pack(fill="both", expand=True)
            self.add_range_btn.grid_remove()
            self.merge_ranges_cb.grid()
            self.execute_split_btn.configure(text="⚡ Ekstrak Halaman Terpilih ➜")
        else:
            self.sidebar_frame_all.pack(fill="both", expand=True)
            if hasattr(self, "all_mode_desc_lbl") and self.all_mode_desc_lbl:
                self.all_mode_desc_lbl.configure(text=f"Setiap dari total {self.split_total_pages} halaman akan disimpan menjadi berkas PDF mandiri (1 file per halaman).")
            self.add_range_btn.grid_remove()
            self.merge_ranges_cb.grid_remove()
            self.execute_split_btn.configure(text="⚡ Ekstrak Semua Halaman (1 hal = 1 file) ➜")

        self._relayout_visual_grid()
        self._update_sidebar_custom_view()

    def _bind_click_all(self, widget, page_num: int):
        cb = lambda e, p=page_num: self._on_page_clicked(p)
        try:
            widget.bind("<Button-1>", cb)
        except Exception:
            pass
        if hasattr(widget, "_canvas") and widget._canvas:
            try:
                widget._canvas.bind("<Button-1>", cb)
            except Exception:
                pass
        if hasattr(widget, "_label") and widget._label:
            try:
                widget._label.bind("<Button-1>", cb)
            except Exception:
                pass

    def _format_page_list(self, pages: List[int]) -> str:
        if not pages:
            return "Kosong"
        if len(pages) > 10:
            return ", ".join(str(p) for p in pages[:10]) + f" (+{len(pages)-10} lainnya)"
        return ", ".join(str(p) for p in pages)

    def _init_page_cards_cache(self):
        for child in self.visual_bundles_container.winfo_children():
            child.destroy()

        self.cached_page_cards.clear()
        self.cached_page_card_labels.clear()
        self.cached_card_bundled.clear()
        self.card_current_grid.clear()
        self.bundle_banners_cache.clear()
        self.banner_current_grid.clear()
        self.loose_banner_grid = None
        self.visual_banner_all = None
        self.visual_banner_pages = None
        self.visual_banner_empty_bundle = None
        self.visual_banner_loose = None

        if not self.split_current_file or not os.path.exists(self.split_current_file) or self.split_total_pages <= 0:
            lbl = ctk.CTkLabel(self.visual_bundles_container, text="Pilih berkas PDF untuk melihat pratinjau visual halaman.", text_color=("gray50", "gray50"))
            lbl.pack(pady=60)
            self.visual_grid_frame = None
            return

        self.visual_grid_frame = ctk.CTkFrame(self.visual_bundles_container, fg_color="transparent")
        self.visual_grid_frame.pack(fill="both", expand=True, padx=6)
        for c in range(4):
            self.visual_grid_frame.grid_columnconfigure(c, weight=1)

        # Persistent visual banners (No destruction!)
        # 1. All Banner
        b_all = ctk.CTkFrame(self.visual_grid_frame, fg_color="transparent")
        ctk.CTkLabel(b_all, text=f"📄 Memisahkan Seluruh {self.split_total_pages} Halaman (1 Berkas per Halaman):", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.visual_banner_all = b_all

        # 2. Pages Banner
        b_pages = ctk.CTkFrame(self.visual_grid_frame, fg_color="transparent")
        self.grid_header_title = ctk.CTkLabel(b_pages, text=f"Pilih Halaman yang Ingin Diekstrak ({len(self.selected_pages)} Terpilih):", font=ctk.CTkFont(size=13, weight="bold"))
        self.grid_header_title.pack(side="left")
        self.visual_banner_pages = b_pages

        # 3. Empty Bundle Banner
        b_empty = ctk.CTkFrame(self.visual_grid_frame, fg_color="transparent")
        ctk.CTkLabel(b_empty, text=f"📄 Semua Halaman (Total {self.split_total_pages} Halaman)", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(b_empty, text="➕ Buat Bundle Baru", height=28, font=ctk.CTkFont(size=11, weight="bold"), fg_color=("#1976D2", "#1565C0"), command=self._add_bundle_group).pack(side="right")
        self.visual_banner_empty_bundle = b_empty

        # 4. Loose Pages Banner
        b_loose = ctk.CTkFrame(self.visual_grid_frame, corner_radius=10, border_width=1.5, border_color=("gray75", "gray30"), fg_color=("gray95", "gray15"))
        u_bar = ctk.CTkFrame(b_loose, fg_color="transparent")
        u_bar.pack(fill="x", padx=12, pady=8)
        u_title = ctk.CTkLabel(u_bar, text="", font=ctk.CTkFont(size=13, weight="bold"))
        u_title.pack(side="left")
        ctk.CTkButton(u_bar, text="➕ Jadikan Bundle Baru", height=26, font=ctk.CTkFont(size=11), fg_color=("#1976D2", "#1565C0"), command=self._add_bundle_group).pack(side="right")
        self.visual_banner_loose = {"frame": b_loose, "title_lbl": u_title}

        # 36 Card Widgets (Created once, never destroyed!)
        for p in range(1, self.split_total_pages + 1):
            thumb_box = ctk.CTkFrame(
                self.visual_grid_frame,
                corner_radius=8,
                border_width=1,
                border_color=("gray80", "gray30"),
                fg_color=("white", "gray20"),
                cursor="hand2"
            )

            card_top = ctk.CTkFrame(thumb_box, fg_color="transparent", cursor="hand2")
            card_top.pack(fill="x", padx=6, pady=(4, 2))

            hal_lbl = ctk.CTkLabel(
                card_top,
                text=f"Hal {p}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray20", "gray80"),
                cursor="hand2"
            )
            hal_lbl.pack(side="left")

            eye_lbl = ctk.CTkLabel(
                card_top,
                text="👁️",
                font=ctk.CTkFont(size=13),
                text_color=("gray35", "gray65"),
                cursor="hand2"
            )
            eye_lbl.pack(side="right", padx=(0, 2))

            # Direct click on eye to open zoom
            zoom_cmd = lambda e, page=p: self._open_page_zoom_modal(page)
            eye_lbl.bind("<Button-1>", zoom_cmd)
            if hasattr(eye_lbl, "_label") and eye_lbl._label:
                eye_lbl._label.bind("<Button-1>", zoom_cmd)

            # Hover micro-interaction on eye
            def make_eye_hover(lbl):
                def on_enter(e):
                    lbl.configure(text_color=("#1976D2", "#42A5F5"))
                def on_leave(e):
                    lbl.configure(text_color=("gray35", "gray65"))
                lbl.bind("<Enter>", on_enter)
                lbl.bind("<Leave>", on_leave)
                if hasattr(lbl, "_label") and lbl._label:
                    lbl._label.bind("<Enter>", on_enter)
                    lbl._label.bind("<Leave>", on_leave)
            make_eye_hover(eye_lbl)

            img = self._get_thumbnail(self.split_current_file, p, max_size=(105, 145))
            if img:
                img_lbl = ctk.CTkLabel(thumb_box, image=img, text="", cursor="hand2")
                img_lbl.pack(padx=6, pady=(0, 6))
                self._bind_click_all(img_lbl, p)

            self._bind_click_all(thumb_box, p)
            self._bind_click_all(card_top, p)
            self._bind_click_all(hal_lbl, p)

            self.cached_page_cards[p] = thumb_box
            self.cached_page_card_labels[p] = hal_lbl
            self.cached_card_bundled[p] = False

    def _update_card_style(self, page_num: int, is_bundled: bool):
        if page_num not in self.cached_page_cards:
            return
        if self.cached_card_bundled.get(page_num) == is_bundled:
            return
        card = self.cached_page_cards[page_num]
        lbl = self.cached_page_card_labels[page_num]
        if is_bundled:
            card.configure(
                border_width=2,
                border_color=("#1976D2", "#42A5F5"),
                fg_color=("#E3F2FD", "#1E3A5F")
            )
            lbl.configure(
                text=f"✓ Hal {page_num}",
                text_color=("#1565C0", "#90CAF9")
            )
        else:
            card.configure(
                border_width=1,
                border_color=("gray80", "gray30"),
                fg_color=("white", "gray20")
            )
            lbl.configure(
                text=f"Hal {page_num}",
                text_color=("gray20", "gray80")
            )
        self.cached_card_bundled[page_num] = is_bundled

    def _relayout_visual_grid(self):
        if not self.visual_grid_frame or not self.cached_page_cards:
            return

        mode = self.split_visual_mode_var.get()

        if mode == "all":
            if self.visual_banner_all and not self.visual_banner_all.winfo_ismapped():
                self.visual_banner_all.grid(row=0, column=0, columnspan=4, sticky="ew", padx=6, pady=(6, 8))
            if self.visual_banner_pages and self.visual_banner_pages.winfo_ismapped():
                self.visual_banner_pages.grid_forget()
            if self.visual_banner_empty_bundle and self.visual_banner_empty_bundle.winfo_ismapped():
                self.visual_banner_empty_bundle.grid_forget()
            if self.visual_banner_loose and self.visual_banner_loose["frame"].winfo_ismapped():
                self.visual_banner_loose["frame"].grid_forget()
            for bb in self.bundle_banners_cache:
                if bb["frame"].winfo_ismapped():
                    bb["frame"].grid_forget()

            for i in range(1, self.split_total_pages + 1):
                self._update_card_style(i, is_bundled=False)
                r = 1 + ((i - 1) // 4)
                col = (i - 1) % 4
                if self.card_current_grid.get(i) != (r, col):
                    self.cached_page_cards[i].grid(row=r, column=col, padx=6, pady=6, sticky="nsew")
                    self.card_current_grid[i] = (r, col)
            return

        if mode == "pages":
            if self.visual_banner_pages and not self.visual_banner_pages.winfo_ismapped():
                self.visual_banner_pages.grid(row=0, column=0, columnspan=4, sticky="ew", padx=6, pady=(6, 8))
            if self.visual_banner_all and self.visual_banner_all.winfo_ismapped():
                self.visual_banner_all.grid_forget()
            if self.visual_banner_empty_bundle and self.visual_banner_empty_bundle.winfo_ismapped():
                self.visual_banner_empty_bundle.grid_forget()
            if self.visual_banner_loose and self.visual_banner_loose["frame"].winfo_ismapped():
                self.visual_banner_loose["frame"].grid_forget()
            for bb in self.bundle_banners_cache:
                if bb["frame"].winfo_ismapped():
                    bb["frame"].grid_forget()

            for i in range(1, self.split_total_pages + 1):
                is_sel = (i in self.selected_pages)
                self._update_card_style(i, is_bundled=is_sel)
                r = 1 + ((i - 1) // 4)
                col = (i - 1) % 4
                if self.card_current_grid.get(i) != (r, col):
                    self.cached_page_cards[i].grid(row=r, column=col, padx=6, pady=6, sticky="nsew")
                    self.card_current_grid[i] = (r, col)
            return

        # MODE CUSTOM BUNDLE (GROUPED SPACES)
        if self.visual_banner_all and self.visual_banner_all.winfo_ismapped():
            self.visual_banner_all.grid_forget()
        if self.visual_banner_pages and self.visual_banner_pages.winfo_ismapped():
            self.visual_banner_pages.grid_forget()

        if not self.bundle_groups:
            if self.visual_banner_empty_bundle and not self.visual_banner_empty_bundle.winfo_ismapped():
                self.visual_banner_empty_bundle.grid(row=0, column=0, columnspan=4, sticky="ew", padx=6, pady=(6, 8))
            if self.visual_banner_loose and self.visual_banner_loose["frame"].winfo_ismapped():
                self.visual_banner_loose["frame"].grid_forget()
            for bb in self.bundle_banners_cache:
                if bb["frame"].winfo_ismapped():
                    bb["frame"].grid_forget()

            for i in range(1, self.split_total_pages + 1):
                self._update_card_style(i, is_bundled=False)
                r = 1 + ((i - 1) // 4)
                col = (i - 1) % 4
                if self.card_current_grid.get(i) != (r, col):
                    self.cached_page_cards[i].grid(row=r, column=col, padx=6, pady=6, sticky="nsew")
                    self.card_current_grid[i] = (r, col)
            return

        if self.visual_banner_empty_bundle and self.visual_banner_empty_bundle.winfo_ismapped():
            self.visual_banner_empty_bundle.grid_forget()

        curr_row = 0
        all_bundled_set = set()

        for b_idx, bundle in enumerate(self.bundle_groups):
            b_pages = bundle["pages"]  # list of pages in exact click order!
            all_bundled_set.update(b_pages)
            is_active = (b_idx == self.active_bundle_idx)

            # Buat banner jika belum ada di cache
            if b_idx >= len(self.bundle_banners_cache):
                b_banner = ctk.CTkFrame(self.visual_grid_frame, corner_radius=10)
                h_bar = ctk.CTkFrame(b_banner, fg_color="transparent")
                h_bar.pack(fill="x", padx=12, pady=8)

                t_lbl = ctk.CTkLabel(h_bar, text="", font=ctk.CTkFont(size=13, weight="bold"))
                t_lbl.pack(side="left")

                cnt_lbl = ctk.CTkLabel(h_bar, text="", font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"))
                cnt_lbl.pack(side="left", padx=8)

                seq_lbl = ctk.CTkLabel(h_bar, text="", font=ctk.CTkFont(size=11), text_color=("#1976D2", "#42A5F5"))
                seq_lbl.pack(side="left", padx=8)

                del_b = ctk.CTkButton(
                    h_bar,
                    text="🗑️ Hapus Bundle",
                    width=110,
                    height=26,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color="transparent",
                    border_width=1,
                    border_color=("#E53935", "#EF5350"),
                    text_color=("#E53935", "#EF5350"),
                    hover_color=("#FFEBEE", "#3E1E1E")
                )
                del_b.pack(side="right")

                badge_l = ctk.CTkLabel(
                    h_bar,
                    text="● TARGET AKTIF (Klik halaman lepas untuk akumulasi)",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=("#1976D2", "#42A5F5")
                )

                act_b = ctk.CTkButton(
                    h_bar,
                    text="🎯 Jadikan Target Aktif",
                    width=140,
                    height=24,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color=("gray85", "gray30"),
                    hover_color=("#1976D2", "#1565C0"),
                    text_color=("gray20", "gray90")
                )

                self.bundle_banners_cache.append({
                    "frame": b_banner,
                    "title_lbl": t_lbl,
                    "cnt_lbl": cnt_lbl,
                    "seq_lbl": seq_lbl,
                    "del_btn": del_b,
                    "badge_lbl": badge_l,
                    "act_btn": act_b,
                    "is_active": None,
                    "cached_seq": None
                })

            bb = self.bundle_banners_cache[b_idx]
            if bb.get("is_active") != is_active:
                bb["frame"].configure(
                    border_width=2 if is_active else 1.5,
                    border_color=("#1976D2", "#42A5F5") if is_active else ("gray75", "gray35"),
                    fg_color=("#E3F2FD", "#1E3A5F") if is_active else ("white", "gray18")
                )
                bb["title_lbl"].configure(
                    text_color=("#1565C0", "#90CAF9") if is_active else ("gray15", "gray90")
                )
                if is_active:
                    bb["act_btn"].pack_forget()
                    bb["badge_lbl"].pack(side="right", padx=12)
                else:
                    bb["badge_lbl"].pack_forget()
                    bb["act_btn"].configure(command=lambda i=b_idx: self._set_active_bundle(i))
                    bb["act_btn"].pack(side="right", padx=10)
                bb["is_active"] = is_active

            title_text = f"📦 Bundle {b_idx + 1}"
            if bb["title_lbl"].cget("text") != title_text:
                bb["title_lbl"].configure(text=title_text)

            cnt_text = f"({len(b_pages)} Halaman)"
            if bb["cnt_lbl"].cget("text") != cnt_text:
                bb["cnt_lbl"].configure(text=cnt_text)

            if bb.get("cached_seq") != b_pages:
                if b_pages:
                    seq_str = "Urutan: " + self._format_page_list(b_pages)
                    bb["seq_lbl"].configure(text=seq_str)
                else:
                    bb["seq_lbl"].configure(text="[Klik halaman lepas untuk mengisi]")
                bb["cached_seq"] = list(b_pages)

            bb["del_btn"].configure(command=lambda i=b_idx: self._delete_bundle_group(i))

            if self.banner_current_grid.get(b_idx) != curr_row:
                bb["frame"].grid(row=curr_row, column=0, columnspan=4, sticky="ew", padx=6, pady=(10, 4))
                self.banner_current_grid[b_idx] = curr_row
            curr_row += 1

            # Grid kartu halaman bundle SESUAI URUTAN KLIK ASLI!
            if b_pages:
                for i, p in enumerate(b_pages):
                    self._update_card_style(p, is_bundled=True)
                    r = curr_row + (i // 4)
                    col = i % 4
                    if self.card_current_grid.get(p) != (r, col):
                        self.cached_page_cards[p].grid(row=r, column=col, padx=6, pady=6, sticky="nsew")
                        self.card_current_grid[p] = (r, col)
                curr_row += ((len(b_pages) - 1) // 4 + 1)

        for j in range(len(self.bundle_groups), len(self.bundle_banners_cache)):
            if self.bundle_banners_cache[j]["frame"].winfo_ismapped():
                self.bundle_banners_cache[j]["frame"].grid_forget()
            self.banner_current_grid.pop(j, None)

        loose_pages = [p for p in range(1, self.split_total_pages + 1) if p not in all_bundled_set]
        if loose_pages:
            if self.visual_banner_loose:
                title_txt = f"📄 Halaman Lepas / Belum Masuk Bundle ({len(loose_pages)} Halaman)"
                if self.visual_banner_loose["title_lbl"].cget("text") != title_txt:
                    self.visual_banner_loose["title_lbl"].configure(text=title_txt)
                if self.loose_banner_grid != curr_row:
                    self.visual_banner_loose["frame"].grid(row=curr_row, column=0, columnspan=4, sticky="ew", padx=6, pady=(16, 4))
                    self.loose_banner_grid = curr_row
                curr_row += 1

            for i, p in enumerate(loose_pages):
                self._update_card_style(p, is_bundled=False)
                r = curr_row + (i // 4)
                col = i % 4
                if self.card_current_grid.get(p) != (r, col):
                    self.cached_page_cards[p].grid(row=r, column=col, padx=6, pady=6, sticky="nsew")
                    self.card_current_grid[p] = (r, col)
        else:
            if self.visual_banner_loose and self.visual_banner_loose["frame"].winfo_ismapped():
                self.visual_banner_loose["frame"].grid_forget()
            self.loose_banner_grid = None

    def _update_selected_pages_text(self):
        if hasattr(self, "grid_header_title") and self.grid_header_title and self.grid_header_title.winfo_exists():
            self.grid_header_title.configure(text=f"Pilih Halaman yang Ingin Diekstrak ({len(self.selected_pages)} Terpilih):")

        if not hasattr(self, "sel_pages_lbl") or not self.sel_pages_lbl or not self.sel_pages_lbl.winfo_exists():
            return
        count = len(self.selected_pages)
        if count == 0:
            pages_str = "Belum ada halaman dipilih.\nKlik kartu halaman di sebelah kiri."
            color = ("gray50", "gray50")
            btn_txt = "⚡ Ekstrak Halaman Terpilih ➜"
        else:
            sorted_pages = sorted(list(self.selected_pages))
            pages_str = f"Total: {count} halaman\n" + ", ".join(f"Hal {p}" for p in sorted_pages[:15])
            if count > 15:
                pages_str += f"... (+{count - 15} lainnya)"
            color = ("#1976D2", "#42A5F5")
            btn_txt = f"⚡ Ekstrak {count} Halaman Terpilih ➜"

        self.sel_pages_lbl.configure(text=pages_str, text_color=color)
        self.execute_split_btn.configure(text=btn_txt)

    def _select_all_pages(self):
        self.selected_pages = set(range(1, self.split_total_pages + 1))
        for p in range(1, self.split_total_pages + 1):
            self._update_card_style(p, is_bundled=True)
        self._update_selected_pages_text()

    def _clear_selected_pages(self):
        self.selected_pages.clear()
        for p in range(1, self.split_total_pages + 1):
            self._update_card_style(p, is_bundled=False)
        self._update_selected_pages_text()

    def _add_bundle_group(self):
        if not self.split_current_file or self.split_total_pages <= 0:
            messagebox.showinfo("Informasi", "Silakan pilih berkas PDF terlebih dahulu!")
            return

        new_idx = len(self.bundle_groups) + 1
        self.bundle_groups.append({
            "id": new_idx,
            "name": f"Bundle {new_idx}",
            "pages": []  # List preserving exact click order!
        })
        self.active_bundle_idx = len(self.bundle_groups) - 1
        self._relayout_visual_grid()
        self._update_sidebar_custom_view()

    def _delete_bundle_group(self, index: int):
        if 0 <= index < len(self.bundle_groups):
            removed = self.bundle_groups.pop(index)
            for p in removed["pages"]:
                self._update_card_style(p, is_bundled=False)

            if self.bundle_groups:
                self.active_bundle_idx = max(0, min(self.active_bundle_idx, len(self.bundle_groups) - 1))
            else:
                self.active_bundle_idx = 0

            self._relayout_visual_grid()
            self._update_sidebar_custom_view()

    def _set_active_bundle(self, index: int):
        if 0 <= index < len(self.bundle_groups):
            self.active_bundle_idx = index
            self._relayout_visual_grid()
            self._update_sidebar_custom_view()

    def _on_page_clicked(self, page_num: int):
        mode = self.split_visual_mode_var.get()
        if mode == "all":
            self._set_split_visual_mode("custom")
            mode = "custom"

        if mode == "pages":
            # Respons Instan 0ms: Update in-place tanpa rebuild/destroy widget, tanpa blink!
            if page_num in self.selected_pages:
                self.selected_pages.remove(page_num)
                self._update_card_style(page_num, is_bundled=False)
            else:
                self.selected_pages.add(page_num)
                self._update_card_style(page_num, is_bundled=True)

            self._update_selected_pages_text()
            return

        # MODE CUSTOM BUNDLE: AKUMULASI INDEPENDEN SESUAI URUTAN KLIK (0ms ZERO-BLINK)
        if not self.bundle_groups:
            # Bundle pertama otomatis dibuat dan langsung diisi HANYA halaman ini!
            self.bundle_groups.append({
                "id": 1,
                "name": "Bundle 1",
                "pages": [page_num]
            })
            self.active_bundle_idx = 0
            self._update_card_style(page_num, is_bundled=True)
            self.update_idletasks()
            self._relayout_visual_grid()
            self._update_sidebar_custom_view()
            return

        # Pastikan active_bundle_idx valid
        if self.active_bundle_idx >= len(self.bundle_groups):
            self.active_bundle_idx = max(0, len(self.bundle_groups) - 1)

        active_bundle = self.bundle_groups[self.active_bundle_idx]

        # 1. Jika halaman yang diklik SUDAH ada di dalam bundle aktif ini -> keluarkan kembali ke halaman lepas
        if page_num in active_bundle["pages"]:
            active_bundle["pages"].remove(page_num)
            self._update_card_style(page_num, is_bundled=False)
            self.update_idletasks()
            self._relayout_visual_grid()
            self._update_sidebar_custom_view()
            return

        # 2. Jika halaman yang diklik ada di bundle LAIN -> pindahkan ke bundle aktif
        other_bundle_idx = None
        for b_idx, b in enumerate(self.bundle_groups):
            if page_num in b["pages"]:
                other_bundle_idx = b_idx
                break

        if other_bundle_idx is not None:
            self.bundle_groups[other_bundle_idx]["pages"].remove(page_num)
            active_bundle["pages"].append(page_num)
            self._update_card_style(page_num, is_bundled=True)
            self.update_idletasks()
            self._relayout_visual_grid()
            self._update_sidebar_custom_view()
            return

        # 3. Halaman lepas diklik -> LANGSUNG DIAKUMULASI SESUAI URUTAN KLIK!
        # HANYA halaman ini yang dimasukkan (halaman sebelumnya TIDAK ikutan)!
        active_bundle["pages"].append(page_num)
        self._update_card_style(page_num, is_bundled=True)
        self.update_idletasks()
        self._relayout_visual_grid()
        self._update_sidebar_custom_view()

    def _execute_visual_split_bundles(self):
        if not self.split_current_file or not os.path.exists(self.split_current_file):
            messagebox.showwarning("Peringatan", "Silakan pilih berkas PDF terlebih dahulu!")
            return

        mode = self.split_visual_mode_var.get()
        out_dir = filedialog.askdirectory(title="Pilih Folder Tujuan Penyimpanan")
        if not out_dir:
            return

        self.execute_split_btn.configure(state="disabled")

        def run():
            try:
                if mode == "all":
                    created = self.tools.split_pdf(self.split_current_file, out_dir, split_mode="all")
                    msg = f"Berhasil memecah seluruh dokumen!\n\nDihasilkan {len(created)} berkas PDF di:\n{out_dir}"
                elif mode == "pages":
                    if not self.selected_pages:
                        self.after(0, lambda: messagebox.showwarning("Peringatan", "Belum ada halaman yang dipilih! Klik kartu halaman di layar."))
                        return

                    sorted_pages = sorted(list(self.selected_pages))
                    merge_all = self.merge_ranges_var.get()

                    if merge_all:
                        range_str = ", ".join(str(p) for p in sorted_pages)
                        created = self.tools.split_pdf(self.split_current_file, out_dir, split_mode="range", range_str=range_str)
                        msg = f"Berhasil mengekstrak {len(sorted_pages)} halaman terpilih menjadi 1 berkas:\n{created[0]}"
                    else:
                        created = []
                        for p in sorted_pages:
                            out_f = self.tools.split_pdf(self.split_current_file, out_dir, split_mode="range", range_str=str(p))
                            created.extend(out_f)
                        msg = f"Berhasil membuat {len(created)} berkas dari halaman terpilih!\nTersimpan di:\n{out_dir}"
                else:
                    # Mode custom bundle - Ekstrak sesuai URUTAN KLIK ASLI!
                    bundle_page_lists = [list(b["pages"]) for b in self.bundle_groups if b["pages"]]
                    if not bundle_page_lists:
                        self.after(0, lambda: messagebox.showwarning("Peringatan", "Belum ada bundle yang memiliki halaman! Klik halaman untuk memasukkan ke bundle."))
                        return

                    merge_all = self.merge_ranges_var.get()
                    created = self.tools.split_pdf_bundles(
                        self.split_current_file,
                        out_dir,
                        ranges=bundle_page_lists,
                        merge_all_ranges=merge_all
                    )
                    if merge_all:
                        msg = f"Berhasil menggabungkan seluruh {len(bundle_page_lists)} bundle menjadi 1 berkas:\n{created[0]}"
                    else:
                        msg = f"Berhasil membuat {len(created)} berkas bundle PDF!\n\nTersimpan di:\n{out_dir}"

                self.after(0, lambda: messagebox.showinfo("Split Selesai!", msg))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal Split", f"Terjadi kesalahan: {str(e)}"))
            finally:
                self.after(0, lambda: self.execute_split_btn.configure(state="normal"))

        threading.Thread(target=run, daemon=True).start()

    # ================= TAB 3: GABUNG PDF (MERGE) =================
    def _build_merge_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        l_frame = ctk.CTkFrame(parent, corner_radius=10)
        l_frame.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")
        l_frame.grid_columnconfigure(0, weight=1)
        l_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(l_frame, text="📑 Daftar Berkas yang Akan Digabung", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(l_frame, text="Urutkan dokumen dari atas ke bawah sesuai urutan penggabungan.", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=12, pady=(0, 6), sticky="w")

        self.merge_files = []
        self.merge_listbox = tk.Listbox(l_frame, selectmode=tk.SINGLE, font=("Segoe UI", 10), bg="#222" if ctk.get_appearance_mode() == "Dark" else "#f7f7f7", fg="#fff" if ctk.get_appearance_mode() == "Dark" else "#111", borderwidth=0, highlightthickness=1)
        self.merge_listbox.grid(row=2, column=0, padx=12, pady=4, sticky="nsew")
        self.merge_listbox.bind("<<ListboxSelect>>", self._on_merge_select_item)

        m_btn_box = ctk.CTkFrame(l_frame, fg_color="transparent")
        m_btn_box.grid(row=3, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkButton(m_btn_box, text="➕ Tambah PDF", width=110, height=30, command=self._add_merge_files).pack(side="left", padx=2)
        ctk.CTkButton(m_btn_box, text="➖ Hapus", width=75, height=30, fg_color="gray40", command=self._remove_merge_file).pack(side="left", padx=2)
        ctk.CTkButton(m_btn_box, text="▲ Naik", width=65, height=30, fg_color="gray30", command=lambda: self._move_merge_item(-1)).pack(side="left", padx=2)
        ctk.CTkButton(m_btn_box, text="▼ Turun", width=65, height=30, fg_color="gray30", command=lambda: self._move_merge_item(1)).pack(side="left", padx=2)

        ctk.CTkButton(l_frame, text="⚡ Gabungkan Berkas Sekarang", height=40, fg_color=("#1976D2", "#1565C0"), font=ctk.CTkFont(weight="bold", size=13), command=self._execute_merge).grid(row=4, column=0, padx=12, pady=(4, 12), sticky="ew")

        r_frame = ctk.CTkFrame(parent, corner_radius=10, fg_color=("gray95", "gray16"))
        r_frame.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")
        r_frame.grid_columnconfigure(0, weight=1)
        r_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(r_frame, text="🔍 Pratinjau Dokumen Terpilih", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        self.merge_preview_info = ctk.CTkLabel(r_frame, text="Klik salah satu file di daftar untuk melihat pratinjau halaman pertamanya.", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12))
        self.merge_preview_info.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="w")

        self.merge_preview_box = ctk.CTkFrame(r_frame, corner_radius=8, fg_color=("white", "gray20"))
        self.merge_preview_box.grid(row=2, column=0, padx=12, pady=10, sticky="nsew")

        self.merge_img_lbl = ctk.CTkLabel(self.merge_preview_box, text="Pratinjau Halaman")
        self.merge_img_lbl.pack(expand=True, pady=20)

    def _on_merge_select_item(self, event):
        sel = self.merge_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        file_path = self.merge_files[idx]
        try:
            info = self.tools.get_pdf_info(file_path)
            self.merge_preview_info.configure(text=f"{info['filename']} | {info['total_pages']} Halaman | {info['size_kb']:.1f} KB")
            img = self._get_thumbnail(file_path, 1, max_size=(220, 300))
            if img:
                self.merge_img_lbl.configure(image=img, text="")
            else:
                self.merge_img_lbl.configure(image=None, text="Tidak dapat memuat pratinjau")
        except Exception:
            pass

    def _add_merge_files(self):
        paths = filedialog.askopenfilenames(title="Pilih Berkas PDF untuk Digabung", filetypes=[("Berkas PDF", "*.pdf")])
        for p in paths:
            norm = os.path.normpath(p)
            if norm not in self.merge_files:
                self.merge_files.append(norm)
                self.merge_listbox.insert(tk.END, f"{len(self.merge_files)}. {os.path.basename(norm)}")
        if self.merge_files and not self.merge_listbox.curselection():
            self.merge_listbox.select_set(0)
            self._on_merge_select_item(None)

    def _remove_merge_file(self):
        sel = self.merge_listbox.curselection()
        if sel:
            idx = sel[0]
            del self.merge_files[idx]
            self.merge_listbox.delete(0, tk.END)
            for i, f in enumerate(self.merge_files, start=1):
                self.merge_listbox.insert(tk.END, f"{i}. {os.path.basename(f)}")
            self.merge_img_lbl.configure(image=None, text="Pratinjau Halaman")

    def _move_merge_item(self, direction):
        sel = self.merge_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        new_idx = idx + direction
        if 0 <= new_idx < len(self.merge_files):
            self.merge_files[idx], self.merge_files[new_idx] = self.merge_files[new_idx], self.merge_files[idx]
            self.merge_listbox.delete(0, tk.END)
            for i, f in enumerate(self.merge_files, start=1):
                self.merge_listbox.insert(tk.END, f"{i}. {os.path.basename(f)}")
            self.merge_listbox.select_set(new_idx)

    def _execute_merge(self):
        if len(self.merge_files) < 2:
            messagebox.showwarning("Peringatan", "Pilih minimal 2 file PDF untuk digabungkan!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan File Hasil Gabungan", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.merge_pdfs(self.merge_files, out_path)
                self.after(0, lambda: messagebox.showinfo("Berhasil", f"Berhasil menggabungkan {len(self.merge_files)} file!\n\nTersimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    # ================= TAB 4: HALAMAN & ROTASI =================
    def _build_pages_rotate_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # Card Kiri: Hapus Halaman
        rm_card = ctk.CTkFrame(parent, corner_radius=10)
        rm_card.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")
        rm_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rm_card, text="🗑️ Hapus Halaman PDF", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(rm_card, text="Pilih halaman yang ingin dihapus dari dokumen PDF.", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

        rm_box = ctk.CTkFrame(rm_card, fg_color="transparent")
        rm_box.grid(row=2, column=0, padx=12, pady=6, sticky="ew")
        rm_box.grid_columnconfigure(0, weight=1)

        self.rm_file_entry = ctk.CTkEntry(rm_box, placeholder_text="Pilih file PDF...", height=32)
        self.rm_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(rm_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.rm_file_entry)).grid(row=0, column=1)

        ctk.CTkLabel(rm_card, text="Nomor Halaman yang Dihapus:", font=ctk.CTkFont(weight="bold", size=12)).grid(row=3, column=0, padx=12, pady=(10, 4), sticky="w")
        self.rm_pages_entry = ctk.CTkEntry(rm_card, placeholder_text="Contoh: 2, 4-6 (pisahkan dengan koma)", height=32)
        self.rm_pages_entry.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")

        ctk.CTkButton(rm_card, text="⚡ Hapus Halaman Terpilih", height=38, fg_color=("#C62828", "#B71C1C"), font=ctk.CTkFont(weight="bold"), command=self._execute_remove_pages).grid(row=5, column=0, padx=12, pady=(14, 12), sticky="ew")

        # Card Kanan: Putar PDF
        rot_card = ctk.CTkFrame(parent, corner_radius=10)
        rot_card.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")
        rot_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rot_card, text="🔄 Putar PDF (Rotate PDF)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(rot_card, text="Putar orientasi dokumen (90°, 180°, atau 270°).", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

        rot_box = ctk.CTkFrame(rot_card, fg_color="transparent")
        rot_box.grid(row=2, column=0, padx=12, pady=6, sticky="ew")
        rot_box.grid_columnconfigure(0, weight=1)

        self.rot_file_entry = ctk.CTkEntry(rot_box, placeholder_text="Pilih file PDF...", height=32)
        self.rot_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(rot_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.rot_file_entry)).grid(row=0, column=1)

        ctk.CTkLabel(rot_card, text="Sudut Rotasi:", font=ctk.CTkFont(weight="bold", size=12)).grid(row=3, column=0, padx=12, pady=(10, 4), sticky="w")
        self.rot_angle_var = ctk.StringVar(value="90° (Searah Jarum Jam)")
        rot_menu = ctk.CTkOptionMenu(rot_card, variable=self.rot_angle_var, values=["90° (Searah Jarum Jam)", "180° (Balik Arah)", "270° (Berlawanan Jarum Jam)"])
        rot_menu.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(rot_card, text="Halaman Tertentu (Opsional, kosongkan untuk semua):", font=ctk.CTkFont(size=11), text_color=("gray40", "gray60")).grid(row=5, column=0, padx=12, pady=(4, 2), sticky="w")
        self.rot_pages_entry = ctk.CTkEntry(rot_card, placeholder_text="Contoh: 1, 3 (kosong = semua halaman)", height=32)
        self.rot_pages_entry.grid(row=6, column=0, padx=12, pady=(0, 10), sticky="ew")

        ctk.CTkButton(rot_card, text="⚡ Putar Dokumen PDF", height=38, fg_color=("#F57C00", "#E65100"), font=ctk.CTkFont(weight="bold"), command=self._execute_rotate).grid(row=7, column=0, padx=12, pady=(14, 12), sticky="ew")

    # ================= TAB 5: KONVERSI & KOMPRESI =================
    def _build_convert_compress_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        img_card = ctk.CTkFrame(parent, corner_radius=10)
        img_card.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")
        img_card.grid_columnconfigure(0, weight=1)
        img_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(img_card, text="🖼️ Gambar ke PDF (JPG/PNG to PDF)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(img_card, text="Gabungkan foto atau scan gambar menjadi satu berkas PDF.", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        self.img_files = []
        self.img_listbox = tk.Listbox(img_card, selectmode=tk.SINGLE, font=("Segoe UI", 10), bg="#222" if ctk.get_appearance_mode() == "Dark" else "#f7f7f7", fg="#fff" if ctk.get_appearance_mode() == "Dark" else "#111", borderwidth=0, highlightthickness=1)
        self.img_listbox.grid(row=2, column=0, padx=12, pady=4, sticky="nsew")

        img_btn_box = ctk.CTkFrame(img_card, fg_color="transparent")
        img_btn_box.grid(row=3, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkButton(img_btn_box, text="➕ Tambah Foto/Gambar", width=140, height=30, command=self._add_images).pack(side="left", padx=2)
        ctk.CTkButton(img_btn_box, text="➖ Hapus", width=75, height=30, fg_color="gray40", command=self._remove_image_file).pack(side="left", padx=2)

        ctk.CTkButton(img_card, text="⚡ Konversi Menjadi PDF", height=38, fg_color=("#2E7D32", "#1B5E20"), font=ctk.CTkFont(weight="bold"), command=self._execute_images_to_pdf).grid(row=4, column=0, padx=12, pady=(4, 12), sticky="ew")

        r_card = ctk.CTkFrame(parent, corner_radius=10)
        r_card.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")
        r_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(r_card, text="📝 PDF ke Markdown / Teks", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")
        ctk.CTkLabel(r_card, text="Ekstrak teks lengkap halaman per halaman ke format Markdown (.md).", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=12, pady=(0, 6), sticky="w")

        md_box = ctk.CTkFrame(r_card, fg_color="transparent")
        md_box.grid(row=2, column=0, padx=12, pady=4, sticky="ew")
        md_box.grid_columnconfigure(0, weight=1)

        self.md_file_entry = ctk.CTkEntry(md_box, placeholder_text="Pilih file PDF...", height=32)
        self.md_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(md_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.md_file_entry)).grid(row=0, column=1)

        ctk.CTkButton(r_card, text="⚡ Ekstrak ke Markdown (.md)", height=34, fg_color=("#6A1B9A", "#4A148C"), font=ctk.CTkFont(weight="bold"), command=self._execute_pdf_to_markdown).grid(row=3, column=0, padx=12, pady=(4, 14), sticky="ew")

        ttk.Separator(r_card, orient="horizontal").grid(row=4, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkLabel(r_card, text="🗜️ Kompresi PDF (Compress PDF)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=5, column=0, padx=12, pady=(8, 4), sticky="w")
        ctk.CTkLabel(r_card, text="Optimalkan ukuran file PDF dengan kompresi stream Flate lossless.", text_color=("gray40", "gray60"), font=ctk.CTkFont(size=12)).grid(row=6, column=0, padx=12, pady=(0, 6), sticky="w")

        comp_box = ctk.CTkFrame(r_card, fg_color="transparent")
        comp_box.grid(row=7, column=0, padx=12, pady=4, sticky="ew")
        comp_box.grid_columnconfigure(0, weight=1)

        self.comp_file_entry = ctk.CTkEntry(comp_box, placeholder_text="Pilih file PDF...", height=32)
        self.comp_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(comp_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.comp_file_entry)).grid(row=0, column=1)

        ctk.CTkButton(r_card, text="⚡ Kompres PDF Sekarang", height=34, fg_color=("#00838F", "#006064"), font=ctk.CTkFont(weight="bold"), command=self._execute_compress).grid(row=8, column=0, padx=12, pady=(4, 12), sticky="ew")

    # ================= TAB 6: KEAMANAN & WATERMARK =================
    def _build_security_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        wm_card = ctk.CTkFrame(parent, corner_radius=10)
        wm_card.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="nsew")
        wm_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(wm_card, text="💧 Tambah Watermark & Nomor Halaman", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        wm_box = ctk.CTkFrame(wm_card, fg_color="transparent")
        wm_box.grid(row=1, column=0, padx=12, pady=4, sticky="ew")
        wm_box.grid_columnconfigure(0, weight=1)

        self.wm_file_entry = ctk.CTkEntry(wm_box, placeholder_text="Pilih file PDF...", height=32)
        self.wm_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(wm_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.wm_file_entry)).grid(row=0, column=1)

        ctk.CTkLabel(wm_card, text="Teks Watermark Cap:", font=ctk.CTkFont(weight="bold", size=12)).grid(row=2, column=0, padx=12, pady=(8, 2), sticky="w")
        self.wm_text_entry = ctk.CTkEntry(wm_card, placeholder_text="Contoh: RAHASIA / CONFIDENTIAL / DRAFT", height=32)
        self.wm_text_entry.grid(row=3, column=0, padx=12, pady=(0, 6), sticky="ew")

        ctk.CTkButton(wm_card, text="⚡ Terapkan Watermark Teks", height=34, fg_color=("#0288D1", "#0277BD"), font=ctk.CTkFont(weight="bold"), command=self._execute_watermark).grid(row=4, column=0, padx=12, pady=(4, 12), sticky="ew")

        ttk.Separator(wm_card, orient="horizontal").grid(row=5, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkLabel(wm_card, text="Format Nomor Halaman:", font=ctk.CTkFont(weight="bold", size=12)).grid(row=6, column=0, padx=12, pady=(6, 2), sticky="w")
        self.pn_format_entry = ctk.CTkEntry(wm_card, placeholder_text="Contoh: Halaman {n} dari {total}", height=32)
        self.pn_format_entry.insert(0, "Halaman {n} dari {total}")
        self.pn_format_entry.grid(row=7, column=0, padx=12, pady=(0, 8), sticky="ew")

        ctk.CTkButton(wm_card, text="⚡ Terapkan Nomor Halaman", height=34, fg_color=("#455A64", "#37474F"), font=ctk.CTkFont(weight="bold"), command=self._execute_page_numbers).grid(row=8, column=0, padx=12, pady=(4, 12), sticky="ew")

        sec_card = ctk.CTkFrame(parent, corner_radius=10)
        sec_card.grid(row=0, column=1, padx=(4, 8), pady=8, sticky="nsew")
        sec_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sec_card, text="🔒 Keamanan PDF (Password)", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=12, pady=(10, 4), sticky="w")

        ctk.CTkLabel(sec_card, text="1. Kunci Dokumen dengan Password", font=ctk.CTkFont(weight="bold", size=13)).grid(row=1, column=0, padx=12, pady=(8, 2), sticky="w")
        p_box = ctk.CTkFrame(sec_card, fg_color="transparent")
        p_box.grid(row=2, column=0, padx=12, pady=4, sticky="ew")
        p_box.grid_columnconfigure(0, weight=1)

        self.prot_file_entry = ctk.CTkEntry(p_box, placeholder_text="Pilih file PDF untuk dikunci...", height=32)
        self.prot_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(p_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.prot_file_entry)).grid(row=0, column=1)

        self.prot_pwd_entry = ctk.CTkEntry(sec_card, placeholder_text="Masukkan password proteksi...", show="•", height=32)
        self.prot_pwd_entry.grid(row=3, column=0, padx=12, pady=(0, 6), sticky="ew")

        ctk.CTkButton(sec_card, text="⚡ Kunci PDF dengan Password", height=34, fg_color=("#D32F2F", "#C62828"), font=ctk.CTkFont(weight="bold"), command=self._execute_protect).grid(row=4, column=0, padx=12, pady=(4, 12), sticky="ew")

        ttk.Separator(sec_card, orient="horizontal").grid(row=5, column=0, padx=12, pady=6, sticky="ew")

        ctk.CTkLabel(sec_card, text="2. Buka Password Dokumen (Unlock)", font=ctk.CTkFont(weight="bold", size=13)).grid(row=6, column=0, padx=12, pady=(8, 2), sticky="w")
        u_box = ctk.CTkFrame(sec_card, fg_color="transparent")
        u_box.grid(row=7, column=0, padx=12, pady=4, sticky="ew")
        u_box.grid_columnconfigure(0, weight=1)

        self.unl_file_entry = ctk.CTkEntry(u_box, placeholder_text="Pilih file PDF terkunci...", height=32)
        self.unl_file_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(u_box, text="📂 Pilih PDF", width=100, height=32, command=lambda: self._browse_single_file(self.unl_file_entry)).grid(row=0, column=1)

        self.unl_pwd_entry = ctk.CTkEntry(sec_card, placeholder_text="Masukkan password dokumen saat ini...", show="•", height=32)
        self.unl_pwd_entry.grid(row=8, column=0, padx=12, pady=(0, 6), sticky="ew")

        ctk.CTkButton(sec_card, text="⚡ Buka Kunci & Simpan Bebas Password", height=34, fg_color=("#388E3C", "#2E7D32"), font=ctk.CTkFont(weight="bold"), command=self._execute_unlock).grid(row=9, column=0, padx=12, pady=(4, 12), sticky="ew")

    # ================= LOGIKA TOOL UMUM =================
    def _browse_single_file(self, entry_widget):
        path = filedialog.askopenfilename(title="Pilih Berkas PDF", filetypes=[("Berkas PDF", "*.pdf")])
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, os.path.normpath(path))

    def _execute_remove_pages(self):
        f = self.rm_file_entry.get().strip()
        pages = self.rm_pages_entry.get().strip()
        if not f or not os.path.exists(f) or not pages:
            messagebox.showwarning("Peringatan", "Lengkapi file PDF dan nomor halaman yang ingin dihapus!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan Berkas PDF Baru", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.remove_pages(f, pages, out_path)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Halaman berhasil dihapus!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_rotate(self):
        f = self.rot_file_entry.get().strip()
        if not f or not os.path.exists(f):
            messagebox.showwarning("Peringatan", "Pilih file PDF yang valid!")
            return

        choice = self.rot_angle_var.get()
        angle = 90 if "90" in choice else (180 if "180" in choice else 270)
        pages = self.rot_pages_entry.get().strip() or None

        out_path = filedialog.asksaveasfilename(title="Simpan PDF yang Sudah Diputar", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.rotate_pdf(f, angle, out_path, pages_str=pages)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Dokumen berhasil diputar {angle}°!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _add_images(self):
        paths = filedialog.askopenfilenames(title="Pilih Foto/Gambar", filetypes=[("Gambar", "*.jpg;*.jpeg;*.png;*.webp;*.bmp")])
        for p in paths:
            norm = os.path.normpath(p)
            if norm not in self.img_files:
                self.img_files.append(norm)
                self.img_listbox.insert(tk.END, f"{len(self.img_files)}. {os.path.basename(norm)}")

    def _remove_image_file(self):
        sel = self.img_listbox.curselection()
        if sel:
            idx = sel[0]
            del self.img_files[idx]
            self.img_listbox.delete(0, tk.END)
            for i, f in enumerate(self.img_files, start=1):
                self.img_listbox.insert(tk.END, f"{i}. {os.path.basename(f)}")

    def _execute_images_to_pdf(self):
        if not self.img_files:
            messagebox.showwarning("Peringatan", "Pilih minimal 1 file gambar!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan Dokumen PDF", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.images_to_pdf(self.img_files, out_path)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Berhasil mengonversi {len(self.img_files)} gambar ke PDF!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_pdf_to_markdown(self):
        f = self.md_file_entry.get().strip()
        if not f or not os.path.exists(f):
            messagebox.showwarning("Peringatan", "Pilih file PDF yang valid!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan Berkas Markdown", defaultextension=".md", filetypes=[("Markdown", "*.md"), ("Text", "*.txt")])
        if not out_path:
            return

        def run():
            try:
                self.tools.pdf_to_markdown(f, out_path)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Teks dokumen berhasil diekstrak ke Markdown!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_compress(self):
        f = self.comp_file_entry.get().strip()
        if not f or not os.path.exists(f):
            messagebox.showwarning("Peringatan", "Pilih file PDF yang valid!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan Berkas PDF Hasil Kompresi", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                orig_s, new_s, pct = self.tools.compress_pdf(f, out_path)
                msg = f"Kompresi Selesai!\n\nUkuran Awal: {orig_s / 1024:.1f} KB\nUkuran Baru: {new_s / 1024:.1f} KB\nHemat: {pct:.1f}%\n\nTersimpan di:\n{out_path}"
                self.after(0, lambda: messagebox.showinfo("Kompresi Berhasil", msg))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_watermark(self):
        f = self.wm_file_entry.get().strip()
        text = self.wm_text_entry.get().strip()
        if not f or not os.path.exists(f) or not text:
            messagebox.showwarning("Peringatan", "Lengkapi file PDF dan teks watermark!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan PDF dengan Watermark", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.add_watermark(f, text, out_path)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Watermark berhasil diterapkan!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_page_numbers(self):
        f = self.wm_file_entry.get().strip()
        fmt = self.pn_format_entry.get().strip()
        if not f or not os.path.exists(f) or not fmt:
            messagebox.showwarning("Peringatan", "Pilih file PDF dan tentukan format nomor halaman!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan PDF dengan Nomor Halaman", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.add_page_numbers(f, out_path, format_str=fmt)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Nomor halaman berhasil ditambahkan!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_protect(self):
        f = self.prot_file_entry.get().strip()
        pwd = self.prot_pwd_entry.get().strip()
        if not f or not os.path.exists(f) or not pwd:
            messagebox.showwarning("Peringatan", "Pilih file PDF dan masukkan password!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan PDF Terproteksi", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.protect_pdf(f, pwd, out_path)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Dokumen berhasil dikunci dengan password!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    def _execute_unlock(self):
        f = self.unl_file_entry.get().strip()
        pwd = self.unl_pwd_entry.get().strip()
        if not f or not os.path.exists(f):
            messagebox.showwarning("Peringatan", "Pilih file PDF terkunci!")
            return
        out_path = filedialog.asksaveasfilename(title="Simpan PDF Bebas Password", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not out_path:
            return

        def run():
            try:
                self.tools.unlock_pdf(f, pwd, out_path)
                self.after(0, lambda: messagebox.showinfo("Selesai", f"Kunci password berhasil dihapus!\nDisimpan di:\n{out_path}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Gagal membuka proteksi: {str(e)}"))

        threading.Thread(target=run, daemon=True).start()

    # ================= EVENT HANDLERS SMART RENAMER =================
    def _browse_folder(self):
        path = filedialog.askdirectory(title="Pilih Folder File PDF")
        if path:
            self.current_folder = os.path.normpath(path)
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, self.current_folder)
            self._start_scan()

    def _open_in_explorer(self):
        folder = self.folder_entry.get().strip()
        if folder and os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showwarning("Peringatan", "Folder tidak valid atau belum dipilih!")

    def _change_theme(self, choice):
        ctk.set_appearance_mode(choice)
        is_dark = ctk.get_appearance_mode() == "Dark"
        style = ttk.Style()
        style.configure("Custom.Treeview", background="#1e1e1e" if is_dark else "#fdfdfd", foreground="#f0f0f0" if is_dark else "#101010", fieldbackground="#1e1e1e" if is_dark else "#fdfdfd")
        style.configure("Custom.Treeview.Heading", background="#2b2b2b" if is_dark else "#e2e2e2", foreground="#ffffff" if is_dark else "#111111")
        for lb in [self.merge_listbox, self.img_listbox]:
            lb.configure(bg="#222" if is_dark else "#f7f7f7", fg="#fff" if is_dark else "#111")

    def _on_mode_change(self, choice):
        if choice == "Kata Kunci Kustom":
            self.custom_entry.configure(state="normal", placeholder_text="Kata kunci (contoh: Nomor: atau Kepada:)")
        elif choice == "Regex Lanjutan":
            self.custom_entry.configure(state="normal", placeholder_text="Pola Regex (contoh: Invoice\s*#(\d+))")
        else:
            self.custom_entry.configure(state="disabled")

    def _insert_tag(self, tag):
        self.tpl_entry.insert(tk.INSERT, tag)

    def _update_table(self, items):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for item in items:
            self.tree.insert("", "end", values=(item["no"], item["old_name"], item["detected"], item["new_name"], item["status"]))
        total = len(items)
        ready = sum(1 for x in items if "Siap" in x["status"] or "Duplikat" in x["status"])
        self.stats_lbl.configure(text=f"Pratinjau Hasil: {total} berkas | {ready} siap rename")

    def _filter_table(self, event=None):
        query = self.search_entry.get().strip().lower()
        if not query:
            self._update_table(self.scanned_items)
            return
        filtered = [it for it in self.scanned_items if query in it["old_name"].lower() or query in it["detected"].lower() or query in it["new_name"].lower()]
        self._update_table(filtered)

    def _on_double_click_cell(self, event):
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item_id or column != "#4":
            return
        current_val = self.tree.item(item_id, "values")[3]
        dialog = ctk.CTkInputDialog(text="Ubah usulan nama file baru:", title="Edit Nama File")
        new_val = dialog.get_input()
        if new_val:
            new_val = sanitize_filename(new_val)
            if not new_val.lower().endswith(".pdf"):
                new_val += ".pdf"
            values = list(self.tree.item(item_id, "values"))
            values[3] = new_val
            values[4] = "Manual Edit"
            self.tree.item(item_id, values=values)
            no = int(values[0])
            for sc in self.scanned_items:
                if sc["no"] == no:
                    sc["new_name"] = new_val
                    sc["status"] = "Manual Edit"
                    break

    def _start_scan(self):
        folder = self.folder_entry.get().strip()
        if not folder or not os.path.exists(folder):
            messagebox.showwarning("Peringatan", "Silakan pilih folder PDF yang valid terlebih dahulu!")
            return
        self.current_folder = folder
        template = self.tpl_var.get().strip()
        mode = self.mode_var.get()
        custom_input = self.custom_entry.get().strip()
        custom_kw = custom_input if mode == "Kata Kunci Kustom" else None
        regex_pat = custom_input if mode == "Regex Lanjutan" else None

        self.scan_btn.configure(state="disabled")
        self.execute_btn.configure(state="disabled")
        self.status_lbl.configure(text="Sedang memindai dan membaca isi PDF...")
        self.progress_bar.set(0)

        def run_thread():
            try:
                def progress(current, total, filename):
                    pct = current / total if total > 0 else 0
                    self.after(0, lambda: self.progress_bar.set(pct))
                    self.after(0, lambda: self.status_lbl.configure(text=f"Membaca ({current}/{total}): {filename}"))

                results = self.extractor.scan_folder(folder, template=template, custom_keyword=custom_kw, regex_pattern=regex_pat, progress_callback=progress)
                self.scanned_items = results
                self.after(0, lambda: self._update_table(results))
                self.after(0, lambda: self.status_lbl.configure(text=f"Selesai memindai {len(results)} file PDF."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal Memindai", f"Terjadi kesalahan: {str(e)}"))
                self.after(0, lambda: self.status_lbl.configure(text="Gagal memindai."))
            finally:
                self.after(0, lambda: self.scan_btn.configure(state="normal"))
                self.after(0, lambda: self.execute_btn.configure(state="normal"))

        threading.Thread(target=run_thread, daemon=True).start()

    def _start_rename(self):
        if not self.scanned_items:
            messagebox.showinfo("Informasi", "Belum ada berkas yang dipindai!")
            return
        folder = self.current_folder
        total = len(self.scanned_items)
        confirm = messagebox.askyesno("Konfirmasi Rename", f"Apakah Anda yakin ingin me-rename {total} berkas PDF ini?\n\nCatatan: Anda dapat membatalkan (undo) jika ada kesalahan melalui tombol 'Undo'.")
        if not confirm:
            return

        self.scan_btn.configure(state="disabled")
        self.execute_btn.configure(state="disabled")
        self.progress_bar.set(0)

        def run_thread():
            try:
                def progress(current, total_files, name):
                    pct = current / total_files if total_files > 0 else 0
                    self.after(0, lambda: self.progress_bar.set(pct))
                    self.after(0, lambda: self.status_lbl.configure(text=f"Me-rename ({current}/{total_files}): {name}"))

                success, fails, errors = self.extractor.execute_rename(folder, self.scanned_items, progress_callback=progress)

                def show_result():
                    if fails == 0:
                        messagebox.showinfo("Sukses!", f"Selamat! Seluruh {success} berkas berhasil di-rename dengan sempurna.")
                    else:
                        err_msg = "\n".join(errors[:5])
                        messagebox.showwarning("Selesai dengan Catatan", f"{success} berhasil, {fails} gagal.\n\nContoh masalah:\n{err_msg}")
                    self._start_scan()

                self.after(0, show_result)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Gagal", f"Terjadi kesalahan: {str(e)}"))
            finally:
                self.after(0, lambda: self.scan_btn.configure(state="normal"))
                self.after(0, lambda: self.execute_btn.configure(state="normal"))

        threading.Thread(target=run_thread, daemon=True).start()

    def _undo_rename(self):
        folder = self.folder_entry.get().strip()
        if not folder or not os.path.exists(folder):
            messagebox.showwarning("Peringatan", "Pilih folder yang valid terlebih dahulu!")
            return
        confirm = messagebox.askyesno("Konfirmasi Undo", "Kembalikan nama semua file ke nama sebelum rename terakhir?")
        if not confirm:
            return
        success, fails, msg = self.extractor.undo_last_rename(folder)
        if success > 0:
            messagebox.showinfo("Undo Berhasil", f"{msg}")
            self._start_scan()
        else:
            messagebox.showwarning("Undo", msg)


if __name__ == "__main__":
    app = SmartPDFSuiteApp()
    app.mainloop()
