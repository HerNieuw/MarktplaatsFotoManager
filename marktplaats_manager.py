#!/usr/bin/env python3
"""
Marktplaats Foto Manager - Grafische applicatie voor het verwerken van productfoto's
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf
import subprocess
import os
import shutil
import glob
import random
import string
import threading
import time
from PIL import Image
import tempfile
import json
from queue import Queue
import gc
import sys
import io

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

def run_safe_command(cmd, timeout=300):
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if result.returncode != 0:
            return False, result.stderr.decode('utf-8', errors='ignore')
        return True, result.stdout.decode('utf-8', errors='ignore')
    except subprocess.TimeoutExpired:
        return False, f"Timeout na {timeout} seconden"
    except Exception as e:
        return False, str(e)


def crop_and_scale_background(bg_image_path, target_size):
    """Schaal de achtergrondafbeelding op de kortste zijde en crop center."""
    try:
        bg_img = Image.open(bg_image_path)
        target_width, target_height = target_size

        bg_width, bg_height = bg_img.size
        target_ratio = target_width / target_height
        bg_ratio = bg_width / bg_height

        if bg_ratio > target_ratio:
            new_height = target_height
            new_width = int(target_height * bg_ratio)
        else:
            new_width = target_width
            new_height = int(target_width / bg_ratio)

        bg_img = bg_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        bg_img = bg_img.crop((left, top, right, bottom))
        return bg_img
    except Exception as e:
        print(f"Fout bij schalen achtergrond: {e}")
        return None


class ImagePreviewWindow(Gtk.Window):
    def __init__(self, parent, image_files):
        super().__init__(title="Inspecteer Afbeeldingen - Transparante Achtergrond")
        self.parent = parent
        self.image_files = image_files
        self.current_index = 0
        self.current_pixbuf = None
        self.rotation_angle = 0
        self.original_pixbuf = None
        self.zoom_level = 100
        self.is_loading = False
        self.current_image_path = None

        self.set_default_size(Gdk.Screen.width(), Gdk.Screen.height())
        self.set_position(Gtk.WindowPosition.CENTER)
        self.maximize()
        self.set_border_width(10)

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_vbox)

        # Titel
        title_box = Gtk.Box(spacing=10)
        main_vbox.pack_start(title_box, False, False, 0)

        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>Inspecteer Afbeeldingen</span>")
        title_box.pack_start(title_label, True, True, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        title_box.pack_start(self.status_label, True, True, 10)

        # Scrollbare afbeelding
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
        main_vbox.pack_start(scrolled_window, True, True, 0)

        self.event_box = Gtk.EventBox()
        self.event_box.set_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.event_box.connect("scroll-event", self.on_scroll_zoom)
        scrolled_window.add(self.event_box)

        self.image = Gtk.Image()
        self.event_box.add(self.image)

        # Toolbar
        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        toolbar_box.set_size_request(-1, 140)
        main_vbox.pack_start(toolbar_box, False, False, 0)

        # Rotatie + Zoom
        control_row1 = Gtk.Box(spacing=10)
        toolbar_box.pack_start(control_row1, False, False, 0)

        # Rotatie
        rotate_frame = Gtk.Frame(label="Rotatie")
        rotate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        rotate_frame.add(rotate_box)
        control_row1.pack_start(rotate_frame, False, False, 0)

        rotate_btn_box = Gtk.Box(spacing=5)
        rotate_box.pack_start(rotate_btn_box, False, False, 0)

        self.rotate_left_btn = Gtk.Button(label="↺ -90°")
        self.rotate_left_btn.connect("clicked", self.rotate_left)
        rotate_btn_box.pack_start(self.rotate_left_btn, False, False, 0)

        self.rotate_right_btn = Gtk.Button(label="↻ +90°")
        self.rotate_right_btn.connect("clicked", self.rotate_right)
        rotate_btn_box.pack_start(self.rotate_right_btn, False, False, 0)

        self.rotate_reset_btn = Gtk.Button(label="⟲ Reset")
        self.rotate_reset_btn.connect("clicked", self.reset_rotation)
        rotate_btn_box.pack_start(self.rotate_reset_btn, False, False, 0)

        self.rotation_label = Gtk.Label(label="0°")
        rotate_btn_box.pack_start(self.rotation_label, False, False, 10)

        rot_scale_box = Gtk.Box(spacing=5)
        rotate_box.pack_start(rot_scale_box, False, False, 0)

        self.rotation_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 360, 1)
        self.rotation_scale.set_value(0)
        self.rotation_scale.set_size_request(200, -1)
        self.rotation_scale.connect("value-changed", self.on_rotation_scale_changed)
        rot_scale_box.pack_start(self.rotation_scale, True, True, 0)

        # Zoom
        zoom_frame = Gtk.Frame(label="Zoom")
        zoom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        zoom_frame.add(zoom_box)
        control_row1.pack_start(zoom_frame, False, False, 0)

        zoom_btn_box = Gtk.Box(spacing=5)
        zoom_box.pack_start(zoom_btn_box, False, False, 0)

        self.zoom_out_btn = Gtk.Button(label="🔍−")
        self.zoom_out_btn.connect("clicked", self.zoom_out)
        zoom_btn_box.pack_start(self.zoom_out_btn, False, False, 0)

        self.zoom_in_btn = Gtk.Button(label="🔍+")
        self.zoom_in_btn.connect("clicked", self.zoom_in)
        zoom_btn_box.pack_start(self.zoom_in_btn, False, False, 0)

        self.zoom_fit_btn = Gtk.Button(label="⟐ Passend")
        self.zoom_fit_btn.connect("clicked", self.zoom_fit)
        zoom_btn_box.pack_start(self.zoom_fit_btn, False, False, 0)

        self.zoom_100_btn = Gtk.Button(label="100%")
        self.zoom_100_btn.connect("clicked", self.zoom_100)
        zoom_btn_box.pack_start(self.zoom_100_btn, False, False, 0)

        self.zoom_label = Gtk.Label(label="100%")
        zoom_btn_box.pack_start(self.zoom_label, False, False, 10)

        zoom_scale_box = Gtk.Box(spacing=5)
        zoom_box.pack_start(zoom_scale_box, False, False, 0)

        self.zoom_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 400, 1)
        self.zoom_scale.set_value(100)
        self.zoom_scale.set_size_request(200, -1)
        self.zoom_scale.connect("value-changed", self.on_zoom_scale_changed)
        zoom_scale_box.pack_start(self.zoom_scale, True, True, 0)

        zoom_percent_label = Gtk.Label(label="%")
        zoom_scale_box.pack_start(zoom_percent_label, False, False, 0)

        # Navigatie
        control_row2 = Gtk.Box(spacing=10)
        toolbar_box.pack_start(control_row2, False, False, 0)

        nav_frame = Gtk.Frame(label="Navigatie")
        nav_box = Gtk.Box(spacing=5)
        nav_frame.add(nav_box)
        control_row2.pack_start(nav_frame, False, False, 0)

        self.prev_btn = Gtk.Button(label="◀ Vorige")
        self.prev_btn.connect("clicked", self.prev_image)
        nav_box.pack_start(self.prev_btn, False, False, 0)

        self.next_btn = Gtk.Button(label="Volgende ▶")
        self.next_btn.connect("clicked", self.next_image)
        nav_box.pack_start(self.next_btn, False, False, 0)

        self.progress_label = Gtk.Label(label="1/1")
        nav_box.pack_start(self.progress_label, False, False, 10)

        info_frame = Gtk.Frame(label="Informatie")
        info_box = Gtk.Box(spacing=5)
        info_frame.add(info_box)
        control_row2.pack_start(info_frame, False, False, 0)

        self.image_info_label = Gtk.Label(label="")
        info_box.pack_start(self.image_info_label, False, False, 0)

        action_frame = Gtk.Frame(label="Acties")
        action_box = Gtk.Box(spacing=5)
        action_frame.add(action_box)
        control_row2.pack_start(action_frame, False, False, 0)

        self.open_gimp_btn = Gtk.Button(label="🖌 Open in GIMP")
        self.open_gimp_btn.connect("clicked", self.open_in_gimp)
        action_box.pack_start(self.open_gimp_btn, False, False, 0)

        self.refresh_btn = Gtk.Button(label="⟳ Vernieuw")
        self.refresh_btn.connect("clicked", self.refresh_current)
        action_box.pack_start(self.refresh_btn, False, False, 0)

        # Proces knoppen
        control_row3 = Gtk.Box(spacing=10)
        toolbar_box.pack_start(control_row3, False, False, 0)

        process_frame = Gtk.Frame(label="Verwerking")
        process_box = Gtk.Box(spacing=20)
        process_frame.add(process_box)
        control_row3.pack_start(process_frame, True, True, 0)

        self.cancel_btn = Gtk.Button(label="❌ Annuleren")
        self.cancel_btn.connect("clicked", self.cancel_processing)
        process_box.pack_start(self.cancel_btn, False, False, 0)

        self.continue_btn = Gtk.Button(label="✅ Proces Voortzetten")
        self.continue_btn.get_style_context().add_class("suggested-action")
        self.continue_btn.connect("clicked", self.continue_processing)
        process_box.pack_start(self.continue_btn, False, False, 0)

        # Tooltips
        self.rotate_left_btn.set_tooltip_text("Roteer 90 graden linksom")
        self.rotate_right_btn.set_tooltip_text("Roteer 90 graden rechtsom")
        self.rotate_reset_btn.set_tooltip_text("Reset rotatie naar 0 graden")
        self.rotation_scale.set_tooltip_text("Sleep om te roteren (0-360 graden)")
        self.zoom_in_btn.set_tooltip_text("Inzoomen (+10%)")
        self.zoom_out_btn.set_tooltip_text("Uitzoomen (-10%)")
        self.zoom_fit_btn.set_tooltip_text("Pas afbeelding aan venster aan")
        self.zoom_100_btn.set_tooltip_text("Zet zoom naar 100%")
        self.zoom_scale.set_tooltip_text("Sleep om te zoomen (10-400%)")

        GLib.idle_add(self.load_first_image)
        self.show_all()

    def load_first_image(self):
        self.load_image(0)
        return False

    def on_scroll_zoom(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self.zoom_in(None)
            return True
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.zoom_out(None)
            return True
        return False

    def on_rotation_scale_changed(self, widget):
        if not self.original_pixbuf:
            return
        self.rotation_angle = int(self.rotation_scale.get_value())
        self.rotation_label.set_text(f"{self.rotation_angle}°")
        self.update_display()

    def on_zoom_scale_changed(self, widget):
        if not self.original_pixbuf:
            return
        self.zoom_level = int(self.zoom_scale.get_value())
        self.zoom_label.set_text(f"{self.zoom_level}%")
        self.update_display()

    def zoom_in(self, widget):
        if not self.original_pixbuf:
            return
        new_zoom = min(400, self.zoom_level + 10)
        self.zoom_level = new_zoom
        self.zoom_scale.set_value(new_zoom)
        self.zoom_label.set_text(f"{new_zoom}%")
        self.update_display()

    def zoom_out(self, widget):
        if not self.original_pixbuf:
            return
        new_zoom = max(10, self.zoom_level - 10)
        self.zoom_level = new_zoom
        self.zoom_scale.set_value(new_zoom)
        self.zoom_label.set_text(f"{new_zoom}%")
        self.update_display()

    def zoom_fit(self, widget):
        if not self.original_pixbuf:
            return
        allocation = self.event_box.get_allocation()
        width = allocation.width - 20
        height = allocation.height - 20

        orig_width = self.original_pixbuf.get_width()
        orig_height = self.original_pixbuf.get_height()

        if width > 0 and height > 0:
            scale_x = width / orig_width
            scale_y = height / orig_height
            scale = min(scale_x, scale_y) * 100
            new_zoom = int(max(10, min(400, scale)))
            self.zoom_level = new_zoom
            self.zoom_scale.set_value(new_zoom)
            self.zoom_label.set_text(f"{new_zoom}%")
            self.update_display()

    def zoom_100(self, widget):
        if not self.original_pixbuf:
            return
        self.zoom_level = 100
        self.zoom_scale.set_value(100)
        self.zoom_label.set_text("100%")
        self.update_display()

    def update_display(self):
        """Update de afbeelding met huidige zoom en rotatie (via PIL voor willekeurige hoeken)"""
        if not self.original_pixbuf or not self.current_image_path:
            return

        try:
            # Haal de originele afbeelding op
            orig_width = self.original_pixbuf.get_width()
            orig_height = self.original_pixbuf.get_height()

            # Schaal eerst (via GdkPixbuf voor snelheid)
            scale = self.zoom_level / 100.0
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)

            if new_width > 0 and new_height > 0:
                scaled_pixbuf = self.original_pixbuf.scale_simple(
                    new_width, new_height, GdkPixbuf.InterpType.BILINEAR
                )
            else:
                scaled_pixbuf = self.original_pixbuf.copy()

            # Als er rotatie nodig is, gebruik PIL voor willekeurige hoeken
            if self.rotation_angle != 0:
                # Converteer GdkPixbuf naar PIL Image
                data = scaled_pixbuf.get_pixels()
                pil_img = Image.frombytes('RGBA', (scaled_pixbuf.get_width(), scaled_pixbuf.get_height()), data)

                # Roteer met PIL (ondersteunt willekeurige hoeken)
                rotated_pil = pil_img.rotate(self.rotation_angle, expand=True, resample=Image.Resampling.BICUBIC)

                # Sla de geroteerde afbeelding tijdelijk op en laad hem weer in GdkPixbuf
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    rotated_pil.save(tmp.name, 'PNG')
                    tmp_path = tmp.name

                self.current_pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp_path)
                os.unlink(tmp_path)  # Verwijder tijdelijk bestand
            else:
                self.current_pixbuf = scaled_pixbuf

            self.image.set_from_pixbuf(self.current_pixbuf)

        except Exception as e:
            self.status_label.set_text(f"Fout: {e}")

    def load_image(self, index):
        if self.is_loading:
            return

        if 0 <= index < len(self.image_files):
            self.is_loading = True
            self.current_index = index
            self.rotation_angle = 0
            self.rotation_label.set_text("0°")
            self.rotation_scale.set_value(0)

            self.current_image_path = self.image_files[index]
            if not os.path.exists(self.current_image_path):
                self.status_label.set_text(f"Bestand niet gevonden: {self.current_image_path}")
                self.is_loading = False
                return

            try:
                if self.original_pixbuf:
                    del self.original_pixbuf
                if self.current_pixbuf:
                    del self.current_pixbuf

                self.original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.current_image_path)

                filename = os.path.basename(self.current_image_path)
                size = f"{self.original_pixbuf.get_width()}x{self.original_pixbuf.get_height()}"
                self.image_info_label.set_text(f"{filename}  |  {size}px")
                self.status_label.set_text(f"Afbeelding {index + 1} van {len(self.image_files)}")
                self.progress_label.set_text(f"{index + 1}/{len(self.image_files)}")

                GLib.idle_add(self.zoom_fit, None)
                gc.collect()

            except Exception as e:
                self.status_label.set_text(f"Fout bij laden: {e}")
            finally:
                self.is_loading = False

    def rotate_image(self, degrees):
        if not self.original_pixbuf:
            return

        new_angle = (self.rotation_angle + degrees) % 360
        self.rotation_angle = new_angle
        self.rotation_label.set_text(f"{new_angle}°")
        self.rotation_scale.set_value(new_angle)

        self.update_display()
        self.status_label.set_text(f"Afbeelding geroteerd naar {new_angle}°")
        self.save_rotation()

    def save_rotation(self):
        """Sla de geroteerde afbeelding op met behoud van originele resolutie"""
        if not self.original_pixbuf or self.rotation_angle == 0 or not self.current_image_path:
            return True

        try:
            # Gebruik PIL voor rotatie met originele resolutie
            pil_img = Image.open(self.current_image_path)

            # Roteer met PIL (behoud kwaliteit)
            if self.rotation_angle != 0:
                rotated_pil = pil_img.rotate(self.rotation_angle, expand=True, resample=Image.Resampling.BICUBIC)
            else:
                rotated_pil = pil_img

            # Sla op als PNG (behoud transparantie)
            rotated_pil.save(self.current_image_path, 'PNG')

            # Herlaad de pixbuf
            self.original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.current_image_path)

            self.update_display()
            self.status_label.set_text(f"Rotatie opgeslagen: {self.rotation_angle}°")
            return True
        except Exception as e:
            self.status_label.set_text(f"Fout bij opslaan: {e}")
            return False

    def rotate_left(self, widget):
        self.rotate_image(-90)

    def rotate_right(self, widget):
        self.rotate_image(90)

    def reset_rotation(self, widget):
        self.rotation_angle = 0
        self.rotation_label.set_text("0°")
        self.rotation_scale.set_value(0)

        try:
            if self.current_image_path and os.path.exists(self.current_image_path):
                self.original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.current_image_path)
                self.update_display()
                self.status_label.set_text("Rotatie gereset")
        except Exception as e:
            self.status_label.set_text(f"Fout bij resetten: {e}")

    def prev_image(self, widget):
        if self.current_index > 0:
            self.save_rotation()
            self.load_image(self.current_index - 1)

    def next_image(self, widget):
        if self.current_index < len(self.image_files) - 1:
            self.save_rotation()
            self.load_image(self.current_index + 1)

    def open_in_gimp(self, widget):
        try:
            self.save_rotation()
            subprocess.Popen(["gimp", self.current_image_path],
                           stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            self.status_label.set_text("Afbeelding geopend in GIMP")
        except FileNotFoundError:
            self.status_label.set_text("GIMP niet geïnstalleerd")

    def refresh_current(self, widget):
        self.load_image(self.current_index)

    def cancel_processing(self, widget):
        self.parent.cancel_processing()
        self.destroy()

    def continue_processing(self, widget):
        if self.save_rotation():
            if self.current_pixbuf:
                del self.current_pixbuf
            if self.original_pixbuf:
                del self.original_pixbuf
            gc.collect()
            self.parent.process_after_inspection()
            self.destroy()
        else:
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Rotatie opslaan mislukt!"
            )
            dialog.format_secondary_text("Wil je doorgaan zonder de rotatie op te slaan?")
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.parent.process_after_inspection()
                self.destroy()


class CustomFileChooser(Gtk.Dialog):
    """Eigen bestandskiezer met grote pictogrammen"""

    def __init__(self, parent, title="Selecteer foto's", select_multiple=True):
        super().__init__(title=title, parent=parent, flags=0)
        self.set_default_size(950, 700)
        self.set_modal(True)

        self.selected_files = []
        self.select_multiple = select_multiple
        self.current_folder = os.path.expanduser("~/Afbeeldingen")
        self.icon_store = None

        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )

        # Main container
        vbox = self.get_content_area()
        vbox.set_spacing(10)

        # Top: pad invoer en blader knop
        top_box = Gtk.Box(spacing=5)
        vbox.pack_start(top_box, False, False, 0)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_placeholder_text("Pad naar map met foto's...")
        self.path_entry.connect("activate", self.on_path_enter)
        top_box.pack_start(self.path_entry, True, True, 0)

        browse_btn = Gtk.Button(label="📂 Bladeren")
        browse_btn.connect("clicked", self.browse_folder)
        top_box.pack_start(browse_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="🔄 Vernieuw")
        refresh_btn.connect("clicked", self.refresh_current_folder)
        top_box.pack_start(refresh_btn, False, False, 0)

        # Huidige map label
        self.folder_label = Gtk.Label()
        self.folder_label.set_markup("<i>Selecteer een map met de 'Bladeren' knop</i>")
        self.folder_label.set_xalign(0)
        vbox.pack_start(self.folder_label, False, False, 0)

        # IconView met grote pictogrammen
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_size_request(-1, 450)
        vbox.pack_start(scrolled, True, True, 0)

        # ListStore voor IconView: (pictogram, bestandsnaam, volledig_pad)
        self.icon_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str)
        self.icon_view = Gtk.IconView()
        self.icon_view.set_model(self.icon_store)
        self.icon_view.set_pixbuf_column(0)
        self.icon_view.set_text_column(1)
        self.icon_view.set_item_width(140)
        self.icon_view.set_columns(0)
        self.icon_view.set_selection_mode(Gtk.SelectionMode.MULTIPLE if select_multiple else Gtk.SelectionMode.SINGLE)
        self.icon_view.set_activate_on_single_click(False)
        self.icon_view.connect("item-activated", self.on_item_activated)
        scrolled.add(self.icon_view)

        # Selectie info
        info_box = Gtk.Box(spacing=20)
        vbox.pack_start(info_box, False, False, 5)

        self.selected_label = Gtk.Label()
        self.selected_label.set_markup("<small>0 bestanden geselecteerd</small>")
        info_box.pack_start(self.selected_label, True, True, 0)

        if select_multiple:
            select_all_btn = Gtk.Button(label="Alles selecteren")
            select_all_btn.connect("clicked", self.select_all)
            info_box.pack_start(select_all_btn, False, False, 0)

            deselect_all_btn = Gtk.Button(label="Alles deselecteren")
            deselect_all_btn.connect("clicked", self.deselect_all)
            info_box.pack_start(deselect_all_btn, False, False, 0)

        # Verbind selectie verandering
        self.icon_view.connect("selection-changed", self.on_selection_changed)

        # Laad standaard map
        self.load_folder(self.current_folder)
        self.show_all()

    def load_folder(self, folder_path):
        """Laad afbeeldingen uit een map in de IconView"""
        self.icon_store.clear()
        self.selected_files = []
        self.selected_label.set_markup("<small>0 bestanden geselecteerd</small>")

        if not os.path.exists(folder_path):
            self.folder_label.set_markup(f"<span color='red'>Map bestaat niet: {folder_path}</span>")
            return

        self.current_folder = folder_path
        self.folder_label.set_markup(f"<b>{folder_path}</b>")
        self.path_entry.set_text(folder_path)

        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif']
        count = 0

        try:
            for file in sorted(os.listdir(folder_path)):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    ext = os.path.splitext(file)[1].lower()
                    if ext in image_extensions:
                        try:
                            pil_img = Image.open(file_path)
                            pil_img.thumbnail((120, 120), Image.Resampling.LANCZOS)

                            img_bytes = io.BytesIO()

                            if pil_img.mode in ('RGBA', 'LA', 'P'):
                                if pil_img.mode == 'P':
                                    pil_img = pil_img.convert('RGBA')
                                pil_img.save(img_bytes, format='PNG')
                            else:
                                pil_img = pil_img.convert('RGB')
                                pil_img.save(img_bytes, format='JPEG')

                            img_bytes.seek(0)

                            loader = GdkPixbuf.PixbufLoader.new()
                            loader.write(img_bytes.getvalue())
                            loader.close()
                            pixbuf = loader.get_pixbuf()

                            self.icon_store.append([pixbuf, file, file_path])
                            count += 1
                        except Exception as e:
                            print(f"Fout bij laden {file}: {e}")
                            try:
                                pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 80, 80)
                                pixbuf.fill(0x88888888)
                                self.icon_store.append([pixbuf, file, file_path])
                                count += 1
                            except:
                                pass
        except Exception as e:
            self.folder_label.set_markup(f"<span color='red'>Fout bij lezen map: {e}</span>")

        self.folder_label.set_markup(f"<b>{folder_path}</b>  <small>({count} afbeeldingen)</small>")

    def browse_folder(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Selecteer map met foto's",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OK, Gtk.ResponseType.OK)
        )
        dialog.set_current_folder(self.current_folder)

        if dialog.run() == Gtk.ResponseType.OK:
            folder_path = dialog.get_filename()
            self.load_folder(folder_path)
        dialog.destroy()

    def refresh_current_folder(self, widget):
        self.load_folder(self.current_folder)

    def on_path_enter(self, widget):
        folder_path = self.path_entry.get_text().strip()
        if folder_path and os.path.exists(folder_path):
            self.load_folder(folder_path)

    def on_item_activated(self, icon_view, path):
        model = icon_view.get_model()
        iter_ = model.get_iter(path)
        file_path = model.get_value(iter_, 2)

        if os.path.isdir(file_path):
            self.load_folder(file_path)

    def on_selection_changed(self, icon_view):
        self.selected_files = []

        model = icon_view.get_model()
        iter_ = model.get_iter_first()

        while iter_:
            path = model.get_path(iter_)
            if icon_view.path_is_selected(path):
                file_path = model.get_value(iter_, 2)
                if os.path.isfile(file_path):
                    self.selected_files.append(file_path)
            iter_ = model.iter_next(iter_)

        self.selected_label.set_markup(f"<small><b>{len(self.selected_files)}</b> bestanden geselecteerd</small>")

    def select_all(self, widget):
        model = self.icon_view.get_model()
        iter_ = model.get_iter_first()
        while iter_:
            path = model.get_path(iter_)
            self.icon_view.select_path(path)
            iter_ = model.iter_next(iter_)

    def deselect_all(self, widget):
        self.icon_view.unselect_all()

    def get_filenames(self):
        return self.selected_files


class MarktplaatsApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Marktplaats Foto Manager")

        # Kleiner en beter schaalbaar venster
        self.set_default_size(900, 650)
        self.set_border_width(15)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(True)  # Zorg dat het venster geresized kan worden

        # Set application icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if os.path.exists(icon_path):
            try:
                self.set_icon_from_file(icon_path)
            except Exception:
                pass

        self.config = {
            'source_dir': '',
            'source_files': [],
            'source_type': 'map',
            'output_dir': '',
            'watermark_path': '',
            'logo_path': '',
            'background_type': 'white',
            'background_color': '#ffffff',
            'background_image': '',
            'auto_rotate': True,
            'color_enhance': True,
            'bg_removal_tool': 'transparent-background'
        }

        self.transparent_pngs = []
        self.log_queue = Queue()
        self.stop_flag = False

        self.setup_ui()
        self.load_config()
        GLib.timeout_add(100, self.process_log_queue)

    def setup_ui(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.add(main_vbox)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Marktplaats Foto Manager</span>")
        main_vbox.pack_start(title, False, False, 0)

        notebook = Gtk.Notebook()
        main_vbox.pack_start(notebook, True, True, 0)

        settings_page = self.create_settings_page()
        notebook.append_page(settings_page, Gtk.Label(label="Instellingen"))

        processing_page = self.create_processing_page()
        notebook.append_page(processing_page, Gtk.Label(label="Verwerking"))

        log_page = self.create_log_page()
        notebook.append_page(log_page, Gtk.Label(label="Logboek"))

        self.statusbar = Gtk.Statusbar()
        main_vbox.pack_start(self.statusbar, False, False, 0)
        self.status_context = self.statusbar.get_context_id("status")

    def create_settings_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)

        # Maak een scrollbare container zodat alles past
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        page.pack_start(scrolled, True, True, 0)

        # De inhoud komt in de scrollbare container
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.set_border_width(5)
        scrolled.add(content_box)

        locations_frame = Gtk.Frame(label="Bestandslocaties")
        locations_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        locations_frame.add(locations_box)
        content_box.pack_start(locations_frame, False, False, 0)

        # ===== BRON SELECTIE =====
        source_frame = Gtk.Frame(label="Bronbestanden")
        source_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        source_frame.add(source_box)
        locations_box.pack_start(source_frame, False, False, 5)

        # Radio buttons voor bron type
        radio_box = Gtk.Box(spacing=20)
        source_box.pack_start(radio_box, False, False, 5)

        self.source_type_map = Gtk.RadioButton.new_with_label(None, "📁 Bronmap")
        self.source_type_map.connect("toggled", self.on_source_type_changed, "map")
        radio_box.pack_start(self.source_type_map, False, False, 0)

        self.source_type_files = Gtk.RadioButton.new_with_label_from_widget(self.source_type_map, "📄 Losse bestanden")
        self.source_type_files.connect("toggled", self.on_source_type_changed, "files")
        radio_box.pack_start(self.source_type_files, False, False, 0)

        # Bronmap selector
        map_box = Gtk.Box(spacing=10)
        source_box.pack_start(map_box, False, False, 5)

        map_label = Gtk.Label(label="Bronmap (foto's):")
        map_label.set_size_request(120, -1)
        self.src_entry = Gtk.Entry()
        self.src_entry.connect("changed", self.on_src_changed)
        src_btn = Gtk.Button(label="Bladeren")
        src_btn.connect("clicked", self.browse_source)
        map_box.pack_start(map_label, False, False, 0)
        map_box.pack_start(self.src_entry, True, True, 0)
        map_box.pack_start(src_btn, False, False, 0)

        # Losse bestanden selector
        files_box = Gtk.Box(spacing=10)
        source_box.pack_start(files_box, False, False, 5)

        files_label = Gtk.Label(label="Bestanden:")
        files_label.set_size_request(120, -1)
        files_box.pack_start(files_label, False, False, 0)

        files_btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        add_files_btn = Gtk.Button(label="➕ Bestanden toevoegen (grote pictogrammen)")
        add_files_btn.connect("clicked", self.browse_files_with_icons)
        files_btn_box.pack_start(add_files_btn, False, False, 0)

        files_box.pack_start(files_btn_box, False, False, 0)

        # Lijst van geselecteerde bestanden
        list_frame = Gtk.Frame(label="Geselecteerde bestanden")
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        list_frame.add(list_box)
        source_box.pack_start(list_frame, True, True, 5)

        self.files_list = Gtk.ListStore(str, str)
        self.files_treeview = Gtk.TreeView(model=self.files_list)
        self.files_treeview.set_headers_visible(True)
        self.files_treeview.set_size_request(-1, 80)

        renderer_text = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Bestandsnaam", renderer_text, text=0)
        self.files_treeview.append_column(column)

        column2 = Gtk.TreeViewColumn("Pad", renderer_text, text=1)
        self.files_treeview.append_column(column2)

        files_scroll = Gtk.ScrolledWindow()
        files_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        files_scroll.set_size_request(-1, 60)
        files_scroll.add(self.files_treeview)
        list_box.pack_start(files_scroll, True, True, 0)

        list_btn_box = Gtk.Box(spacing=5)
        list_box.pack_start(list_btn_box, False, False, 0)

        remove_file_btn = Gtk.Button(label="➖ Verwijder geselecteerd")
        remove_file_btn.connect("clicked", self.remove_selected_file)
        list_btn_box.pack_start(remove_file_btn, False, False, 0)

        clear_files_btn = Gtk.Button(label="🗑️ Lijst leegmaken")
        clear_files_btn.connect("clicked", self.clear_file_list)
        list_btn_box.pack_start(clear_files_btn, False, False, 0)

        self.files_count_label = Gtk.Label()
        self.files_count_label.set_markup("<small>0 bestanden geselecteerd</small>")
        source_box.pack_start(self.files_count_label, False, False, 5)

        # ===== UITVOERMAP =====
        out_box = Gtk.Box(spacing=10)
        out_label = Gtk.Label(label="Uitvoermap:")
        out_label.set_size_request(120, -1)
        self.out_entry = Gtk.Entry()
        self.out_entry.connect("changed", self.on_out_changed)
        out_btn = Gtk.Button(label="Bladeren")
        out_btn.connect("clicked", self.browse_output)
        out_box.pack_start(out_label, False, False, 0)
        out_box.pack_start(self.out_entry, True, True, 0)
        out_box.pack_start(out_btn, False, False, 0)
        locations_box.pack_start(out_box, False, False, 5)

        # ===== WATERMERK =====
        wm_box = Gtk.Box(spacing=10)
        wm_label = Gtk.Label(label="Watermerk bestand:")
        wm_label.set_size_request(120, -1)
        self.wm_entry = Gtk.Entry()
        self.wm_entry.connect("changed", self.on_wm_changed)
        wm_btn = Gtk.Button(label="Bladeren")
        wm_btn.connect("clicked", self.browse_watermark)
        wm_box.pack_start(wm_label, False, False, 0)
        wm_box.pack_start(self.wm_entry, True, True, 0)
        wm_box.pack_start(wm_btn, False, False, 0)
        locations_box.pack_start(wm_box, False, False, 5)

        # ===== LOGO =====
        logo_box = Gtk.Box(spacing=10)
        logo_label = Gtk.Label(label="Logo bestand:")
        logo_label.set_size_request(120, -1)
        self.logo_entry = Gtk.Entry()
        self.logo_entry.connect("changed", self.on_logo_changed)
        logo_btn = Gtk.Button(label="Bladeren")
        logo_btn.connect("clicked", self.browse_logo)
        logo_box.pack_start(logo_label, False, False, 0)
        logo_box.pack_start(self.logo_entry, True, True, 0)
        logo_box.pack_start(logo_btn, False, False, 0)
        locations_box.pack_start(logo_box, False, False, 5)

        # ===== ACHTERGROND INSTELLINGEN =====
        bg_frame = Gtk.Frame(label="Achtergrond instellingen (na inspectie)")
        bg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        bg_frame.add(bg_box)
        locations_box.pack_start(bg_frame, False, False, 8)

        type_box = Gtk.Box(spacing=10)
        type_label = Gtk.Label(label="Achtergrond type:")
        type_label.set_size_request(120, -1)
        self.bg_type_combo = Gtk.ComboBoxText()
        self.bg_type_combo.append_text("Wit (standaard)")
        self.bg_type_combo.append_text("Kleur")
        self.bg_type_combo.append_text("Afbeelding")
        self.bg_type_combo.append_text("Originele achtergrond behouden")
        self.bg_type_combo.set_active(0)
        self.bg_type_combo.connect("changed", self.on_background_type_changed)
        type_box.pack_start(type_label, False, False, 0)
        type_box.pack_start(self.bg_type_combo, False, False, 0)
        bg_box.pack_start(type_box, False, False, 0)

        color_box = Gtk.Box(spacing=10)
        color_label = Gtk.Label(label="Kleurcode (HEX):")
        color_label.set_size_request(120, -1)
        self.bg_color_entry = Gtk.Entry()
        self.bg_color_entry.set_text("#ffffff")
        self.bg_color_entry.set_sensitive(False)
        color_box.pack_start(color_label, False, False, 0)
        color_box.pack_start(self.bg_color_entry, True, True, 0)
        bg_box.pack_start(color_box, False, False, 0)

        img_box = Gtk.Box(spacing=10)
        img_label = Gtk.Label(label="Achtergrond afbeelding:")
        img_label.set_size_request(120, -1)
        self.bg_image_entry = Gtk.Entry()
        self.bg_image_entry.set_sensitive(False)
        img_btn = Gtk.Button(label="Bladeren")
        img_btn.connect("clicked", self.browse_background_image)
        img_box.pack_start(img_label, False, False, 0)
        img_box.pack_start(self.bg_image_entry, True, True, 0)
        img_box.pack_start(img_btn, False, False, 0)
        bg_box.pack_start(img_box, False, False, 0)

        info_label = Gtk.Label()
        info_label.set_markup("<small>Tip: HEX code zoals #ff0000 (rood) of selecteer een afbeelding</small>")
        bg_box.pack_start(info_label, False, False, 0)

        # ===== TOOL SELECTIE =====
        tool_frame = Gtk.Frame(label="Achtergrond Verwijdering Tool")
        tool_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        tool_frame.add(tool_box)
        locations_box.pack_start(tool_frame, False, False, 8)

        tool_info = Gtk.Label()
        tool_info.set_markup("<small>Kies welke tool je wilt gebruiken voor het verwijderen van de achtergrond</small>")
        tool_box.pack_start(tool_info, False, False, 0)

        tool_radio_box = Gtk.Box(spacing=15)
        tool_box.pack_start(tool_radio_box, False, False, 5)

        self.tool_transparent = Gtk.RadioButton.new_with_label(None, "Transparent-Background (standaard)")
        self.tool_transparent.connect("toggled", self.on_tool_changed, "transparent-background")
        tool_radio_box.pack_start(self.tool_transparent, False, False, 0)

        self.tool_rembg = Gtk.RadioButton.new_with_label_from_widget(self.tool_transparent, "Rembg (alternatief)")
        self.tool_rembg.connect("toggled", self.on_tool_changed, "rembg")
        tool_radio_box.pack_start(self.tool_rembg, False, False, 0)

        tool_status_box = Gtk.Box(spacing=10)
        tool_box.pack_start(tool_status_box, False, False, 5)

        self.tool_status_label = Gtk.Label()
        self.tool_status_label.set_markup("<small>Controleren van geïnstalleerde tools...</small>")
        tool_status_box.pack_start(self.tool_status_label, False, False, 0)

        self.check_installed_tools()

        # ===== OPTIES =====
        options_frame = Gtk.Frame(label="Verwerkingsopties")
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        options_frame.add(options_box)
        locations_box.pack_start(options_frame, False, False, 8)

        self.auto_rotate_check = Gtk.CheckButton(label="Auto-rotatie (EXIF data)")
        self.auto_rotate_check.set_active(True)
        options_box.pack_start(self.auto_rotate_check, False, False, 0)

        self.color_enhance_check = Gtk.CheckButton(label="Kleuren verbeteren (automatisch)")
        self.color_enhance_check.set_active(True)
        options_box.pack_start(self.color_enhance_check, False, False, 0)

        # ===== OPSLAAN KNOOP =====
        button_box = Gtk.Box(spacing=10)
        button_box.set_margin_top(10)
        content_box.pack_start(button_box, False, False, 0)

        save_btn = Gtk.Button(label="💾 Instellingen Opslaan")
        save_btn.connect("clicked", self.save_config)
        button_box.pack_start(save_btn, False, False, 0)

        self.source_type_map.set_active(True)
        self.on_source_type_changed(None, "map")

        return page

    def on_source_type_changed(self, widget, source_type):
        is_map = (source_type == "map")
        self.src_entry.set_sensitive(is_map)
        self.files_treeview.set_sensitive(not is_map)

        if is_map:
            self.config['source_type'] = 'map'
            self.files_count_label.set_markup("<small>Bronmap modus (alle bestanden in map worden gebruikt)</small>")
        else:
            self.config['source_type'] = 'files'
            count = len(self.files_list)
            self.files_count_label.set_markup(f"<small>{count} bestanden geselecteerd</small>")

    def browse_files_with_icons(self, widget):
        chooser = CustomFileChooser(self, "Selecteer foto's (grote pictogrammen)", select_multiple=True)
        response = chooser.run()

        if response == Gtk.ResponseType.OK:
            filenames = chooser.get_filenames()
            for filename in filenames:
                exists = False
                for row in self.files_list:
                    if row[1] == filename:
                        exists = True
                        break

                if not exists:
                    self.files_list.append([os.path.basename(filename), filename])

            count = len(self.files_list)
            self.files_count_label.set_markup(f"<small>{count} bestanden geselecteerd</small>")
            self.log_message(f"{len(filenames)} bestanden toegevoegd")

        chooser.destroy()

    def remove_selected_file(self, widget):
        selection = self.files_treeview.get_selection()
        model, iter_ = selection.get_selected()
        if iter_:
            filename = model[iter_][0]
            self.files_list.remove(iter_)
            count = len(self.files_list)
            self.files_count_label.set_markup(f"<small>{count} bestanden geselecteerd</small>")
            self.log_message(f"Verwijderd: {filename}")

    def clear_file_list(self, widget):
        self.files_list.clear()
        self.files_count_label.set_markup("<small>0 bestanden geselecteerd</small>")
        self.log_message("Bestandenlijst geleegd")

    def get_source_files(self):
        if self.source_type_map.get_active():
            source_dir = self.config.get('source_dir', '')
            if source_dir and os.path.exists(source_dir):
                image_files = []
                for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG', '*.png', '*.PNG']:
                    image_files.extend(glob.glob(os.path.join(source_dir, ext)))
                return image_files
            return []
        else:
            return [row[1] for row in self.files_list if os.path.exists(row[1])]

    def check_installed_tools(self):
        tools_status = []

        try:
            import transparent_background
            tools_status.append("✅ Transparent-Background (geïnstalleerd)")
            self.tool_transparent.set_sensitive(True)
        except ImportError:
            tools_status.append("❌ Transparent-Background (niet geïnstalleerd)")
            self.tool_transparent.set_sensitive(False)

        try:
            import rembg
            tools_status.append("✅ Rembg (geïnstalleerd)")
            self.tool_rembg.set_sensitive(True)
        except ImportError:
            tools_status.append("❌ Rembg (niet geïnstalleerd)")
            self.tool_rembg.set_sensitive(False)

        status_text = " | ".join(tools_status)
        self.tool_status_label.set_markup(f"<small>{status_text}</small>")

        if self.config.get('bg_removal_tool') == 'transparent-background' and self.tool_transparent.get_sensitive():
            self.tool_transparent.set_active(True)
        elif self.config.get('bg_removal_tool') == 'rembg' and self.tool_rembg.get_sensitive():
            self.tool_rembg.set_active(True)
        elif self.tool_transparent.get_sensitive():
            self.tool_transparent.set_active(True)
        elif self.tool_rembg.get_sensitive():
            self.tool_rembg.set_active(True)

    def on_tool_changed(self, widget, tool_name):
        if widget.get_active():
            self.config['bg_removal_tool'] = tool_name
            self.log_message(f"Tool gewijzigd naar: {tool_name}")

    def browse_source(self, widget):
        dialog = Gtk.FileChooserDialog(title="Selecteer bronmap", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.src_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def browse_output(self, widget):
        dialog = Gtk.FileChooserDialog(title="Selecteer uitvoermap", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.out_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def browse_watermark(self, widget):
        dialog = Gtk.FileChooserDialog(title="Selecteer watermerk", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        filter_png = Gtk.FileFilter()
        filter_png.set_name("PNG afbeeldingen")
        filter_png.add_mime_type("image/png")
        dialog.add_filter(filter_png)
        if dialog.run() == Gtk.ResponseType.OK:
            self.wm_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def browse_logo(self, widget):
        dialog = Gtk.FileChooserDialog(title="Selecteer logo", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        filter_img = Gtk.FileFilter()
        filter_img.set_name("Afbeeldingen")
        filter_img.add_mime_type("image/png")
        filter_img.add_mime_type("image/jpeg")
        dialog.add_filter(filter_img)
        if dialog.run() == Gtk.ResponseType.OK:
            self.logo_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def browse_background_image(self, widget):
        dialog = Gtk.FileChooserDialog(title="Selecteer achtergrond afbeelding", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        filter_img = Gtk.FileFilter()
        filter_img.set_name("Afbeeldingen")
        filter_img.add_mime_type("image/png")
        filter_img.add_mime_type("image/jpeg")
        dialog.add_filter(filter_img)
        if dialog.run() == Gtk.ResponseType.OK:
            self.bg_image_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def on_src_changed(self, widget):
        self.config['source_dir'] = widget.get_text()

    def on_out_changed(self, widget):
        self.config['output_dir'] = widget.get_text()

    def on_wm_changed(self, widget):
        self.config['watermark_path'] = widget.get_text()

    def on_logo_changed(self, widget):
        self.config['logo_path'] = widget.get_text()

    def on_background_type_changed(self, widget):
        selected = self.bg_type_combo.get_active()
        self.bg_color_entry.set_sensitive(selected == 1)
        self.bg_image_entry.set_sensitive(selected == 2)

    def create_processing_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)

        self.info_label = Gtk.Label()
        self.info_label.set_markup("<span size='large'>Klik op 'Start Verwerking'</span>")
        page.pack_start(self.info_label, False, False, 0)

        self.progress_bar = Gtk.ProgressBar()
        page.pack_start(self.progress_bar, False, False, 0)

        self.start_btn = Gtk.Button(label="Start Verwerking")
        self.start_btn.connect("clicked", self.start_processing)
        page.pack_start(self.start_btn, False, False, 0)

        self.stop_btn = Gtk.Button(label="Stop Verwerking")
        self.stop_btn.connect("clicked", self.stop_processing_callback)
        self.stop_btn.set_sensitive(False)
        page.pack_start(self.stop_btn, False, False, 0)

        self.next_project_btn = Gtk.Button(label="Door naar Volgende Project")
        self.next_project_btn.connect("clicked", self.next_project)
        self.next_project_btn.set_sensitive(False)
        page.pack_start(self.next_project_btn, False, False, 0)

        return page

    def create_log_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_border_width(10)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        page.pack_start(scrolled, True, True, 0)
        self.log_textview = Gtk.TextView()
        self.log_textview.set_editable(False)
        self.log_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        scrolled.add(self.log_textview)
        clear_btn = Gtk.Button(label="Logboek Wissen")
        clear_btn.connect("clicked", self.clear_log)
        page.pack_start(clear_btn, False, False, 0)
        return page

    def log_message(self, message, is_error=False):
        self.log_queue.put((message, is_error))

    def process_log_queue(self):
        try:
            while not self.log_queue.empty():
                message, is_error = self.log_queue.get_nowait()
                buffer = self.log_textview.get_buffer()
                end_iter = buffer.get_end_iter()
                timestamp = time.strftime("%H:%M:%S")
                log_line = f"[{timestamp}] {message}\n"
                buffer.insert(end_iter, log_line)
                self.log_textview.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 0)
                self.statusbar.push(self.status_context, message[:50])
                print(log_line.strip())
        except Exception as e:
            print(f"Error: {e}")
        return True

    def cancel_processing(self):
        self.log_message("Verwerking geannuleerd")
        self.stop_flag = True
        GLib.idle_add(self.reset_ui_after_stop)

    def stop_processing_callback(self, widget):
        self.log_message("Stop signaal...")
        self.stop_flag = True

    def save_config(self, widget):
        self.config['source_dir'] = self.src_entry.get_text()
        self.config['output_dir'] = self.out_entry.get_text()
        self.config['watermark_path'] = self.wm_entry.get_text()
        self.config['logo_path'] = self.logo_entry.get_text()
        self.config['auto_rotate'] = self.auto_rotate_check.get_active()
        self.config['color_enhance'] = self.color_enhance_check.get_active()

        selected = self.bg_type_combo.get_active()
        if selected == 0: self.config['background_type'] = 'white'
        elif selected == 1: self.config['background_type'] = 'color'
        elif selected == 2: self.config['background_type'] = 'image'
        else: self.config['background_type'] = 'original'

        self.config['background_color'] = self.bg_color_entry.get_text()
        self.config['background_image'] = self.bg_image_entry.get_text()

        self.config['source_files'] = [row[1] for row in self.files_list]

        with open(os.path.expanduser("~/.marktplaats_manager_config.json"), 'w') as f:
            json.dump(self.config, f, indent=2)
        self.log_message("Instellingen opgeslagen")
        dialog = Gtk.MessageDialog(parent=self, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text="Instellingen opgeslagen!")
        dialog.run()
        dialog.destroy()

    def load_config(self):
        config_file = os.path.expanduser("~/.marktplaats_manager_config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)

                self.src_entry.set_text(self.config.get('source_dir', ''))
                self.out_entry.set_text(self.config.get('output_dir', ''))
                self.wm_entry.set_text(self.config.get('watermark_path', ''))
                self.logo_entry.set_text(self.config.get('logo_path', ''))
                self.auto_rotate_check.set_active(self.config.get('auto_rotate', True))
                self.color_enhance_check.set_active(self.config.get('color_enhance', True))

                if 'source_files' in self.config:
                    for file_path in self.config['source_files']:
                        if os.path.exists(file_path):
                            self.files_list.append([os.path.basename(file_path), file_path])
                    count = len(self.files_list)
                    self.files_count_label.set_markup(f"<small>{count} bestanden geselecteerd</small>")

                bg_type = self.config.get('background_type', 'white')
                if bg_type == 'white': self.bg_type_combo.set_active(0)
                elif bg_type == 'color': self.bg_type_combo.set_active(1)
                elif bg_type == 'image': self.bg_type_combo.set_active(2)
                else: self.bg_type_combo.set_active(3)

                self.bg_color_entry.set_text(self.config.get('background_color', '#ffffff'))
                self.bg_image_entry.set_text(self.config.get('background_image', ''))
                self.on_background_type_changed(None)

                self.log_message("Configuratie geladen")
            except Exception as e:
                self.log_message(f"Fout bij laden: {e}", True)

    def start_processing(self, widget):
        source_files = self.get_source_files()

        if not source_files:
            self.show_error("Geen bronbestanden geselecteerd!\nSelecteer een bronmap of voeg bestanden toe.")
            return

        if not self.config['output_dir']:
            self.show_error("Selecteer een uitvoermap")
            return

        self.log_message(f"{len(source_files)} bronbestanden gevonden")
        self.config['current_source_files'] = source_files

        bg_type = self.config.get('background_type', 'white')

        if bg_type != 'original':
            tool = self.config.get('bg_removal_tool', 'transparent-background')
            if tool == 'transparent-background':
                try:
                    import transparent_background
                except ImportError:
                    self.show_error("Transparent-Background is niet geïnstalleerd!\nInstalleer met: pip install transparent-background")
                    return
            else:
                try:
                    import rembg
                except ImportError:
                    self.show_error("Rembg is niet geïnstalleerd!\nInstalleer met: pip install rembg")
                    return

        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.next_project_btn.set_sensitive(False)
        self.progress_bar.set_fraction(0)
        self.info_label.set_markup("<span size='large'>Bezig met verwerken...</span>")
        self.stop_flag = False

        thread = threading.Thread(target=self.process_images)
        thread.daemon = False
        thread.start()

    def update_progress_safe(self, fraction):
        GLib.idle_add(self._update_progress, fraction)

    def _update_progress(self, fraction):
        self.progress_bar.set_fraction(fraction)
        if fraction < 1.0:
            self.info_label.set_markup(f"<span size='large'>Verwerking: {int(fraction * 100)}%</span>")
        else:
            self.info_label.set_markup("<span size='large' color='green'>Verwerking voltooid!</span>")
        return False

    def process_remove_background_rembg(self, image_paths, output_dir):
        self.log_message("Achtergrond verwijderen met rembg...")
        output_files = []

        for i, img in enumerate(image_paths):
            if self.stop_flag:
                return []

            base_name = os.path.splitext(os.path.basename(img))[0]
            output_path = os.path.join(output_dir, f"{base_name}.png")

            try:
                from rembg import remove

                with open(img, 'rb') as f:
                    input_data = f.read()
                output_data = remove(input_data)

                with open(output_path, 'wb') as f:
                    f.write(output_data)

                output_files.append(output_path)
                self.log_message(f"Rembg: {i+1}/{len(image_paths)} verwerkt")

            except Exception as e:
                self.log_message(f"Fout met rembg voor {img}: {e}", True)
                shutil.copy2(img, output_path)
                output_files.append(output_path)

            progress = 0.5 + ((i + 1) / len(image_paths)) * 0.1
            self.update_progress_safe(progress)

        return output_files

    def process_remove_background_transparent(self, image_paths, output_dir):
        self.log_message("Achtergrond verwijderen met transparent-background...")

        for batch_start in range(0, len(image_paths), 3):
            if self.stop_flag:
                return []

            batch = image_paths[batch_start:batch_start + 3]
            temp_dir = tempfile.mkdtemp()

            self.log_message(f"Batch {batch_start//3 + 1}: {len(batch)} afbeeldingen")

            for img in batch:
                shutil.copy2(img, os.path.join(temp_dir, os.path.basename(img)))

            cmd = ["transparent-background", "--source", temp_dir, "--dest", output_dir,
                   "--type", "rgba", "--mode", "base", "--device", "cpu", "--format", "png"]

            success, output = run_safe_command(cmd, timeout=600)

            if not success:
                self.log_message(f"Fout bij transparent-background: {output}", True)

            shutil.rmtree(temp_dir, ignore_errors=True)
            progress = 0.5 + ((batch_start + len(batch)) / len(image_paths)) * 0.1
            self.update_progress_safe(progress)

        output_files = glob.glob(os.path.join(output_dir, "*.png"))
        self.log_message(f"{len(output_files)} PNG bestanden gevonden in {output_dir}")

        return output_files

    def process_images(self):
        try:
            self.log_message("=== START VERWERKING ===")

            bg_type = self.config.get('background_type', 'white')
            is_original = (bg_type == 'original')

            base_dir = os.path.dirname(os.path.abspath(__file__))
            input_dir = os.path.join(base_dir, "input")
            enhance_dir = os.path.join(base_dir, "output")

            for d in [input_dir, enhance_dir]:
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
                os.makedirs(d, exist_ok=True)

            if self.stop_flag: return

            source_files = self.config.get('current_source_files', [])

            if not source_files:
                self.log_message("Geen bronbestanden gevonden!", True)
                GLib.idle_add(self.reset_ui_after_error)
                return

            self.log_message(f"{len(source_files)} afbeeldingen om te verwerken")

            self.log_message("Stap 1: Kopieer afbeeldingen...")
            copied_files = []
            for i, img in enumerate(source_files):
                if self.stop_flag: return
                dest = os.path.join(input_dir, os.path.basename(img))
                shutil.copy2(img, dest)
                copied_files.append(dest)
                self.update_progress_safe((i + 1) / len(source_files) * 0.2)

            if is_original:
                self.log_message("Originele achtergrond behouden - overslaan van achtergrond verwijdering")
                self.transparent_pngs = copied_files
                self.log_message(f"{len(self.transparent_pngs)} originele afbeeldingen worden gebruikt")
                self.update_progress_safe(0.6)

                if self.transparent_pngs:
                    GLib.idle_add(self.show_inspection_window)
                else:
                    self.log_message("Geen afbeeldingen!", True)
                    GLib.idle_add(self.reset_ui_after_error)
                return

            if self.config['auto_rotate']:
                self.log_message("Stap 2: Auto-rotatie...")
                for i, img in enumerate(copied_files):
                    if self.stop_flag: return
                    run_safe_command(["mogrify", "-auto-orient", img], timeout=60)
                    self.update_progress_safe(0.2 + (i / len(copied_files)) * 0.1)

            self.log_message("Stap 3: Verkleinen naar 50%...")
            for i, img in enumerate(copied_files):
                if self.stop_flag: return
                run_safe_command(["mogrify", "-colorspace", "RGB", "-resize", "50%", "-colorspace", "sRGB", img], timeout=120)
                self.update_progress_safe(0.3 + (i / len(copied_files)) * 0.1)

            if self.config['color_enhance']:
                self.log_message("Stap 4: Kleurverbetering...")
                for i, img in enumerate(copied_files):
                    if self.stop_flag: return
                    dest = os.path.join(enhance_dir, os.path.basename(img))
                    shutil.copy2(img, dest)
                    self.update_progress_safe(0.4 + (i / len(copied_files)) * 0.1)

                enhancer_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image_enhancer.py")
                if os.path.exists(enhancer_script):
                    run_safe_command(["python3", enhancer_script], timeout=300)
                processed_dir = enhance_dir
            else:
                processed_dir = input_dir

            tool = self.config.get('bg_removal_tool', 'transparent-background')
            self.log_message(f"Stap 5: Transparante achtergrond maken met {tool}...")

            transparent_dir = os.path.join(self.config['output_dir'], "transparant")
            if os.path.exists(transparent_dir):
                shutil.rmtree(transparent_dir, ignore_errors=True)
            os.makedirs(transparent_dir, exist_ok=True)

            images_to_process = glob.glob(os.path.join(processed_dir, "*.jpg")) + glob.glob(os.path.join(processed_dir, "*.JPG"))
            self.log_message(f"{len(images_to_process)} afbeeldingen te verwerken")

            if tool == 'rembg':
                self.transparent_pngs = self.process_remove_background_rembg(images_to_process, transparent_dir)
            else:
                self.transparent_pngs = self.process_remove_background_transparent(images_to_process, transparent_dir)

            self.log_message(f"{len(self.transparent_pngs)} transparante PNGs gemaakt")
            self.update_progress_safe(0.6)

            if self.transparent_pngs:
                GLib.idle_add(self.show_inspection_window)
            else:
                self.log_message("Geen afbeeldingen!", True)
                GLib.idle_add(self.reset_ui_after_error)

        except Exception as e:
            self.log_message(f"Fout: {str(e)}", True)
            GLib.idle_add(self.reset_ui_after_error)

    def show_inspection_window(self):
        self.log_message("Open inspectievenster...")
        try:
            self.inspect_window = ImagePreviewWindow(self, self.transparent_pngs)
            self.inspect_window.show_all()
        except Exception as e:
            self.log_message(f"Fout: {e}", True)

    def add_background_to_png(self, png_path, output_path, bg_type, bg_color=None, bg_image=None):
        try:
            img = Image.open(png_path)

            if bg_type == 'color' and bg_color:
                bg_color = bg_color.lstrip('#')
                rgb = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4))
                background = Image.new('RGB', img.size, rgb)
                if img.mode == 'RGBA':
                    background.paste(img, (0, 0), img.split()[3])
                else:
                    background.paste(img, (0, 0))
                background.save(output_path, 'JPEG', quality=95)

            elif bg_type == 'image' and bg_image and os.path.exists(bg_image):
                bg_img = crop_and_scale_background(bg_image, img.size)
                if bg_img is not None:
                    if img.mode == 'RGBA':
                        bg_img.paste(img, (0, 0), img.split()[3])
                    else:
                        bg_img.paste(img, (0, 0))
                    bg_img.save(output_path, 'JPEG', quality=95)
                else:
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'RGBA':
                        background.paste(img, (0, 0), img.split()[3])
                    else:
                        background.paste(img, (0, 0))
                    background.save(output_path, 'JPEG', quality=95)

            else:
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, (0, 0), img.split()[3])
                else:
                    background.paste(img, (0, 0))
                background.save(output_path, 'JPEG', quality=95)

            return True
        except Exception as e:
            self.log_message(f"Fout bij toevoegen achtergrond: {e}", True)
            return False

    def process_after_inspection(self):
        self.log_message("Start genereren van eindproducten...")

        if not self.transparent_pngs:
            self.log_message("Geen transparante PNGs!", True)
            GLib.idle_add(self.reset_ui_after_error)
            return

        bg_type = self.config.get('background_type', 'white')
        is_original = (bg_type == 'original')
        bg_color = self.config.get('background_color', '#ffffff') if bg_type == 'color' else None
        bg_image = self.config.get('background_image', '') if bg_type == 'image' else None

        has_watermark = self.config['watermark_path'] and os.path.exists(self.config['watermark_path'])
        has_logo = self.config['logo_path'] and os.path.exists(self.config['logo_path'])

        temp_square_dir = os.path.join(self.config['output_dir'], "temp_square")
        os.makedirs(temp_square_dir, exist_ok=True)

        self.log_message("Stap 1: Vierkant maken van afbeeldingen (2040x2040)...")
        square_pngs = []

        for i, png in enumerate(self.transparent_pngs):
            if self.stop_flag:
                self.log_message("Verwerking gestopt")
                GLib.idle_add(self.reset_ui_after_stop)
                return

            square_png = os.path.join(temp_square_dir, f"square_{i:03d}.png")
            shutil.copy2(png, square_png)

            try:
                img = Image.open(square_png)
                square_size = 2040
                square_canvas = Image.new('RGBA' if not is_original else 'RGB', (square_size, square_size), (0, 0, 0, 0))

                x_offset = (square_size - img.width) // 2
                y_offset = (square_size - img.height) // 2

                if img.mode == 'RGBA' and not is_original:
                    square_canvas.paste(img, (x_offset, y_offset), img)
                else:
                    square_canvas.paste(img, (x_offset, y_offset))

                square_canvas.save(square_png, 'PNG' if not is_original else 'JPEG', quality=95)
                square_pngs.append(square_png)
            except Exception as e:
                self.log_message(f"Fout bij vierkant maken: {e}", True)
                square_pngs.append(square_png)

            progress = 0.7 + ((i + 1) / len(self.transparent_pngs)) * 0.1
            self.update_progress_safe(progress)

        if is_original:
            self.log_message("Originele achtergrond behouden - alleen logo/watermerk toevoegen")

            rand_prefix = ''.join(random.choices(string.ascii_uppercase, k=3))
            files_with_logo = []

            temp_with_logo_dir = os.path.join(self.config['output_dir'], "temp_with_logo")
            os.makedirs(temp_with_logo_dir, exist_ok=True)

            for i, png in enumerate(square_pngs):
                if self.stop_flag:
                    self.log_message("Verwerking gestopt")
                    GLib.idle_add(self.reset_ui_after_stop)
                    return

                jpg_path = os.path.join(temp_with_logo_dir, f"logo_{i:03d}.jpg")
                shutil.copy2(png, jpg_path)

                if has_watermark:
                    run_safe_command(["mogrify", "-path", temp_with_logo_dir, "-draw", f"image over 0,0 0,0 '{self.config['watermark_path']}'", jpg_path], timeout=60)
                if has_logo:
                    run_safe_command(["mogrify", "-gravity", "northeast", "-geometry", "+10+10", "-draw", f"image over 0,0 0,0 '{self.config['logo_path']}'", jpg_path], timeout=60)

                files_with_logo.append(jpg_path)
                self.update_progress_safe(0.8 + (i / len(square_pngs)) * 0.1)

            self.update_progress_safe(0.95)

            GLib.idle_add(self.ask_for_article_number_original, files_with_logo, temp_with_logo_dir, temp_square_dir)
            return

        # Normale flow
        self.log_message("Stap 2: Achtergrond toevoegen aan vierkante afbeeldingen...")

        white_files = []
        bg_files = []

        for i, png in enumerate(square_pngs):
            if self.stop_flag:
                self.log_message("Verwerking gestopt")
                GLib.idle_add(self.reset_ui_after_stop)
                return

            white_jpg = png.replace('.png', '_white.jpg')
            if self.add_background_to_png(png, white_jpg, 'white', None, None):
                white_files.append(white_jpg)

            if bg_type != 'white':
                bg_jpg = png.replace('.png', '_bg.jpg')
                if self.add_background_to_png(png, bg_jpg, bg_type, bg_color, bg_image):
                    bg_files.append(bg_jpg)

            progress = 0.8 + ((i + 1) / len(square_pngs)) * 0.05
            self.update_progress_safe(progress)

        self.log_message("Stap 3: Watermerk en logo toevoegen...")

        white_with_logo = []
        bg_with_logo = []

        if has_watermark or has_logo:
            for img in white_files:
                new_path = img.replace('.jpg', '_with_logo.jpg')
                shutil.copy2(img, new_path)
                white_with_logo.append(new_path)

            for img in bg_files:
                new_path = img.replace('.jpg', '_with_logo.jpg')
                shutil.copy2(img, new_path)
                bg_with_logo.append(new_path)

            if has_watermark:
                for img in white_with_logo + bg_with_logo:
                    run_safe_command(["mogrify", "-path", os.path.dirname(img), "-draw", f"image over 0,0 0,0 '{self.config['watermark_path']}'", img], timeout=60)
                self.log_message("Watermerk toegevoegd")

            if has_logo:
                for img in white_with_logo + bg_with_logo:
                    run_safe_command(["mogrify", "-gravity", "northeast", "-geometry", "+10+10", "-draw", f"image over 0,0 0,0 '{self.config['logo_path']}'", img], timeout=60)
                self.log_message("Logo toegevoegd")
        else:
            self.log_message("Geen watermerk of logo geselecteerd, map met_logo wordt niet aangemaakt")

        self.update_progress_safe(0.95)

        GLib.idle_add(self.ask_for_article_number, white_files, white_with_logo, bg_files, bg_with_logo, temp_square_dir, has_watermark or has_logo)

    def ask_for_article_number_original(self, files_with_logo, temp_with_logo_dir, temp_square_dir):
        self.log_message("Vraag artikelnummer (originele achtergrond modus)...")

        dialog = Gtk.Dialog(title="Artikelnummer", parent=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_size(500, 350)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(10)

        label = Gtk.Label(label="Voer artikel/locatie nummer in:")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Bijv: 12345 of KLANT_A")
        entry.set_size_request(300, -1)
        box.pack_start(entry, False, False, 0)

        info_text = "Mappen die worden aangemaakt:\n\n"
        info_text += "📁 met_logo/           - JPEG met logo/watermerk (originele achtergrond behouden)\n"
        info_text += "📁 originelen/         - Originele foto's uit bronmap (optioneel)"

        info_label = Gtk.Label()
        info_label.set_markup(f"<small>{info_text}</small>")
        info_label.set_xalign(0)
        box.pack_start(info_label, False, False, 0)

        move_originals_check = Gtk.CheckButton(label="Originele foto's verplaatsen naar map 'originelen/'")
        move_originals_check.set_active(True)
        box.pack_start(move_originals_check, False, False, 5)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            article_number = entry.get_text().strip()
            if article_number:
                final_dir = os.path.join(os.path.dirname(self.config['output_dir']), article_number)
                os.makedirs(final_dir, exist_ok=True)

                dir_with_logo = os.path.join(final_dir, "met_logo")
                os.makedirs(dir_with_logo, exist_ok=True)

                rand_prefix = ''.join(random.choices(string.ascii_uppercase, k=3))

                for i, img in enumerate(files_with_logo):
                    if os.path.exists(img):
                        new_name = f"{rand_prefix}_{i+1:03d}.jpg"
                        dest = os.path.join(dir_with_logo, new_name)
                        shutil.move(img, dest)

                if move_originals_check.get_active():
                    dir_originals = os.path.join(final_dir, "originelen")
                    os.makedirs(dir_originals, exist_ok=True)
                    originals_count = 0
                    for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']:
                        for img in glob.glob(os.path.join(self.config['source_dir'], ext)):
                            dest = os.path.join(dir_originals, os.path.basename(img))
                            shutil.move(img, dest)
                            originals_count += 1
                    self.log_message(f"Originelen: {originals_count} bestanden")

                shutil.rmtree(temp_square_dir, ignore_errors=True)
                shutil.rmtree(temp_with_logo_dir, ignore_errors=True)

                self.log_message(f"=== VERWERKING VOLTOOID! ===")
                self.log_message(f"Bestanden opgeslagen in: {final_dir}")

                success_msg = f"✅ Verwerking voltooid!\n\n"
                success_msg += f"📁 met_logo/ - {len(files_with_logo)} bestanden\n"
                success_msg += f"\n📍 Locatie: {final_dir}"

                success_dialog = Gtk.MessageDialog(parent=self, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text="Verwerking voltooid!")
                success_dialog.format_secondary_text(success_msg)
                success_dialog.run()
                success_dialog.destroy()

                self.update_progress_safe(1.0)
                self.next_project_btn.set_sensitive(True)

        dialog.destroy()
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)

    def ask_for_article_number(self, white_files, white_with_logo, bg_files, bg_with_logo, temp_square_dir, has_logo_files):
        self.log_message("Vraag artikelnummer...")

        dialog = Gtk.Dialog(title="Artikelnummer", parent=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_default_size(500, 450)

        box = dialog.get_content_area()
        box.set_spacing(10)
        box.set_border_width(10)

        label = Gtk.Label(label="Voer artikel/locatie nummer in:")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Bijv: 12345 of KLANT_A")
        entry.set_size_request(300, -1)
        box.pack_start(entry, False, False, 0)

        bg_type = self.config.get('background_type', 'white')
        tool = self.config.get('bg_removal_tool', 'transparent-background')

        info_text = f"Mappen die worden aangemaakt:\n\n"
        info_text += f"📁 transparant/        - Vierkante PNG met transparante achtergrond (2040x2040)\n"
        info_text += f"   (gemaakt met: {tool})\n"
        info_text += f"📁 zonder_logo/        - JPEG met witte achtergrond\n"

        if has_logo_files:
            info_text += f"📁 met_logo/           - JPEG met witte achtergrond + watermerk/logo\n"

        if bg_type != 'white':
            info_text += "📁 zonder_logo_bg/     - JPEG met gekozen achtergrond\n"
            if has_logo_files:
                info_text += "📁 met_logo_bg/        - JPEG met gekozen achtergrond + watermerk/logo\n"

        info_text += "\n📁 originelen/         - Originele foto's uit bronmap (optioneel)"

        info_label = Gtk.Label()
        info_label.set_markup(f"<small>{info_text}</small>")
        info_label.set_xalign(0)
        box.pack_start(info_label, False, False, 0)

        move_originals_check = Gtk.CheckButton(label="Originele foto's verplaatsen naar map 'originelen/'")
        move_originals_check.set_active(True)
        box.pack_start(move_originals_check, False, False, 5)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            article_number = entry.get_text().strip()
            if article_number:
                final_dir = os.path.join(os.path.dirname(self.config['output_dir']), article_number)
                os.makedirs(final_dir, exist_ok=True)

                dir_transparent = os.path.join(final_dir, "transparant")
                dir_without = os.path.join(final_dir, "zonder_logo")
                os.makedirs(dir_transparent, exist_ok=True)
                os.makedirs(dir_without, exist_ok=True)

                if has_logo_files and white_with_logo:
                    dir_with = os.path.join(final_dir, "met_logo")
                    os.makedirs(dir_with, exist_ok=True)

                for png in self.transparent_pngs:
                    if os.path.exists(png):
                        dest = os.path.join(dir_transparent, os.path.basename(png))
                        shutil.move(png, dest)

                rand_prefix = ''.join(random.choices(string.ascii_uppercase, k=3))

                for i, img in enumerate(white_files):
                    if os.path.exists(img):
                        new_name = f"{rand_prefix}_{i+1:03d}.jpg"
                        dest = os.path.join(dir_without, new_name)
                        shutil.move(img, dest)

                if has_logo_files and white_with_logo:
                    for i, img in enumerate(white_with_logo):
                        if os.path.exists(img):
                            new_name = f"{rand_prefix}_{i+1:03d}.jpg"
                            dest = os.path.join(dir_with, new_name)
                            shutil.move(img, dest)

                if bg_type != 'white' and bg_files:
                    dir_without_bg = os.path.join(final_dir, "zonder_logo_bg")
                    os.makedirs(dir_without_bg, exist_ok=True)

                    if has_logo_files and bg_with_logo:
                        dir_with_bg = os.path.join(final_dir, "met_logo_bg")
                        os.makedirs(dir_with_bg, exist_ok=True)

                    for i, img in enumerate(bg_files):
                        if os.path.exists(img):
                            new_name = f"{rand_prefix}_{i+1:03d}.jpg"
                            dest = os.path.join(dir_without_bg, new_name)
                            shutil.move(img, dest)

                    if has_logo_files and bg_with_logo:
                        for i, img in enumerate(bg_with_logo):
                            if os.path.exists(img):
                                new_name = f"{rand_prefix}_{i+1:03d}.jpg"
                                dest = os.path.join(dir_with_bg, new_name)
                                shutil.move(img, dest)

                if move_originals_check.get_active():
                    dir_originals = os.path.join(final_dir, "originelen")
                    os.makedirs(dir_originals, exist_ok=True)
                    originals_count = 0
                    for ext in ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG']:
                        for img in glob.glob(os.path.join(self.config['source_dir'], ext)):
                            dest = os.path.join(dir_originals, os.path.basename(img))
                            shutil.move(img, dest)
                            originals_count += 1
                    self.log_message(f"Originelen: {originals_count} bestanden")

                shutil.rmtree(temp_square_dir, ignore_errors=True)

                self.log_message(f"=== VERWERKING VOLTOOID! ===")
                self.log_message(f"Bestanden opgeslagen in: {final_dir}")

                success_msg = f"✅ Verwerking voltooid!\n\n"
                success_msg += f"📁 transparant/ - PNG bestanden (tool: {tool})\n"
                success_msg += f"📁 zonder_logo/ - {len(white_files)} bestanden\n"
                if has_logo_files:
                    success_msg += f"📁 met_logo/ - {len(white_with_logo)} bestanden\n"
                if bg_type != 'white' and bg_files:
                    success_msg += f"📁 zonder_logo_bg/ - {len(bg_files)} bestanden\n"
                    if has_logo_files:
                        success_msg += f"📁 met_logo_bg/ - {len(bg_with_logo)} bestanden\n"
                success_msg += f"\n📍 Locatie: {final_dir}"

                success_dialog = Gtk.MessageDialog(parent=self, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text="Verwerking voltooid!")
                success_dialog.format_secondary_text(success_msg)
                success_dialog.run()
                success_dialog.destroy()

                self.update_progress_safe(1.0)
                self.next_project_btn.set_sensitive(True)

        dialog.destroy()
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)

    def next_project(self, widget):
        self.log_message("=== START NIEUW PROJECT ===")
        self.transparent_pngs = []
        self.stop_flag = False

        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        self.next_project_btn.set_sensitive(False)
        self.progress_bar.set_fraction(0)
        self.info_label.set_markup("<span size='large'>Klik op 'Start Verwerking' voor een nieuw project</span>")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        input_dir = os.path.join(base_dir, "input")
        enhance_dir = os.path.join(base_dir, "output")

        for d in [input_dir, enhance_dir]:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
                os.makedirs(d, exist_ok=True)

        transparent_dir = os.path.join(self.config['output_dir'], "transparant")
        shutil.rmtree(transparent_dir, ignore_errors=True)

        self.log_message("Klaar voor volgend project.")

    def reset_ui_after_error(self):
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        self.next_project_btn.set_sensitive(False)
        self.progress_bar.set_fraction(0)
        self.info_label.set_markup("<span size='large' color='red'>Fout!</span>")
        self.stop_flag = False
        return False

    def reset_ui_after_stop(self):
        self.start_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        self.next_project_btn.set_sensitive(False)
        self.progress_bar.set_fraction(0)
        self.info_label.set_markup("<span size='large' color='orange'>Gestopt.</span>")
        self.stop_flag = False
        return False

    def show_error(self, message):
        dialog = Gtk.MessageDialog(parent=self, flags=0, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text=message)
        dialog.run()
        dialog.destroy()

    def clear_log(self, widget):
        self.log_textview.get_buffer().set_text("")


def main():
    GLib.set_prgname("marktplaats_manager")
    app = MarktplaatsApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
