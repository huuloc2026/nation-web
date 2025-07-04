import json
import logging
import threading
import time
from collections import deque
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
# 'serial' and 'serial.tools.list_ports' are imported, but 'serial' itself isn't directly used
# for the reader object, as NationReader handles the low-level serial communication.
# 'list_ports' isn't used in the provided code, but kept if you use it elsewhere.
import serial 
from serial.tools import list_ports 

# Import configuration
from config import get_config

# Nation reader module
from nation import NationReader

# --- Global Configuration & App Initialization ---

# Load application configuration based on FLASK_ENV
config = get_config()

# Initialize Flask app
app = Flask(__name__)
# Load configuration from the Config object
app.config.from_object(config)
# Enable Cross-Origin Resource Sharing for the Flask app
CORS(app)  
# Initialize Flask-SocketIO for real-time communication
socketio = SocketIO(
    app, 
    cors_allowed_origins=config.SOCKETIO_CORS_ALLOWED_ORIGINS, 
    async_mode=config.SOCKETIO_ASYNC_MODE, 
    logger=False, # Flask-SocketIO's own logger is often too verbose
    engineio_logger=False # Engine.IO's logger is also often too verbose
)

# --- Global Variables for Application State ---

# The NationReader instance, accessible globally for convenience (e.g., by helper functions)
# and managed by RFIDWebController.
reader: Optional[NationReader] = None 
# Thread for managing ongoing RFID inventory operations
inventory_thread: Optional[threading.Thread] = None
# Flag to signal the inventory thread to stop gracefully
stop_inventory_flag: bool = False
# A deque (double-ended queue) to store detected tags, with a max length
# This efficiently handles adding/removing tags for display without re-allocating large lists.
detected_tags: deque = deque(maxlen=config.MAX_TAGS_DISPLAY)
# Dictionary to hold overall inventory statistics (e.g., read rate, total count)
inventory_stats: Dict[str, int] = {"read_rate": 0, "total_count": 0}
# Set to keep track of connected WebSocket client SIDs
connected_clients: set = set()

# --- Logging Configuration ---

# Configure the root logger for the application
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL), # Set log level from config (e.g., INFO, DEBUG)
    format=config.LOG_FORMAT # Set log message format from config
)
# Get a logger instance for this module (app.py)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def _get_reader_instance() -> Optional[NationReader]:
    """
    Safely retrieves the global NationReader instance.
    This helper makes sure we're always working with the current reader.
    """
    return globals().get('reader')

def _get_profile_from_reader(nation_reader: NationReader) -> Optional[Dict]:
    """
    Retrieves the full operational profile data from the NationReader.
    This includes antenna settings, power, baseband, etc.
    """
    try:
        profile = nation_reader.GetProfile()
        if profile and isinstance(profile, dict) and not profile.get("error"):
            logger.debug(f"Reader profile retrieved: {profile}")
            return profile
        logger.error(f"Failed to retrieve profile or profile has errors: {profile}")
        return None
    except Exception as e:
        logger.error(f"Error getting reader profile: {e}")
        return None

def _set_profile_on_reader(nation_reader: NationReader, profile_num: int, save_on_power_down: bool) -> bool:
    """
    Sets a specific predefined operational profile on the NationReader.
    This function configures baseband settings based on `config.PROFILE_CONFIGS`.
    """
    profile_data = config.PROFILE_CONFIGS.get(profile_num)
    if not profile_data:
        logger.error(f"Invalid profile number '{profile_num}'. Not found in config.PROFILE_CONFIGS.")
        return False

    try:
        # Configure baseband parameters as part of the profile setting
        configured_baseband = nation_reader.configure_baseband(
            speed=profile_data.get("speed", 255), # Default speed if not in profile_data
            q_value=profile_data.get("q_value", config.DEFAULT_Q_VALUE), # Use config default if not in profile
            session=profile_data.get("session", config.DEFAULT_SESSION),
            inventory_flag=profile_data.get("inventory_flag", 0)
        )
        if not configured_baseband:
            logger.error(f"Failed to configure baseband for profile {profile_num}.")
            return False

        # Attempt to select the profile, assuming `nation_reader.select_profile`
        # handles activating and potentially saving this profile as the active one.
        # Note: Your `nation.py` `select_profile` doesn't currently take `save_on_power_down`.
        # If persistence is needed here, the NationReader method might need modification.
        selected = nation_reader.select_profile(profile_num)
        if not selected:
            logger.error(f"Failed to select profile {profile_num} on reader.")
            return False

        logger.info(f"Successfully applied profile {profile_num} to reader.")
        return True
    except Exception as e:
        logger.error(f"Error setting profile {profile_num} on reader: {e}")
        return False


