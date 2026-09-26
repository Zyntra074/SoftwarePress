import time
import threading
import customtkinter as ctk
from PIL import Image, ImageDraw
from pynput import keyboard, mouse
import os
import sys
import json
import ctypes

# Workaround to show icon in the taskbar (Windows only)
try:
    myappid = 'ekan.universal.mouse.press.v1' # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

# --- Configurations and Colors ---
PRIMARY_COLOR = "#b507e0"
BG_COLOR = "#3B3441"
TEXT_COLOR = "#ffffff"

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

def hex_to_rgba(h, a=255):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (a,)

def get_rounded_image(img, radius):
    # Apply rounded corners to an image
    circle = Image.new('L', (radius * 2, radius * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)
    
    alpha = Image.new('L', img.size, 255)
    w, h = img.size
    
    alpha.paste(circle.crop((0, 0, radius, radius)), (0, 0))
    alpha.paste(circle.crop((0, radius, radius, radius * 2)), (0, h - radius))
    alpha.paste(circle.crop((radius, 0, radius * 2, radius)), (w - radius, 0))
    alpha.paste(circle.crop((radius, radius, radius * 2, radius * 2)), (w - radius, h - radius))
    
    img = img.convert("RGBA")
    img.putalpha(alpha)
    return img

def ensure_mouse_icons_exist():
    base_dir = get_resource_path("")
    left_path = os.path.join(base_dir, "mouse_icon_left.png")
    right_path = os.path.join(base_dir, "mouse_icon_right.png")
    both_path = os.path.join(base_dir, "mouse_icon_both.png")
    
    if os.path.exists(left_path) and os.path.exists(right_path) and os.path.exists(both_path):
        return
        
    w, h = 200, 280
    base_color = hex_to_rgba("#88898C")
    border_color = hex_to_rgba("#434447")
    primary_color = hex_to_rgba(PRIMARY_COLOR) 
    wheel_color = hex_to_rgba("#3B3441")
    wire_color = hex_to_rgba("#CFCFCF")
    
    bb = [40, 60, 160, 240]
    radius = 50
    
    for active_side in ["left", "right", "both"]:
        img = Image.new("RGBA", (w, h), (0,0,0,0))
        d = ImageDraw.Draw(img)
        
        # Wire
        d.line([(100, 60), (100, 30), (120, 10)], fill=wire_color, width=6, joint="curve")
        
        base_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        d_base = ImageDraw.Draw(base_layer)
        d_base.rounded_rectangle(bb, radius=radius, fill=base_color)
        
        active_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        d_active = ImageDraw.Draw(active_layer)
        d_active.rounded_rectangle(bb, radius=radius, fill=primary_color)
        
        # Crop logic
        if active_side == "left":
            region = active_layer.crop((40, 60, 100, 140))
            base_layer.paste(region, (40, 60))
        elif active_side == "right":
            region = active_layer.crop((100, 60, 160, 140))
            base_layer.paste(region, (100, 60))
        elif active_side == "both":
            region = active_layer.crop((40, 60, 160, 140))
            base_layer.paste(region, (40, 60))
            
        img.paste(base_layer, (0,0), base_layer)
        
        # Outlines & Dividers
        d.rounded_rectangle(bb, radius=radius, fill=None, outline=border_color, width=6)
        d.line([(40, 140), (160, 140)], fill=border_color, width=6)
        d.line([(100, 60), (100, 140)], fill=border_color, width=6)
        
        # Scroll wheel
        wheel_bb = [90, 85, 110, 120]
        d.rounded_rectangle(wheel_bb, radius=5, fill=wheel_color, outline=border_color, width=3)
        for wy in range(95, 115, 4):
            d.line([(93, wy), (107, wy)], fill=border_color, width=2)
            
        if active_side == "left":
            img.save(left_path)
        elif active_side == "right":
            img.save(right_path)
        else:
            img.save(both_path)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")  # We'll override colors manually for our theme

class MousePressApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Universal Mouse Press")
        self.geometry("400x650")
        self.resizable(False, False)
        
        # Set Window Icon
        icon_path = get_resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        
        # Override background color
        self.configure(fg_color=BG_COLOR)
        
        # Additional Windows workaround for taskbar grouping
        try:
            self.after(100, lambda: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid))
        except Exception:
            pass

        # Variables for State
        self.custom_hotkey = "F4"  # Default hotkey
        self.target_button = mouse.Button.left
        self.is_holding = False
        self.hotkey_listener_thread = None
        self.mouse_controller = mouse.Controller()
        
        self.capturing_hotkey = False
        self.current_modifiers = set()
        self.captured_modifiers = []
        self.captured_key = ""
        self.custom_hotkey_display = "F4" # Default fallback display
        
        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
            
        self.config_file = os.path.join(application_path, "config.json")
        self.load_settings()
        
        # Build initial display string from loaded config
        parts = [m.capitalize() for m in self.captured_modifiers]
        if self.captured_key:
            parts.append(self.captured_key.upper())
        self.custom_hotkey_display = " + ".join(parts) if parts else "Nenhum"
        
        # Prepare graphical mouse assets
        ensure_mouse_icons_exist()
        base_dir = get_resource_path("")
        self.img_mouse_left = ctk.CTkImage(Image.open(os.path.join(base_dir, "mouse_icon_left.png")), size=(150, 210))
        self.img_mouse_right = ctk.CTkImage(Image.open(os.path.join(base_dir, "mouse_icon_right.png")), size=(150, 210))
        self.img_mouse_both = ctk.CTkImage(Image.open(os.path.join(base_dir, "mouse_icon_both.png")), size=(150, 210))
        
        # UI Elements Setup
        self.setup_ui()
        
        # Start global keyboard listener
        self.start_keyboard_listener()
        
    def setup_ui(self):
        # 1. Logo
        logo_path = get_resource_path("logo.png")
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            # The original image might be large (e.g. 1024x1024). 
            # A fixed 25px radius is too small. We calculate relative to image size.
            radius = int(min(img.size) * 0.15) # 15% rounding
            img = get_rounded_image(img, radius)
            
            logo_img = ctk.CTkImage(light_image=img,
                                    dark_image=img,
                                    size=(120, 120))
            self.logo_label = ctk.CTkLabel(self, image=logo_img, text="")
            self.logo_label.pack(pady=(15, 5))
        
        # 2. Title
        self.title_label = ctk.CTkLabel(self, text="Universal Mouse Press", font=ctk.CTkFont(size=24, weight="bold"), text_color=TEXT_COLOR)
        self.title_label.pack(pady=(0, 5))
        
        # 3. Status Frame
        self.status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.status_frame.pack(pady=10)
        
        self.status_title = ctk.CTkLabel(self.status_frame, text="Status:", font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT_COLOR)
        self.status_title.grid(row=0, column=0, padx=5)
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="INACTIVE", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray")
        self.status_label.grid(row=0, column=1, padx=5)
        
        # 4. Settings Frame
        self.settings_frame = ctk.CTkFrame(self, fg_color="#2b2630", corner_radius=15)
        self.settings_frame.pack(pady=20, padx=30, fill="both", expand=True)

        # Mouse Visual Selection
        self.button_label = ctk.CTkLabel(self.settings_frame, text="Clique no Botão do Mouse Virtual:", text_color=TEXT_COLOR, font=ctk.CTkFont(size=14))
        self.button_label.pack(pady=(15, 10))
        
        self.mouse_visual_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.mouse_visual_frame.pack(pady=(0, 5))

        self.mouse_label = ctk.CTkLabel(self.mouse_visual_frame, text="", image=self.img_mouse_left)
        self.mouse_label.pack()
        self.mouse_label.bind("<Button-1>", self.on_mouse_click)
        self.mouse_label.bind("<Motion>", self.on_mouse_hover)
        
        # Hotkey Configuration
        self.hotkey_label = ctk.CTkLabel(self.settings_frame, text="Tecla de Atalho (Liga/Desliga):", text_color=TEXT_COLOR, font=ctk.CTkFont(size=14))
        self.hotkey_label.pack(pady=(10, 5))
        
        self.hotkey_btn = ctk.CTkButton(self.settings_frame, 
                                        text=f"Atalho Atual: {self.custom_hotkey_display}",
                                        fg_color=PRIMARY_COLOR,
                                        hover_color="#9005b3",
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        command=self.capture_new_hotkey)
        self.hotkey_btn.pack(pady=(0, 20))
        
        # Footer
        self.footer_label = ctk.CTkLabel(self, text="Criado para automatizar seus cliques.", font=ctk.CTkFont(size=12, slant="italic"), text_color="gray")
        self.footer_label.pack(side="bottom", pady=15)

    def is_in_hitbox(self, x, y, side):
        # Precise hitboxes matching the green borders the user indicated
        # Y goes from ~48 to 102
        if 48 <= y <= 102:
            # Left button ranges from ~35 to 65 (avoiding edges and scroll wheel)
            if side == "left" and 35 <= x <= 65:
                return True
            # Right button ranges from ~85 to 115
            elif side == "right" and 85 <= x <= 115:
                return True
        return False

    def on_mouse_hover(self, event):
        if self.is_in_hitbox(event.x, event.y, "left") or self.is_in_hitbox(event.x, event.y, "right"):
            self.mouse_label.configure(cursor="hand2")
        else:
            self.mouse_label.configure(cursor="arrow")

    def on_mouse_click(self, event):
        clicked_side = None
        if self.is_in_hitbox(event.x, event.y, "left"):
            clicked_side = "left"
        elif self.is_in_hitbox(event.x, event.y, "right"):
            clicked_side = "right"
            
        if clicked_side:
            self.toggle_visual_button(clicked_side)

    def toggle_visual_button(self, side):
        new_state = self.target_button
        
        if self.target_button == mouse.Button.left:
            if side == "right":
                new_state = "both"
        elif self.target_button == mouse.Button.right:
            if side == "left":
                new_state = "both"
        elif self.target_button == "both":
            if side == "left":
                new_state = mouse.Button.right
            elif side == "right":
                new_state = mouse.Button.left
                
        if new_state != self.target_button:
            self.target_button = new_state
            
            if new_state == mouse.Button.left:
                self.mouse_label.configure(image=self.img_mouse_left)
            elif new_state == mouse.Button.right:
                self.mouse_label.configure(image=self.img_mouse_right)
            elif new_state == "both":
                self.mouse_label.configure(image=self.img_mouse_both)
                
            # If currently holding, toggle it off to avoid sticky buttons
            if self.is_holding:
                self.toggle_hold()

    def capture_new_hotkey(self):
        self.capturing_hotkey = True
        self.hotkey_btn.configure(text="Pressione uma tecla...", fg_color="#ffcc00", text_color="black")
        
    def update_hotkey_ui(self):
        parts = [m.capitalize() for m in self.captured_modifiers]
        if self.captured_key:
            parts.append(self.captured_key.upper())
        self.custom_hotkey_display = " + ".join(parts) if parts else "Nenhum"
        self.hotkey_btn.configure(text=f"Atalho Atual: {self.custom_hotkey_display}", fg_color=PRIMARY_COLOR, text_color=TEXT_COLOR)

    def save_settings(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump({
                    "captured_modifiers": self.captured_modifiers,
                    "captured_key": self.captured_key
                }, f)
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")
            
    def load_settings(self):
        # Apply defaults
        self.captured_modifiers = []
        self.captured_key = "f4"
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    if "captured_modifiers" in data and "captured_key" in data:
                        self.captured_modifiers = data["captured_modifiers"]
                        self.captured_key = data["captured_key"]
                    # Legacy support for old config format
                    elif "custom_hotkey" in data:
                        self.captured_key = data["custom_hotkey"].lower()
            except Exception as e:
                print(f"Erro ao carregar configurações: {e}")

    def parse_key(self, key):
        try:
            # When Ctrl is held, the char is shifted into control characters (e.g. \x01 for A)
            if hasattr(key, 'char') and key.char:
                if len(key.char) == 1 and ord(key.char) < 32:
                    # Map control characters back to their a-z equivalents roughly
                    # \x01 is 'a', \x1a is 'z'
                    return chr(ord(key.char) + 96)
                return key.char.lower()
            elif hasattr(key, 'vk') and key.vk:
                # Fallback to virtual keycode if char is weird
                if 65 <= key.vk <= 90:
                    return chr(key.vk).lower()
        except Exception:
            pass

        try:
            name = str(key).replace("Key.", "").lower()
            if "ctrl" in name: return "ctrl"
            if "shift" in name: return "shift"
            if "alt" in name: return "alt"
            if "cmd" in name or "windows" in name: return "cmd"
            return name
        except Exception:
            return ""

    def on_press(self, key):
        key_str = self.parse_key(key)
        if not key_str: return

        if key_str in ["ctrl", "shift", "alt", "cmd"]:
            self.current_modifiers.add(key_str)

        if self.capturing_hotkey:
            # Allow releasing modifiers to save the binding if we want JUST modifiers,
            # but usually we want Mod + Key. We finish capturing when a NON-modifier is pressed
            # OR on release of a modifier (handled in on_release).
            if key_str not in ["ctrl", "shift", "alt", "cmd"]:
                self.captured_modifiers = sorted(list(self.current_modifiers))
                self.captured_key = key_str
                
                self.capturing_hotkey = False
                self.save_settings()
                self.after(10, self.update_hotkey_ui)
            return

        # Normal operation: check if current state matches hotkey
        if not self.capturing_hotkey and self.captured_key:
            # If the current pressed key is our target key
            if key_str == self.captured_key:
                # Check if modifiers match EXACTLY
                if sorted(list(self.current_modifiers)) == sorted(self.captured_modifiers):
                    self.toggle_hold()
                    
    def on_release(self, key):
        key_str = self.parse_key(key)
        if key_str in ["ctrl", "shift", "alt", "cmd"]:
            if key_str in self.current_modifiers:
                self.current_modifiers.remove(key_str)
            
        # If we were capturing and released a modifier without pressing a primary key, 
        # allow saving just the modifier if it was the only thing pressed.
        if self.capturing_hotkey and not self.current_modifiers and key_str in ["ctrl", "shift", "alt", "cmd"]:
             self.captured_modifiers = [key_str]
             self.captured_key = ""
             self.capturing_hotkey = False
             self.save_settings()
             self.after(10, self.update_hotkey_ui)

    def toggle_hold(self):
        self.is_holding = not self.is_holding
        
        if self.is_holding:
            if self.target_button == "both":
                self.mouse_controller.press(mouse.Button.left)
                self.mouse_controller.press(mouse.Button.right)
            else:
                self.mouse_controller.press(self.target_button)
            self.after(10, self.update_status, True)
        else:
            if self.target_button == "both":
                self.mouse_controller.release(mouse.Button.left)
                self.mouse_controller.release(mouse.Button.right)
            else:
                self.mouse_controller.release(self.target_button)
            self.after(10, self.update_status, False)
            
    def update_status(self, active):
        if active:
            self.status_label.configure(text="ATIVO (Segurando)", text_color=PRIMARY_COLOR)
        else:
            self.status_label.configure(text="INATIVO", text_color="gray")

    def start_keyboard_listener(self):
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.start()

    def destroy(self):
        # Clean up mouse press if active before exiting
        if self.is_holding:
            if self.target_button == "both":
                self.mouse_controller.release(mouse.Button.left)
                self.mouse_controller.release(mouse.Button.right)
            else:
                self.mouse_controller.release(self.target_button)
        if hasattr(self, 'listener'):
            self.listener.stop()
        super().destroy()

if __name__ == "__main__":
    app = MousePressApp()
    app.mainloop()
