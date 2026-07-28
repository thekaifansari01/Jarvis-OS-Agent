import os
import ctypes
from ctypes import cast, POINTER
import comtypes
from comtypes import CLSCTX_ALL
import pycaw.pycaw as pycaw_module
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import screen_brightness_control as sbc
import traceback
from datetime import datetime
from PIL import ImageGrab

class SystemController:
    @staticmethod
    def _get_audio_interface():
        """Helper to get Windows audio interface safely with COM Threading Fix"""
        comtypes.CoInitialize()  
        
        devices = AudioUtilities.GetSpeakers()
        
        if not hasattr(devices, 'Activate') and hasattr(devices, 'id'):
            devices = pycaw_module.AudioUtilities.CreateDevice(devices.id)
            
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    @staticmethod
    def change_volume(amount: int, relative: bool = True):
        """
        amount: integer (e.g., 10, -20, 50)
        relative: True = Increase/Decrease by amount. False = Set exactly to amount.
        """
        try:
            volume_interface = SystemController._get_audio_interface()
            current_vol = volume_interface.GetMasterVolumeLevelScalar()
            
            if relative:
                new_vol = current_vol + (amount / 100.0)
            else:
                new_vol = amount / 100.0
                
            new_vol = max(0.0, min(1.0, new_vol))
            volume_interface.SetMasterVolumeLevelScalar(new_vol, None)
            
            return f"Volume set to {int(new_vol * 100)}%"
            
        except Exception as pycaw_err:
            if relative:
                try:
                    HWND_BROADCAST = 0xFFFF
                    WM_APPCOMMAND = 0x0319
                    APPCOMMAND_VOLUME_UP = 0x0a0000
                    APPCOMMAND_VOLUME_DOWN = 0x090000
                    
                    steps = abs(amount) // 2 
                    cmd = APPCOMMAND_VOLUME_UP if amount > 0 else APPCOMMAND_VOLUME_DOWN
                    
                    for _ in range(steps):
                        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, cmd)
                    
                    return f"Volume {'increased' if amount > 0 else 'decreased'} natively by ~{abs(amount)}%"
                except Exception as native_err:
                    return f"Volume control fully failed. Pycaw: {pycaw_err} | Native: {native_err}"
            else:
                return f"Volume control error (Absolute setting needs pycaw, try relative commands like 'increase by 10'): {pycaw_err}"

    @staticmethod
    def toggle_speaker_mute():
        """Toggles System Audio (Speakers) Mute State"""
        try:
            volume_interface = SystemController._get_audio_interface()
            is_muted = volume_interface.GetMute()
            volume_interface.SetMute(not is_muted, None)
            state = "Muted" if not is_muted else "Unmuted"
            return f"System speakers are now {state}."
        except Exception as e:
            try:
                HWND_BROADCAST = 0xFFFF
                WM_APPCOMMAND = 0x0319
                APPCOMMAND_VOLUME_MUTE = 0x80000
                ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_MUTE)
                return "System speakers mute state toggled (via fallback)."
            except Exception as native_err:
                return f"Speaker mute error: {str(e)}"

    @staticmethod
    def change_brightness(amount: int, relative: bool = True):
        """
        amount: integer (e.g., 10, -20, 50)
        relative: True = Increase/Decrease by amount. False = Set exactly to amount.
        """
        try:
            current_brightness = sbc.get_brightness()[0] 
            
            if relative:
                new_brightness = current_brightness + amount
            else:
                new_brightness = amount
                
            new_brightness = max(0, min(100, new_brightness))
            sbc.set_brightness(new_brightness)
            
            return f"Brightness set to {new_brightness}%"
        except Exception as e:
            return f"Brightness control error (Might be unsupported on this monitor): {str(e)}"

    @staticmethod
    def lock_pc():
        """Instantly locks the Windows PC (Win + L behavior)"""
        try:
            ctypes.windll.user32.LockWorkStation()
            return "PC Locked successfully."
        except Exception as e:
            return f"Lock error: {str(e)}"

    @staticmethod
    def sleep_pc():
        """Puts the Windows PC to Sleep securely"""
        try:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return "PC put to sleep mode."
        except Exception as e:
            return f"Sleep error: {str(e)}"

    @staticmethod
    def capture_screenshot(filename: str = None, save_dir: str = None):
        try:
            if not save_dir:
                save_dir = "C:/Documents/Jarvis/Screenshots"  
                
            os.makedirs(save_dir, exist_ok=True)
            
            if filename:
                if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    filename += ".png"
                filepath = os.path.join(save_dir, filename)
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(save_dir, f"screenshot_{timestamp}.png")
            
            screenshot = ImageGrab.grab()
            screenshot.save(filepath)
            
            return f"Screenshot saved successfully. Absolute Path: {filepath}"
        except Exception as e:
            return f"Screenshot error: {str(e)}"