class RFIDWebController:
    def __init__(self):
        # Internal NationReader instance, managed by the controller
        self._reader_instance: Optional[NationReader] = None 
        # Connection status flag
        self.is_connected: bool = False
        # Cached current reader profile data
        self.current_profile: Optional[Dict] = None 
        # Cached current antenna power settings
        self.antenna_power: Dict[int, int] = {} 
        
    def connect(self, port: str, baudrate: Optional[int] = None) -> Dict:
        """
        Establishes a connection to the RFID reader.
        If a connection already exists, it attempts to disconnect first.
        """
        # Access the global reader variable to synchronize state
        global reader 

        # Use default baudrate from config if not provided
        if baudrate is None:
            baudrate = config.DEFAULT_BAUDRATE
        
        logger.info(f"Attempting to connect to RFID reader on {port} at {baudrate} bps.")
        try:
            # If already connected, disconnect cleanly before establishing a new connection
            if self.is_connected and self._reader_instance:
                logger.info("Existing reader connection found, attempting to disconnect first for a clean reconnect.")
                self.disconnect() 
                time.sleep(0.1) # Small delay for cleanup

            # Create a new NationReader instance and open the connection
            self._reader_instance = NationReader(port, baudrate)
            self._reader_instance.open()
            self.is_connected = True
            # Update the global reader instance for access by other parts of the app
            reader = self._reader_instance 
            logger.info(f"Successfully connected to RFID reader on {port}.")
            return {"success": True, "message": f"Đã kết nối thành công đến {port}"}
        except Exception as e:
            logger.error(f"Connection error to {port}: {e}")
            # Ensure state is reset on failure
            self.is_connected = False
            self._reader_instance = None
            reader = None 
            return {"success": False, "message": f"Lỗi kết nối: {str(e)}"}

    def disconnect(self) -> Dict:
        """
        Terminates the connection to the RFID reader.
        Ensures any ongoing inventory is stopped before closing the port.
        """
        global reader # Access the global reader variable
        logger.info("Attempting to disconnect from RFID reader.")
        try:
            if self._reader_instance:
                # Stop any active inventory thread before disconnecting the reader
                if inventory_thread and inventory_thread.is_alive():
                    logger.info("Inventory thread is active, attempting to stop it before disconnection.")
                    self.stop_inventory() 
                    time.sleep(0.5) # Allow time for the thread to stop

                self._reader_instance.close() # Close the serial port
            
            # Reset controller and global state
            self.is_connected = False
            self._reader_instance = None
            reader = None 
            logger.info("Disconnected from RFID reader.")
            return {"success": True, "message": "Đã ngắt kết nối"}
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
            return {"success": False, "message": f"Lỗi ngắt kết nối: {str(e)}"}
    
    def get_reader_info(self) -> Dict:
        """
        Retrieves general information about the RFID reader (e.g., serial number, firmware).
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            info = self._reader_instance.Query_Reader_Information()
            if info and isinstance(info, dict) and info:
                logger.info("Reader information retrieved successfully.")
                # You can log individual info items at DEBUG level if needed
                # for k, v in info.items():
                #     logger.debug(f"  {k}: {v}")
                return {"success": True, "data": info}  
            else:
                logger.warning("Could not retrieve reader information or the response was empty/invalid.")
                return {"success": False, "message": "Không thể lấy thông tin reader hoặc thông tin rỗng"}
        except Exception as e:
            logger.error(f"Error getting reader information: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def configure_baseband(self, speed: int, q_value: int, session: int, inventory_flag: int) -> Dict:
        """
        Configures the baseband parameters of the RFID reader, affecting tag reading performance.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            # Delegate the configuration to the NationReader instance
            ok = self._reader_instance.configure_baseband(speed, q_value, session, inventory_flag)
            if ok:
                logger.info(f"Baseband configured successfully: Speed={speed}, Q={q_value}, Session={session}, Flag={inventory_flag}.")
                return {"success": True, "message": "Đã cấu hình baseband thành công"}
            else:
                logger.warning(f"Failed to configure baseband with parameters: Speed={speed}, Q={q_value}, Session={session}, Flag={inventory_flag}.")
                return {"success": False, "message": "Không thể cấu hình baseband"}
        except Exception as e:
            logger.error(f"Error configuring baseband: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def query_baseband_profile(self) -> Dict:
        """
        Queries and retrieves the current baseband profile settings from the reader.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            info = self._reader_instance.query_baseband_profile()
            if info:
                logger.info(f"Baseband profile queried: {info}.")
                return {"success": True, "data": info}
            else:
                logger.warning("Could not retrieve baseband profile.")
                return {"success": False, "message": "Không thể lấy thông tin baseband"}
        except Exception as e:
            logger.error(f"Error querying baseband profile: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def start_inventory(self, antenna_mask) -> Dict:
        """
        Initiates a continuous RFID tag inventory process on the reader.
        This spawns a background thread to handle tag callbacks.
        """
        # Access global variables for thread management and shared data
        global inventory_thread, stop_inventory_flag, detected_tags, inventory_stats

        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        # Prevent starting multiple inventory threads concurrently
        if inventory_thread and inventory_thread.is_alive():
            logger.warning("Inventory thread is already running. Ignoring new start request.")
            return {"success": False, "message": "Inventory đang chạy"}

        try:
            # Reset state for a new inventory session
            stop_inventory_flag = False 
            detected_tags.clear() # Clear tags from previous runs
            inventory_stats = {"read_rate": 0, "total_count": 0} # Reset statistics

            # Flush input buffer to clear any old data before starting
            try:
                self._reader_instance.uart.flush_input()
            except Exception as e:
                logger.warning(f"Buffer clear warning during start_inventory: {e}")

            def tag_callback(tag_data: Dict) -> None:
                """
                Callback function executed by the NationReader when a new tag is detected.
                It logs the tag, adds it to the `detected_tags` deque, and emits it via WebSocket.
                """
                logger.info(f"🔍 Tag detected: EPC={tag_data.get('epc')}, RSSI={tag_data.get('rssi')}, Antenna={tag_data.get('antenna_id')}, TS={tag_data.get('timestamp')}")
                
                # Add tag to the deque; `maxlen` handles automatic popping of old tags
                detected_tags.append(tag_data)
                
                # Update total tag count
                inventory_stats["total_count"] += 1

                # Emit tag data to all connected WebSocket clients
                try:
                    socketio.emit('tag_detected', tag_data)
                except Exception as e:
                    logger.error(f"❌ WebSocket emit failed in tag_callback: {e}")

            def inventory_worker() -> None:
                """
                Background worker thread function that runs the RFID inventory loop.
                It calls the NationReader's inventory method with the tag callback.
                """
                logger.info("Inventory worker thread started.")
                try:         
                    # Start inventory using the NationReader's method.
                    # This call is expected to block until inventory is explicitly stopped
                    # or an end condition is met internally by NationReader.
                    self._reader_instance.start_inventory_with_mode(
                        antenna_mask=[1],
                        callback=tag_callback
                    )
                except Exception as e:
                    logger.error(f"Inventory worker encountered an unhandled error: {e}")
                finally:
                    logger.info("Inventory worker thread finished.")

            # Create and start the inventory thread as a daemon so it exits with the main app
            inventory_thread = threading.Thread(target=inventory_worker, daemon=True)
            inventory_thread.start()

            logger.info("RFID inventory process successfully started in a background thread.")
            return {"success": True, "message": "Inventory đã bắt đầu"}
        except Exception as e:
            logger.error(f"Error initiating inventory: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def stop_inventory(self) -> Dict:
        """
        Stops the ongoing RFID tag inventory process.
        It signals the background thread to stop and sends a stop command to the reader.
        """
        # Access global variables for thread management
        global stop_inventory_flag, inventory_thread 
        
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        logger.info("Attempting to stop RFID inventory.")
        try:
            # Set the flag to signal the inventory worker thread to terminate
            stop_inventory_flag = True
            
            # Send the stop command to the physical reader
            # The NationReader.stop_inventory method is designed to handle retries and confirmation.
            if not self._reader_instance.stop_inventory():
                logger.warning("NationReader.stop_inventory command reported no clear success or encountered an issue.")
                # We'll still proceed to try and join the thread.
            
            # Wait for the inventory worker thread to complete its execution
            if inventory_thread and inventory_thread.is_alive():
                logger.info("Waiting for the inventory worker thread to terminate (max 3 seconds).")
                inventory_thread.join(timeout=3.0) 
                if inventory_thread.is_alive():
                    logger.warning("Inventory thread did not terminate within the specified timeout. It might be stuck.")
                    # In a production system, you might implement more aggressive cleanup or alerts here.
            else:
                logger.info("No active inventory thread found to join.")
            
            logger.info("RFID inventory process successfully stopped.")
            return {"success": True, "message": "Đã dừng inventory"}
        except Exception as e:
            logger.error(f"Error stopping inventory: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def set_power(self, antenna_powers: Dict[int, int], preserve_config: bool = True) -> Dict:
        """
        Configures the RF transmit power levels for specified antenna ports.
        Allows setting power for multiple antennas at once.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        # Validate power levels against configured min/max ranges
        for ant, power in antenna_powers.items():
            if not config.POWER_MIN_DBM <= power <= config.POWER_MAX_DBM:
                return {"success": False, "message": f"Công suất Antenna {ant} ({power} dBm) phải nằm trong khoảng từ {config.POWER_MIN_DBM} đến {config.POWER_MAX_DBM} dBm."}
        
        try:
            # Delegate the power configuration to the NationReader
            result = self._reader_instance.configure_reader_power(antenna_powers, persistence=preserve_config)
            
            if result:
                logger.info(f"Set power successfully for antennas: {antenna_powers} dBm. Persistence: {preserve_config}.")
                # Update the controller's cached antenna power by querying the reader again
                self.antenna_power = self._reader_instance.query_reader_power() 
                return {"success": True, "message": f"Đã thiết lập công suất: {antenna_powers} dBm"}
            else:
                logger.warning(f"Failed to set power for antennas: {antenna_powers} dBm.")
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Error setting power for antennas {antenna_powers}: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def get_antenna_power(self) -> Dict:
        """
        Retrieves the current RF transmit power settings for all available antenna ports.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        logger.info("Attempting to retrieve current antenna power settings.")
        try:
            power_levels = self._reader_instance.query_reader_power()
            if power_levels:
                self.antenna_power = power_levels # Cache the retrieved power levels
                logger.info(f"Retrieved antenna power levels: {power_levels}.")
                # You can log each antenna's power at DEBUG level for detail
                # for ant, val in power_levels.items():
                #     logger.debug(f"  🔧 Antenna {ant}: {val} dBm")
                return {"success": True, "data": power_levels}
            else:
                logger.warning("Could not retrieve antenna power levels. Response was empty.")
                return {"success": False, "message": "Không thể lấy công suất antennas"}
        except Exception as e:
            logger.error(f"Error getting antenna power: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
  
    def set_buzzer(self, enable: bool) -> Dict:
        """
        Controls the reader's built-in buzzer (on/off).
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            # Convert boolean 'enable' to the appropriate mode for NationReader.set_beeper:
            # 1 = continuous beep, 0 = off.
            # Mode 2 ("beep on new tag") would require a separate explicit parameter if desired.
            mode = 1 if enable else 0 
            result = self._reader_instance.set_beeper(mode)
            if result:
                status_msg = "bật" if enable else "tắt"
                logger.info(f"Buzzer {'enabled' if enable else 'disabled'} (mode {mode}).")
                return {"success": True, "message": f"Đã {status_msg} buzzer"}
            else:
                logger.warning(f"Failed to set buzzer to mode {mode}.")
                return {"success": False, "message": "Không thể thiết lập buzzer"}
        except Exception as e:
            logger.error(f"Error setting buzzer: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def get_current_profile_data(self) -> Dict:
        """
        Retrieves the complete current operational profile of the reader.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        logger.info("Attempting to retrieve current reader profile data.")
        try:
            # Use the helper function to get the profile from NationReader
            profile_data = _get_profile_from_reader(self._reader_instance) 
            if profile_data is not None:
                self.current_profile = profile_data # Cache the retrieved profile
                logger.info(f"Current profile data retrieved: {profile_data}.")
                return {"success": True, "data": {"profile": profile_data}}
            else:
                logger.warning("Could not retrieve current profile data from reader.")
                return {"success": False, "message": "Không thể lấy profile"}
        except Exception as e:
            logger.error(f"Error getting current profile data: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def set_profile_by_number(self, profile_num: int, save_on_power_down: bool = True) -> Dict:
        """
        Sets the reader's operational profile based on a predefined profile number
        from the application's configuration.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        # Validate if the profile number exists in the config
        if profile_num not in config.PROFILE_CONFIGS:
            return {"success": False, "message": f"Profile số {profile_num} không hợp lệ hoặc không có trong cấu hình."}
        
        logger.info(f"Attempting to set reader profile to number {profile_num}. Save on power down: {save_on_power_down}.")
        try:
            # Use the helper function to apply the profile configuration to the NationReader
            result = _set_profile_on_reader(self._reader_instance, profile_num, save_on_power_down) 
            if result:
                # After successfully setting, update the cached profile by querying the reader
                self.current_profile = _get_profile_from_reader(self._reader_instance) 
                logger.info(f"Profile successfully set to {profile_num}.")
                return {"success": True, "message": f"Đã thiết lập profile: {profile_num}"}
            else:
                logger.warning(f"Failed to set profile to number {profile_num}.")
                return {"success": False, "message": "Không thể thiết lập profile"}
        except Exception as e:
            logger.error(f"Error setting profile {profile_num}: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def enable_antennas(self, antennas: List[int], save_on_power_down: bool = True) -> Dict:
        """
        Enables a list of specified antenna ports on the reader.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        # Validate antenna IDs against the maximum supported antennas from config
        if not all(1 <= ant <= config.MAX_ANTENNAS for ant in antennas):
            return {"success": False, "message": f"Antenna ID phải nằm trong khoảng từ 1 đến {config.MAX_ANTENNAS}."}

        logger.info(f"Attempting to enable antennas: {antennas}. Save on power down: {save_on_power_down}.")
        try:
            success_count = 0
            for ant_id in antennas:
                if self._reader_instance.enable_ant(ant_id, save_on_power_down):
                    success_count += 1
                else:
                    logger.warning(f"Failed to enable antenna {ant_id}.")
            
            if success_count == len(antennas):
                logger.info(f"All specified antennas ({antennas}) enabled successfully.")
                return {"success": True, "message": f"Đã bật antennas: {antennas}"}
            elif success_count > 0:
                logger.warning(f"Partially enabled antennas: {success_count} out of {len(antennas)} succeeded.")
                return {"success": True, "message": f"Đã bật một số antennas ({success_count}/{len(antennas)})"}
            else:
                logger.error(f"Failed to enable any of the antennas in the list: {antennas}.")
                return {"success": False, "message": f"Không thể bật bất kỳ antennas nào trong danh sách: {antennas}"}
        except Exception as e:
            logger.error(f"Error enabling antennas {antennas}: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def disable_antennas(self, antennas: List[int], save_on_power_down: bool = True) -> Dict:
        """
        Disables a list of specified antenna ports on the reader.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        # Validate antenna IDs
        if not all(1 <= ant <= config.MAX_ANTENNAS for ant in antennas):
            return {"success": False, "message": f"Antenna ID phải nằm trong khoảng từ 1 đến {config.MAX_ANTENNAS}."}

        logger.info(f"Attempting to disable antennas: {antennas}. Save on power down: {save_on_power_down}.")
        try:
            success_count = 0
            for ant_id in antennas:
                if self._reader_instance.disable_ant(ant_id, save_on_power_down):
                    success_count += 1
                else:
                    logger.warning(f"Failed to disable antenna {ant_id}.")
            
            if success_count == len(antennas):
                logger.info(f"All specified antennas ({antennas}) disabled successfully.")
                return {"success": True, "message": f"Đã tắt antennas: {antennas}"}
            elif success_count > 0:
                logger.warning(f"Partially disabled antennas: {success_count} out of {len(antennas)} succeeded.")
                return {"success": True, "message": f"Đã tắt một số antennas ({success_count}/{len(antennas)})"}
            else:
                logger.error(f"Failed to disable any of the antennas in the list: {antennas}.")
                return {"success": False, "message": f"Không thể tắt bất kỳ antennas nào trong danh sách: {antennas}"}
        except Exception as e:
            logger.error(f"Error disabling antennas {antennas}: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
        
    def set_power_for_antenna(self, antenna: int, power: int, preserve_config: bool = True) -> Dict:
        """
        Sets the RF transmit power for a single, specific antenna port.
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        # Validate antenna power against configured range
        if not config.POWER_MIN_DBM <= power <= config.POWER_MAX_DBM: 
            return {"success": False, "message": f"Công suất ({power} dBm) phải nằm trong khoảng từ {config.POWER_MIN_DBM} đến {config.POWER_MAX_DBM} dBm."}
        
        logger.info(f"Attempting to set power for antenna {antenna} to {power} dBm. Persistence: {preserve_config}.")
        try:
            result = self._reader_instance.configure_reader_power({antenna: power}, persistence=preserve_config)
            if result:
                logger.info(f"Power for antenna {antenna} successfully set to {power} dBm.")
                return {"success": True, "message": f"Đã thiết lập công suất Antenna {antenna}: {power} dBm"}
            else:
                logger.warning(f"Failed to set power for antenna {antenna} to {power} dBm.")
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Error setting power for antenna {antenna}: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
        
    def set_power_multi(self, powers: Dict[str, int], preserve_config: bool = True) -> Dict:
        """
        Sets the RF transmit power for multiple antenna ports at once.
        Input `powers` dict has string keys (antenna IDs) and integer values (power).
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        logger.info(f"Attempting to set power for multiple antennas: {powers}. Persistence: {preserve_config}.")
        try:
            # Convert string keys (from JSON) to integer antenna IDs
            powers_int: Dict[int, int] = {}
            for k_str, v_val in powers.items():
                try:
                    ant_id = int(k_str)
                    power_val = int(v_val) # Ensure power value is an integer
                    # Validate power value against configured range
                    if not config.POWER_MIN_DBM <= power_val <= config.POWER_MAX_DBM:
                         return {"success": False, "message": f"Công suất Antenna {ant_id} ({power_val} dBm) phải nằm trong khoảng từ {config.POWER_MIN_DBM} đến {config.POWER_MAX_DBM} dBm."}
                    powers_int[ant_id] = power_val
                except ValueError:
                    return {"success": False, "message": f"Antenna ID '{k_str}' hoặc giá trị công suất '{v_val}' không hợp lệ. Vui lòng kiểm tra định dạng."}

            # Delegate to NationReader's configure_reader_power
            result = self._reader_instance.configure_reader_power(powers_int, persistence=preserve_config)
            if result:
                logger.info(f"Power successfully set for multiple antennas: {powers_int}.")
                return {"success": True, "message": "Đã thiết lập công suất cho tất cả antennas"}
            else:
                logger.warning(f"Failed to set power for multiple antennas: {powers_int}.")
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Error setting power for multiple antennas: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def write_to_target_tag(
        self,
        target_tag_epc: str,
        new_epc_hex: str,
        access_pwd: Optional[int] = None,
        overwrite_pc: bool = False,
        prefix_words: int = 0,
        timeout: float = 2.0,
        scan_timeout: float = 2.0, # This parameter needs to be handled by `NationReader`'s method if it's external to write_epc_tag_auto.
    ) -> Dict:
        """
        Scans for a tag with a specific `target_tag_epc` and then attempts to write
        a `new_epc_hex` value to it.
        This function delegates to `NationReader.write_epc_to_target_auto`
        (which was the translated method from your original Python `NationReader`).
        """
        if not self.is_connected or not self._reader_instance:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        logger.info(f"Attempting to write EPC '{new_epc_hex}' to target tag '{target_tag_epc}'.")
        try:
            # The `NationReader.write_epc_to_target_auto` method in the translated code
            # directly handles the scanning and writing.
            # `target_tag_epc` here is the *match_epc* for the write operation.
            # `new_epc_hex` is the *new_epc_hex* to be written.
            
            # Note: `write_epc_to_target_auto` in the previous translation takes `antenna_id`
            # and `timeout` directly, but `scan_timeout` was not a direct parameter in that specific function.
            # If `scan_timeout` is meant to control the initial scan to *find* the tag,
            # that logic would either need to be inside `write_epc_to_target_auto` or
            # implemented *before* calling it (e.g., using a separate inventory scan).
            # For now, I'm passing `timeout` to the `write_epc_to_target_auto` which is for the write response.
            
            # Assuming `write_epc_to_target_auto` from the `nationreader.py` (translated)
            # is the method to use, it expects: (new_epc_hex, match_epc_hex, antenna_id, access_password, timeout)
            result = self._reader_instance.write_epc_to_target_auto(
                new_epc_hex=new_epc_hex,
                match_epc_hex=target_tag_epc, # This is the EPC the tag must currently have to be written
                antenna_id=config.DEFAULT_ANTENNA_ID, # Assuming default antenna for writing, or pass from UI
                access_password=access_pwd,
                timeout=timeout,
            )
            
            # The result from NationReader.write_epc_to_target_auto should always be a dict
            if result is None: 
                logger.error("NationReader.write_epc_to_target_auto returned None (unexpected).")
                return {"success": False, "message": "Không thể ghi EPC vào tag: Phản hồi từ reader không hợp lệ."}
            
            logger.info(f"Write EPC operation result: {result.get('result_msg')}")
            return result
        except Exception as e:
            logger.error(f"Error writing to target tag '{target_tag_epc}' with new EPC '{new_epc_hex}': {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    

# Initialize the RFID controller instance
rfid_controller = RFIDWebController()

@app.route('/')
def index() -> str:
    """Renders the main HTML page of the application."""
    return render_template('index.html', config=config)

@app.route('/api/connect', methods=['POST'])
def api_connect() -> Dict:
    """
    API endpoint to establish a connection to the RFID reader.
    Expects JSON body: `{'port': '/dev/ttyUSB0', 'baudrate': 115200}`.
    """
    data = request.get_json()
    # Use config.DEFAULT_SERIAL_PORT for consistency with the config.py definition
    port = data.get('port', config.DEFAULT_SERIAL_PORT) 
    baudrate = data.get('baudrate', config.DEFAULT_BAUDRATE)
    
    logger.info(f"API Connect request received: Port='{port}', Baudrate={baudrate}.")
    result = rfid_controller.connect(port, baudrate)
    return jsonify(result)

@app.route('/api/disconnect', methods=['POST'])
def api_disconnect() -> Dict:
    """
    API endpoint to terminate the connection with the RFID reader.
    """
    logger.info("API Disconnect request received.")
    result = rfid_controller.disconnect()
    return jsonify(result)

@app.route('/api/reader_info', methods=['GET'])
def api_reader_info() -> Dict:
    """
    API endpoint to retrieve general information about the connected RFID reader.
    """
    logger.info("API Get Reader Info request received.")
    result = rfid_controller.get_reader_info()
    return jsonify(result)

@app.route('/api/start_inventory', methods=['POST'])
def api_start_inventory() -> Dict:
    """
    API endpoint to start a general RFID tag inventory.
    Expects JSON body: `{'selectedAntennas': [1, 2]}` (list of 1-based antenna IDs).
    """
    data = request.get_json()
    # Expects a list of antenna IDs, default to [1] if not provided
    selected_antennas_raw = data.get('selectedAntennas', [config.DEFAULT_ANTENNA_ID]) 
    
    if not rfid_controller.is_connected or not _get_reader_instance():
        return jsonify({"success": False, "message": "Chưa kết nối đến reader."})

    try:
        # Build the 32-bit antenna mask from the list of selected antenna IDs
        reader_instance = _get_reader_instance()
        antenna_mask_int = reader_instance.build_antenna_mask(selected_antennas_raw)
        logger.info(f"API Start Inventory request: Antennas {selected_antennas_raw} -> Mask 0x{antenna_mask_int:08X}.")
        result = rfid_controller.start_inventory(antenna_mask_int)
        return jsonify(result)
    except ValueError as ve:
        logger.error(f"Invalid antenna ID in mask for start inventory: {ve}")
        return jsonify({"success": False, "message": f"Lỗi tham số antenna: {ve}"})
    except Exception as e:
        logger.error(f"Error in API Start Inventory: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/stop_inventory', methods=['POST'])
def api_stop_inventory() -> Dict:
    """
    API endpoint to stop the active RFID tag inventory process.
    """
    logger.info("API Stop Inventory request received.")
    result = rfid_controller.stop_inventory()
    return jsonify(result)

@app.route('/api/stop_tags_inventory', methods=['POST'])
def api_stop_tags_inventory() -> Dict:
    """
    API endpoint to specifically stop the "tags inventory" mode (custom inventory).
    This function also attempts to stop the global inventory thread.
    """
    global stop_inventory_flag, inventory_thread # Access global variables
    
    logger.info("API Stop Tags Inventory request received.")
    if not rfid_controller.is_connected:
        return jsonify({"success": False, "message": "Chưa kết nối đến reader."})
    
    try:
        # Signal the worker thread to stop
        stop_inventory_flag = True
        
        # Explicitly send stop command to the reader via the NationReader instance
        reader_instance = _get_reader_instance()
        if reader_instance:
            logger.info("Sending stop command to reader from api_stop_tags_inventory.")
            reader_instance.stop_inventory()
            time.sleep(0.1) # Brief pause for command processing

        # Wait for the inventory worker thread to gracefully terminate
        if inventory_thread and inventory_thread.is_alive():
            logger.info("Waiting for custom tags inventory thread to finish (max 3 seconds).")
            inventory_thread.join(timeout=3.0)  
            if inventory_thread.is_alive():
                logger.warning("Custom tags inventory thread did not terminate within timeout.")
                return jsonify({"success": False, "message": "Inventory thread không dừng trong thời gian chờ."})
        
        logger.info("Custom tags inventory successfully stopped.")
        return jsonify({"success": True, "message": "Đã dừng tags inventory thành công."})
    except Exception as e:
        logger.error(f"Error in API Stop Tags Inventory: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/set_power', methods=['POST'])
def api_set_power() -> Dict:
    """
    API endpoint to set RF transmit power for one or multiple antennas.
    Expects JSON body: `{'powers': {'1': 20, '2': 15}, 'preserveConfig': true}`
    or `{'antenna': 1, 'power': 20, 'preserveConfig': true}` for single.
    """
    data = request.get_json()
    powers_dict = data.get('powers') # This will be a dict like {"1": 20, "2": 15}
    preserve_config = data.get('preserveConfig', True)  
    
    if powers_dict and isinstance(powers_dict, dict):
        logger.info(f"API Set Power request for multiple antennas: {powers_dict}. Persistence: {preserve_config}.")
        result = rfid_controller.set_power_multi(powers_dict, preserve_config)
    else:
        # Fallback to single antenna configuration if 'powers' dict is not provided or invalid
        power = data.get('power')
        antenna = data.get('antenna', config.DEFAULT_ANTENNA_ID)
        logger.info(f"API Set Power request for single antenna {antenna} at {power} dBm. Persistence: {preserve_config}.")
        result = rfid_controller.set_power_for_antenna(antenna, power, preserve_config)
    return jsonify(result)

@app.route('/api/set_buzzer', methods=['POST'])
def api_set_buzzer() -> Dict:
    """
    API endpoint to control the reader's buzzer.
    Expects JSON body: `{'enable': true}`.
    """
    data = request.get_json()
    enable = data.get('enable', True)
    logger.info(f"API Set Buzzer request: enable={enable}.")
    result = rfid_controller.set_buzzer(enable)
    return jsonify(result)

@app.route('/api/get_profile', methods=['GET'])
def api_get_profile() -> Dict:
    """
    API endpoint to retrieve the current operational profile of the reader.
    """
    logger.info("API Get Profile request received.")
    result = rfid_controller.get_current_profile_data()
    return jsonify(result)

@app.route('/api/set_profile', methods=['POST'])
def api_set_profile() -> Dict:
    """
    API endpoint to set a predefined operational profile on the reader.
    Expects JSON body: `{'profile_num': 1, 'save_on_power_down': true}`.
    """
    data = request.get_json()
    profile_num = data.get('profile_num', 1)
    save_on_power_down = data.get('save_on_power_down', True)
    logger.info(f"API Set Profile request: Profile Number={profile_num}, Save on power down={save_on_power_down}.")
    result = rfid_controller.set_profile_by_number(profile_num, save_on_power_down)
    return jsonify(result)

@app.route('/api/get_enabled_antennas', methods=['GET'])
def api_get_enabled_antennas() -> Dict:
    """
    API endpoint to retrieve a list of currently enabled antenna ports.
    """
    logger.info("API Get Enabled Antennas request received.")
    if not rfid_controller.is_connected or not _get_reader_instance():
        return jsonify({"success": False, "message": "Chưa kết nối đến reader."})
    try:
        reader_instance = _get_reader_instance()
        enabled_mask = reader_instance.query_enabled_ant_mask()
        # Convert the 32-bit mask to a list of 1-based antenna IDs.
        # Uses config.MAX_ANTENNAS for the loop limit.
        enabled_ants = [i + 1 for i in range(config.MAX_ANTENNAS) if (enabled_mask >> i) & 1]
        logger.info(f"Enabled antennas: {enabled_ants} (Mask: 0x{enabled_mask:08X}).")
        return jsonify({"success": True, "antennas": enabled_ants})
    except Exception as e:
        logger.error(f"Error in API Get Enabled Antennas: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/disable_antennas', methods=['POST'])
def api_disable_antennas() -> Dict:
    """
    API endpoint to disable specific antenna ports.
    Expects JSON body: `{'antennas': [1, 2], 'save_on_power_down': true}`.
    """
    data = request.get_json()
    antennas_to_disable = data.get('antennas', [])
    save_on_power_down = data.get('save_on_power_down', True)
    logger.info(f"API Disable Antennas request for: {antennas_to_disable}. Save on power down: {save_on_power_down}.")
    
    if not isinstance(antennas_to_disable, list):
        return jsonify({"success": False, "message": "Danh sách antennas không hợp lệ. Vui lòng cung cấp một mảng số nguyên."})

    result = rfid_controller.disable_antennas(antennas_to_disable, save_on_power_down)
    return jsonify(result)

@app.route('/api/get_antenna_power', methods=['GET'])
def api_get_antenna_power() -> Dict:
    """
    API endpoint to retrieve the current RF transmit power settings for antennas.
    """
    logger.info("API Get Antenna Power request received.")
    result = rfid_controller.get_antenna_power()
    return jsonify(result)

@app.route('/api/config', methods=['GET'])
def api_get_config() -> Dict:
    """
    API endpoint to retrieve the application's configuration settings.
    """
    logger.info("API Get Config request received.")
    try:
        # Return a subset of configuration data relevant for the frontend
        config_data = {
            "default_serial_port": config.DEFAULT_SERIAL_PORT, # Corrected from DEFAULT_PORT
            "default_baudrate": config.DEFAULT_BAUDRATE,
            "max_power": config.POWER_MAX_DBM, # Consistent naming
            "min_power": config.POWER_MIN_DBM, # Consistent naming
            "max_antennas": config.MAX_ANTENNAS,
            "profiles": config.PROFILE_CONFIGS,
            "max_tags_display": config.MAX_TAGS_DISPLAY,
            "min_session": config.SESSION_MIN,
            "max_session": config.SESSION_MAX,
            "min_q_value": config.Q_VALUE_MIN,
            "max_q_value": config.Q_VALUE_MAX,
            "min_scan_time_seconds": config.SCAN_TIME_MIN_SECONDS,
            "max_scan_time_seconds": config.SCAN_TIME_MAX_SECONDS,
            "default_scan_time_seconds": config.DEFAULT_INVENTORY_SCAN_TIME_SECONDS,
        }
        return jsonify({"success": True, "data": config_data})
    except Exception as e:
        logger.error(f"Error in API Get Config: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})

@app.route('/api/configure_baseband', methods=['POST'])
def api_configure_baseband() -> Dict:
    """
    API endpoint to configure the reader's baseband parameters.
    Expects JSON body with speed, q_value, session, and inventory_flag.
    """
    data = request.get_json()
    speed = int(data.get('speed', 0))
    q_value = int(data.get('q_value', config.DEFAULT_Q_VALUE)) # Use config default
    session = int(data.get('session', config.DEFAULT_SESSION)) # Use config default
    inventory_flag = int(data.get('inventory_flag', 0)) # Default 0 (single)
    logger.info(f"API Configure Baseband request: Speed={speed}, Q={q_value}, Session={session}, Flag={inventory_flag}.")
    result = rfid_controller.configure_baseband(speed, q_value, session, inventory_flag)
    return jsonify(result)

@app.route('/api/query_baseband_profile', methods=['GET'])
def api_query_baseband_profile() -> Dict:
    """
    API endpoint to query the current baseband profile settings from the reader.
    """
    logger.info("API Query Baseband Profile request received.")
    result = rfid_controller.query_baseband_profile()
    return jsonify(result)


@socketio.on('connect')
def handle_connect() -> None:
    """Handles new WebSocket client connections."""
    logger.info(f"🔌 WebSocket client connected: {request.sid}.")
    # Emit a status message back to the newly connected client
    emit('status', {'message': 'Connected to server'})
    # Add the client's session ID to the set of connected clients
    connected_clients.add(request.sid)

@socketio.on('disconnect')
def handle_disconnect() -> None:
    """Handles WebSocket client disconnections."""
    logger.info(f"🔌 WebSocket client disconnected: {request.sid}.")
    # Remove the client's session ID from the set
    connected_clients.remove(request.sid)

@socketio.on('message')
def handle_message(message: str) -> None:
    """
    Handles generic messages received from a WebSocket client.
    `message` is the data sent by the client.
    """
    logger.info(f"📨 Received WebSocket message from {request.sid}: {message}.")

@app.route('/api/tags_inventory', methods=['POST'])
def api_tags_inventory() -> Dict:
    """
    API endpoint to start a custom "tags inventory" mode with configurable baseband parameters.
    This mode includes a `scan_time` parameter which defines the duration of the inventory run.
    """
    global inventory_thread, stop_inventory_flag, detected_tags, inventory_stats

    if not rfid_controller.is_connected or not _get_reader_instance():
        return jsonify({"success": False, "message": "Chưa kết nối đến reader."})

    # If an inventory is already running, attempt to stop it before starting a new one
    if inventory_thread and inventory_thread.is_alive():
        logger.info("An existing inventory is currently running. Stopping it before initiating a new one.")
        if not rfid_controller.stop_inventory().get("success"): # Use controller's stop method
            logger.warning("Failed to cleanly stop the previous inventory before starting a new one.")
        time.sleep(0.5) # Give the reader some time to stabilize after stopping

    try:
        # Reset state for the new inventory session
        stop_inventory_flag = False
        detected_tags.clear()
        inventory_stats = {"read_rate": 0, "total_count": 0}

        # Parse parameters from the incoming JSON request
        data = request.get_json()
        q_value = int(data.get("q_value", config.DEFAULT_Q_VALUE)) # Use config default
        session = int(data.get("session", config.DEFAULT_SESSION)) # Use config default
        # inventory_flag determines the inventory mode (e.g., single, continuous, fast)
        inventory_flag = int(data.get("inventory_flag", 0)) 
        # scan_time is the duration for this specific inventory run in seconds
        scan_time_seconds = int(data.get("scan_time", config.DEFAULT_INVENTORY_SCAN_TIME_SECONDS)) 

        # Validate input parameters against configured ranges
        if not config.Q_VALUE_MIN <= q_value <= config.Q_VALUE_MAX:
            return jsonify({"success": False, "message": f"Giá trị Q ({q_value}) phải từ {config.Q_VALUE_MIN} đến {config.Q_VALUE_MAX}."})
        if not config.SESSION_MIN <= session <= config.SESSION_MAX:
            return jsonify({"success": False, "message": f"Giá trị Session ({session}) phải từ {config.SESSION_MIN} đến {config.SESSION_MAX}."})
        if not config.SCAN_TIME_MIN_SECONDS <= scan_time_seconds <= config.SCAN_TIME_MAX_SECONDS:
            return jsonify({"success": False, "message": f"Thời gian quét ({scan_time_seconds}s) phải từ {config.SCAN_TIME_MIN_SECONDS}s đến {config.SCAN_TIME_MAX_SECONDS}s."})

        # Get the current reader instance
        reader_instance = _get_reader_instance() 

        # Configure baseband parameters on the reader before starting inventory
        configure_result = rfid_controller.configure_baseband(
            speed=255, # Default speed, or make configurable in config.py
            q_value=q_value,
            session=session,
            inventory_flag=inventory_flag
        )
        if not configure_result.get("success"): 
            return jsonify({"success": False, "message": f"Không thể cấu hình baseband: {configure_result.get('message', 'Lỗi không xác định')}"})

        def tag_callback_custom_inventory(tag: Dict) -> None:
            """
            Callback function specifically for new tag detections during custom inventory.
            """
            tag_data = {
                "epc": tag.get("epc"),
                "rssi": tag.get("rssi"),
                "antenna": tag.get("antenna_id"),
                "timestamp": time.strftime("%H:%M:%S")
            }
            detected_tags.append(tag_data) # `maxlen` handles deque size automatically
            
            # Update total tag count
            inventory_stats["total_count"] += 1 

            try:
                socketio.emit("tag_detected", tag_data)
            except Exception as e:
                logger.error(f"❌ WebSocket emit failed in custom tags inventory callback: {e}")

        def inventory_worker_custom() -> None:
            """
            Background worker thread function for the custom tags inventory.
            It starts the inventory for a defined `scan_time_seconds` and then stops it.
            """
            logger.info("Custom tags inventory worker started.")
            try:
                if reader_instance: # Ensure the reader instance is still valid
                    reader_instance.uart.flush_input() # Clear buffer before starting
                    
                    # Build antenna mask for the inventory; assuming default antenna 1 if not specified.
                    # If this API should allow antenna selection, pass it from 'data'.
                    default_antenna_mask = reader_instance.build_antenna_mask([config.DEFAULT_ANTENNA_ID]) 

                    if reader_instance.start_inventory_with_mode(
                        antenna_mask=default_antenna_mask,
                        callback=tag_callback_custom_inventory
                    ):
                        logger.info(f"▶️ Inventory started for {scan_time_seconds} seconds (custom tags inventory mode).")
                        time.sleep(scan_time_seconds) # Sleep for the specified duration
                        logger.info("Custom tags inventory duration ended, attempting to stop reader.")
                        reader_instance.stop_inventory() # Stop the reader after the duration
                    else:
                        logger.error("Failed to start inventory in custom tags inventory mode.")

            except Exception as e:
                logger.error(f"Error in custom tags inventory worker: {e}")
            finally:
                logger.info("Custom tags inventory worker finished.")
                
        # Create and start the new inventory thread as a daemon
        inventory_thread = threading.Thread(target=inventory_worker_custom, daemon=True)
        inventory_thread.start()

        logger.info(f"Custom tags inventory started (Q={q_value}, Session={session}, Flag={inventory_flag}, Scan={scan_time_seconds}s).")
        return jsonify({
            "success": True,
            "message": f"Tags inventory đã bắt đầu (Q={q_value}, Session={session}, Flag={inventory_flag}, Scan={scan_time_seconds}s)"
        })

    except Exception as e:
        logger.error(f"Error starting custom tags inventory: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})
    

@app.route('/api/write_epc_tag_auto', methods=['POST'])
def api_write_epc_tag_auto() -> Dict:
    """
    API endpoint to write a new EPC to an RFID tag,
    automatically handling PC bits and word length calculation.
    Expects JSON body: `{'epc': 'NEW_EPC_HEX', 'match_epc': 'OPTIONAL_OLD_EPC', 'antenna_id': 1, 'access_pwd': 0, 'timeout': 1.0}`.
    """
    data = request.get_json()
    epc_to_write = data.get('epc')
    match_epc_hex = data.get('match_epc') # Optional: EPC the tag must currently have
    antenna_id = data.get('antenna_id', config.DEFAULT_ANTENNA_ID) # Use config default
    access_pwd = data.get('access_pwd') # Optional: access password
    timeout = data.get('timeout', 1.0) # Default timeout for write response

    if not epc_to_write:
        return jsonify({"success": False, "message": "EPC mới không được để trống."})
    
    if not rfid_controller.is_connected or not _get_reader_instance():
        return jsonify({"success": False, "message": "Chưa kết nối đến reader."})
    
    logger.info(f"API Write EPC Auto request: New EPC='{epc_to_write}', Match EPC='{match_epc_hex}', Ant ID={antenna_id}.")
    try:
        reader_instance = _get_reader_instance()
        result = reader_instance.write_epc_tag_auto(
            new_epc_hex=epc_to_write,
            match_epc_hex=match_epc_hex,
            antenna_id=antenna_id,
            access_password=access_pwd,
            timeout=timeout
        )
        logger.info(f"Write EPC Auto command sent, result success: {result.get('success')}. Message: {result.get('result_msg')}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in API Write EPC Auto: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})
    
@app.route('/api/check_write_epc', methods=['POST'])
def api_check_write_epc() -> Dict:
    """
    API endpoint to check if a specific EPC can be detected/written to.
    This often involves starting a temporary inventory to confirm tag presence.
    Expects JSON body: `{'epc': 'EPC_TO_CHECK'}`.
    """
    data = request.get_json()
    epc_to_check = data.get('epc')
    # antenna_id is not directly used by `check_write_epc` in `nation.py` as it sets its own.
    # antenna_id = data.get('antenna_id', config.DEFAULT_ANTENNA_ID) 

    if not epc_to_check:
        return jsonify({"success": False, "message": "EPC không được để trống để kiểm tra."})
    
    if not rfid_controller.is_connected or not _get_reader_instance():
        return jsonify({"success": False, "message": "Chưa kết nối đến reader."})
    
    logger.info(f"API Check Write EPC request for: '{epc_to_check}'.")
    try:
        reader_instance = _get_reader_instance()
        # The `check_write_epc` method in `nation.py` (translated) starts its own temporary
        # inventory, waits for a tag, and returns True if successful.
        check_result = reader_instance.check_write_epc(
            epcHex=epc_to_check,
            # If `check_write_epc` in nation.py needs `antenna_id` or `timeout`, add here.
            # Currently it relies on its internal default/logic.
        )
        
        if check_result:
            logger.info(f"Check write EPC for '{epc_to_check}' indicates success. Tag matched or write function appears supported.")
            return jsonify({"success": True, "message": "Thẻ đã được ghi thành công (hoặc khả năng ghi được hỗ trợ)."})
        else:
            logger.warning(f"Check write EPC for '{epc_to_check}' indicates failure. Tag not matched or write function not supported.")
            return jsonify({"success": False, "message": "Thẻ không khớp hoặc chức năng ghi không được hỗ trợ."})
    except Exception as e:
        logger.error(f"Error in API Check Write EPC for '{epc_to_check}': {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})
    
# ---
# ## Main Application Entry Point

# This block starts the Flask-SocketIO server.

# ```python
if __name__ == '__main__':
    # Log the server start details from the config
    logger.info(f"Starting RFID Web Control Panel on http://{config.HOST}:{config.PORT}...")
    # Run the Flask-SocketIO application.
    # use_reloader=False is important to prevent threads from being spawned multiple times
    # when Flask's auto-reloader is active (in debug mode).
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT, use_reloader=False)