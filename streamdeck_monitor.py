import os
import threading
import time
import math
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageGrab
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from StreamDeck.Transport.Transport import TransportError

DEFAULT_FPS = 20.0      


try:
    import pyautogui
    MOUSE_AVAILABLE = True
    pyautogui.FAILSAFE = False
except ImportError:
    MOUSE_AVAILABLE = False
    print("Warning: pyautogui not installed. Mouse control will be disabled.")
    print("Install with: pip install pyautogui")

class StreamDeckMonitor:
    def __init__(self):
        self.deck = None
        self.running = False
        self.update_thread = None
        self.refresh_rate = DEFAULT_FPS 
        self.screen_regions = []
        self.mouse_enabled = MOUSE_AVAILABLE 
        
    def setup_deck(self):
        streamdecks = DeviceManager().enumerate()
        
        if not streamdecks:
            print("No Stream Deck found!")
            return False
            
        self.deck = streamdecks[0]
        
        if not self.deck.is_visual():
            print("Stream Deck doesn't have screens!")
            return False
            
        self.deck.open()
        self.deck.reset()
        
        print(f"Opened '{self.deck.deck_type()}' device (serial: '{self.deck.get_serial_number()}')")
        print(f"Key layout: {self.deck.key_layout()[0]}x{self.deck.key_layout()[1]} = {self.deck.key_count()} keys")
        print(f"Key image format: {self.deck.key_image_format()}")
        
        self.deck.set_brightness(80)
        
        screen = ImageGrab.grab()
        print(f"Screen resolution: {screen.size[0]}x{screen.size[1]}")
        
        self.calculate_screen_regions()
        
        return True
    
    def calculate_screen_regions(self):
        if not self.deck:
            return
            
        screen = ImageGrab.grab()
        screen_width, screen_height = screen.size

        key_count = self.deck.key_count()
        key_cols = self.deck.key_layout()[0]  
        key_rows = self.deck.key_layout()[1]  
        print(f"Screen: {screen_width}x{screen_height}, Deck: {key_cols}x{key_rows} ({key_count} keys)")
        

        display_width = screen_width
        display_height = screen_height
        offset_x = 0
        offset_y = 0
        
        screen_cols = 5  
        screen_rows = 3  
        
        
        region_width = display_width / screen_cols
        region_height = display_height / screen_rows
        
        print(f"Screen grid: {screen_cols}x{screen_rows}, Region size per area: {region_width:.1f}x{region_height:.1f}")
        
        self.screen_regions = []
        
        key_to_screen_mapping = {
            0: (0, 0),   
            1: (1, 0),   
            2: (2, 0),   
            3: (3, 0),   
            4: (4, 0),   
            
            5: (0, 1),   
            6: (1, 1),   
            7: (2, 1),   
            8: (3, 1),   
            9: (4, 1),   
            
            10: (0, 2),  
            11: (1, 2),  
            12: (2, 2),  
            13: (3, 2),  
            14: (4, 2),  
        }
        
        for key in range(key_count):
            if key in key_to_screen_mapping:
                screen_col, screen_row = key_to_screen_mapping[key]
                
                x1 = int(offset_x + screen_col * region_width)
                y1 = int(offset_y + screen_row * region_height)
                x2 = int(offset_x + (screen_col + 1) * region_width)
                y2 = int(offset_y + (screen_row + 1) * region_height)
                
                x1 = max(0, min(x1, screen_width))
                y1 = max(0, min(y1, screen_height))
                x2 = max(0, min(x2, screen_width))
                y2 = max(0, min(y2, screen_height))
                
                self.screen_regions.append((x1, y1, x2, y2))
                
                region_w = x2 - x1
                region_h = y2 - y1
                print(f"Key {key} -> Screen({screen_col},{screen_row}): ({x1},{y1})-({x2},{y2}) [{region_w}x{region_h}]")
            else:
                self.screen_regions.append((0, 0, 100, 100))
                print(f"Key {key}: Unknown mapping, using fallback")
            
        print(f"Configured {len(self.screen_regions)} screen regions for {key_count} keys")
        print("Korrekte Zuordnung: Bildschirm horizontal gestreckt auf 5x3 Raster")

    def click_screen_region(self, key_index: int):
        if not self.mouse_enabled:
            print("Mouse control is disabled")
            return
            
        if key_index >= len(self.screen_regions):
            print(f"Invalid key index: {key_index}")
            return
            
        region = self.screen_regions[key_index]
        x1, y1, x2, y2 = region
        
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        
        try:
            print(f"Moving mouse to ({center_x}, {center_y}) and clicking...")
            
            pyautogui.moveTo(center_x, center_y, duration=0.2)
            
            time.sleep(0.1)
            
            pyautogui.click()
            
            print(f"Clicked at ({center_x}, {center_y}) for key {key_index}")
            
        except Exception as e:
            print(f"Error clicking at ({center_x}, {center_y}): {e}")
            
    def change_refresh_rate(self, new_rate: float):
        if new_rate > 0:
            self.refresh_rate = new_rate
            print(f"Refresh rate changed to {new_rate} FPS")
        else:
            print("Invalid refresh rate")
            
    def capture_key_region(self, key_index: int) -> Optional[Image.Image]:
        if key_index >= len(self.screen_regions):
            return None
            
        region = self.screen_regions[key_index]
        
        try:
            screenshot = ImageGrab.grab(bbox=region)
            
            key_width = self.deck.key_image_format()['size'][0]
            key_height = self.deck.key_image_format()['size'][1]
            
            screenshot_resized = screenshot.resize((key_width, key_height), Image.Resampling.LANCZOS)
            
            return PILHelper.to_native_key_format(self.deck, screenshot_resized)
            
        except Exception as e:
            print(f"Error capturing region for key {key_index}: {e}")
            return None
    
    def update_all_keys(self):
        if not self.deck:
            return
            
        with self.deck:
            for key in range(self.deck.key_count()):
                key_image = self.capture_key_region(key)
                if key_image:
                    self.deck.set_key_image(key, key_image)
    
    def monitor_loop(self):
        print(f"Starting monitor loop with {self.refresh_rate} FPS")
        
        while self.running:
            start_time = time.time()
            
            self.update_all_keys()
            
            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / self.refresh_rate) - elapsed)
            
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def key_change_callback(self, deck, key, state):
        if state:
            print(f"Key {key} pressed")
            
            if key < len(self.screen_regions):
                region = self.screen_regions[key]
                print(f"Key {key} -> Screen region: {region}")
            
            if key == 0:
                rates = [0.5, 1.0, 2.0, 5.0, 10.0]
                current_index = rates.index(self.refresh_rate) if self.refresh_rate in rates else 2
                next_index = (current_index + 1) % len(rates)
                self.refresh_rate = rates[next_index]
                print(f"Refresh rate changed to {self.refresh_rate} FPS")
            
            else:
                if self.mouse_enabled:
                    self.click_screen_region(key)
                else:
                    print(f"Key {key} pressed - mouse control not available")
        
        else:
            print(f"Key {key} released")
    
    def start(self):
        if not self.setup_deck():
            return False
            
        self.deck.set_key_callback(self.key_change_callback)
        
        self.running = True
        
        self.update_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.update_thread.start()
        
        print("Stream Deck Monitor started!")
        print("Configuration:")
        print(f"- FPS: {self.refresh_rate}")
        print(f"- Mouse Control: {'ENABLED' if self.mouse_enabled else 'DISABLED'}")
        print()
        print("Controls:")
        print("- Key 0: Cycle refresh rate (0.5, 1.0, 2.0, 5.0, 10.0 FPS)")
        print("- All other keys: Click in corresponding screen area")
        print("- Layout: Screen horizontally stretched and divided into 5x3 grid")
        print()
        if self.mouse_enabled:
            print("MOUSE CONTROL: Pressing keys will move mouse and click in corresponding screen area")
        if not MOUSE_AVAILABLE:
            print("WARNING: pyautogui not installed - mouse control unavailable")
        
        return True
    
    def stop(self):
        self.running = False
        
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2.0)
        
        if self.deck:
            with self.deck:
                self.deck.reset()
                self.deck.close()
        
        print("Stream Deck Monitor stopped")
    
    def run(self):
        if not self.start():
            return
            
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received")
        finally:
            self.stop()


def main():
    print("Stream Deck Windows Monitor (Mouse Control Only)")
    print("=" * 40)
    
    monitor = StreamDeckMonitor()
    monitor.run()


if __name__ == "__main__":
    main()