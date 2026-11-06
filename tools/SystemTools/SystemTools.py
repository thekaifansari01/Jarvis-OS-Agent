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
from core.logger.logger import logger


class SystemController:
    @staticmethod
    def _get_audio_interface():
        comtypes.CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        if hasattr(devices, '_dev'):
            devices = devices._dev
        elif not hasattr(devices, 'Activate') and hasattr(devices, 'id'):
            devices = pycaw_module.AudioUtilities.CreateDevice(devices.id)
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    @staticmethod
    def change_volume(amount: int, relative: bool = True):
        logger.info(f"🔊 Volume change: amount={amount}, relative={relative}")
        try:
            volume_interface = SystemController._get_audio_interface()
            current_vol = volume_interface.GetMasterVolumeLevelScalar()

            if relative:
                new_vol = current_vol + (amount / 100.0)
            else:
                new_vol = amount / 100.0

            new_vol = max(0.0, min(1.0, new_vol))
            volume_interface.SetMasterVolumeLevelScalar(new_vol, None)
            msg = f"Observation: Success -> Volume set to {int(new_vol * 100)}%."
            logger.info(f"✅ {msg}")
            return msg

        except Exception as pycaw_err:
            logger.warning(f"Pycaw volume error, trying fallback: {pycaw_err}")
            try:
                HWND_BROADCAST = 0xFFFF
                WM_APPCOMMAND = 0x0319
                APPCOMMAND_VOLUME_UP = 0x0a0000
                APPCOMMAND_VOLUME_DOWN = 0x090000

                if relative:
                    steps = abs(amount) // 2
                    cmd = APPCOMMAND_VOLUME_UP if amount > 0 else APPCOMMAND_VOLUME_DOWN
                    for _ in range(max(1, steps)):
                        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, cmd)
                    msg = f"Observation: Success -> Volume {'increased' if amount > 0 else 'decreased'} natively by ~{abs(amount)}%."
                else:
                    steps = int(amount) // 2
                    for _ in range(50):
                        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_DOWN)
                    for _ in range(steps):
                        ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_UP)
                    msg = f"Observation: Success -> Volume reset and set natively to ~{amount}%."

                logger.info(f"✅ {msg}")
                return msg
            except Exception as native_err:
                msg = f"Observation: Error -> Volume control failed. Both Pycaw and native fallback failed. Pycaw error: {pycaw_err} | Native error: {native_err}. Do NOT retry immediately."
                logger.error(msg)
                return msg

    @staticmethod
    def toggle_speaker_mute():
        logger.info("🔇 Toggling speaker mute")
        try:
            volume_interface = SystemController._get_audio_interface()
            is_muted = volume_interface.GetMute()
            volume_interface.SetMute(not is_muted, None)
            state = "Muted" if not is_muted else "Unmuted"
            msg = f"Observation: Success -> System speakers are now {state}."
            logger.info(f"✅ {msg}")
            return msg
        except Exception as e:
            try:
                HWND_BROADCAST = 0xFFFF
                WM_APPCOMMAND = 0x0319
                APPCOMMAND_VOLUME_MUTE = 0x80000
                ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_MUTE)
                msg = "Observation: Success -> System speakers mute state toggled via native fallback."
                logger.info(f"✅ {msg}")
                return msg
            except Exception as native_err:
                msg = f"Observation: Error -> Speaker mute toggle failed: {str(e)}. Native fallback also failed: {native_err}. Do NOT retry."
                logger.error(msg)
                return msg

    @staticmethod
    def change_brightness(amount: int, relative: bool = True):
        logger.info(f"☀️ Brightness change: amount={amount}, relative={relative}")
        try:
            current_brightness = sbc.get_brightness()[0]

            if relative:
                new_brightness = current_brightness + amount
            else:
                new_brightness = amount

            new_brightness = max(0, min(100, new_brightness))
            sbc.set_brightness(new_brightness)
            msg = f"Observation: Success -> Brightness set to {new_brightness}%."
            logger.info(f"✅ {msg}")
            return msg
        except Exception as e:
            msg = f"Observation: Error -> Brightness control failed: {str(e)}. This monitor may not support brightness control. Do NOT retry."
            logger.error(msg)
            return msg

    @staticmethod
    def lock_pc():
        logger.info("🔒 Locking PC")
        try:
            ctypes.windll.user32.LockWorkStation()
            msg = "Observation: Success -> PC locked successfully."
            logger.info(f"✅ {msg}")
            return msg
        except Exception as e:
            msg = f"Observation: Error -> PC lock failed: {str(e)}. Do NOT retry."
            logger.error(msg)
            return msg

    @staticmethod
    def sleep_pc():
        logger.info("💤 Putting PC to sleep")
        try:
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            msg = "Observation: Success -> PC put to sleep."
            logger.info(f"✅ {msg}")
            return msg
        except Exception as e:
            msg = f"Observation: Error -> PC sleep failed: {str(e)}. Do NOT retry."
            logger.error(msg)
            return msg

    @staticmethod
    def capture_screenshot(filename: str = None, save_dir: str = None):
        logger.info(f"📸 Capturing screenshot, filename={filename}, save_dir={save_dir}")
        try:
            if not save_dir:
                save_dir = "C:/Documents/Jarvis/Screenshots"

            if filename:
                clean_filename = filename.replace("/", os.sep).replace("\\", os.sep)
                if not clean_filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    clean_filename += ".png"

                if os.path.isabs(clean_filename):
                    filepath = clean_filename
                else:
                    filepath = os.path.join(save_dir, clean_filename)
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(save_dir, f"screenshot_{timestamp}.png")

            parent_dir = os.path.dirname(filepath)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            screenshot = ImageGrab.grab()
            screenshot.save(filepath)

            msg = f"Observation: Success -> Screenshot saved at absolute path: {filepath}."
            logger.info(f"✅ {msg}")
            return msg
        except Exception as e:
            msg = f"Observation: Error -> Screenshot failed: {str(e)}. Check write permissions on save directory."
            logger.error(msg)
            return msg