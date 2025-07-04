from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import threading
import time
import json
from typing import Optional, Dict, List
import serial
from serial.tools import list_ports
from collections import deque
# from queue import Queue, Empty
import logging




# Import configuration
from config import get_config

#Nation 
from nation import NationReader

# Load configuration
config = get_config()

app = Flask(__name__)
app.config.from_object(config)
CORS(app)  
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=True)

# Global variables
reader: Optional[serial.Serial] = None
inventory_thread: Optional[threading.Thread] = None
stop_inventory_flag = False
detected_tags = []
# detected_tags = deque(maxlen=config.MAX_TAGS_DISPLAY)
# tag_queue = Queue()
inventory_stats = {"read_rate": 0, "total_count": 0}
connected_clients = set()

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

class RFIDWebController:
    def __init__(self):
        self.reader = None
        self.is_connected = False
        self.current_profile = None
        self.antenna_power = {}
        
    def connect(self, port: str, baudrate: int = None) -> Dict:
        if baudrate is None:
            baudrate = config.DEFAULT_BAUDRATE
            print(port, baudrate)
        try:
            self.reader = NationReader(port, baudrate)
            self.reader.open()
            self.is_connected = True
            logger.info(f"Connected to RFID reader on {port}")
            return {"success": True, "message": f"Đã kết nối thành công đến {port}"}
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return {"success": False, "message": f"Lỗi kết nối: {str(e)}"}

    
    def disconnect(self) -> Dict:
        """Ngắt kết nối RFID reader"""
        try:
            if self.reader:
                self.reader.close()
            self.is_connected = False
            self.reader = None
            logger.info("Disconnected from RFID reader")
            return {"success": True, "message": "Đã ngắt kết nối"}
        except Exception as e:
            logger.error(f"Disconnect error: {e}")
            return {"success": False, "message": f"Lỗi ngắt kết nối: {str(e)}"}
    
    def get_reader_info(self) -> Dict:
        """Lấy thông tin reader"""
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            info = self.reader.Query_Reader_Information()
            if info and isinstance(info, dict) and info:
                for k, v in info.items():
                    print(f"  {k}: {v}")
                return {"success": True, "data": info}  
            else:
                return {"success": False, "message": "Không thể lấy thông tin reader"}
        except Exception as e:
            logger.error(f"Get reader info error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def configure_baseband(self, speed: int, q_value: int, session: int, inventory_flag: int) -> Dict:
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            ok = self.reader.configure_baseband(speed, q_value, session, inventory_flag)
            if ok:
                return {"success": True, "message": "Đã cấu hình baseband thành công"}
            else:
                return {"success": False, "message": "Không thể cấu hình baseband"}
        except Exception as e:
            logger.error(f"Configure baseband error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def query_baseband_profile(self) -> Dict:
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            info = self.reader.query_baseband_profile()
            if info:
                return {"success": True, "data": info}
            else:
                return {"success": False, "message": "Không thể lấy thông tin baseband"}
        except Exception as e:
            logger.error(f"Query baseband profile error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def start_inventory(self, antenna_mask: int ) -> Dict:
        global inventory_thread, stop_inventory_flag, detected_tags, inventory_stats

        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        # If inventory is already running, do not start another
        if inventory_thread and inventory_thread.is_alive():
            logger.warning("Inventory thread already running. Ignoring new start request.")
            return {"success": False, "message": "Inventory đang chạy"}

        try:
            stop_inventory_flag = False
            detected_tags.clear()
            inventory_stats = {"read_rate": 0, "total_count": 0}

            # Only flush input, avoid unnecessary sleeps
            try:
                self.reader.uart.flush_input()
            except Exception as e:
                logger.warning(f"Buffer clear warning: {e}")

            def tag_callback(tag: dict):
                logger.info(f"🔍 Tag callback called: EPC={tag.get('epc')}, RSSI={tag.get('rssi')}, Antenna={tag.get('antenna_id')}")
                tag_data = {
                    "epc": tag.get("epc"),
                    "rssi": tag.get("rssi"),
                    "antenna": tag.get("antenna_id"),
                    "timestamp": time.strftime("%H:%M:%S")
                }
                print(f"Detected tag: {tag_data}")
                detected_tags.append(tag_data)
                if len(detected_tags) > config.MAX_TAGS_DISPLAY:
                    detected_tags.pop(0)
                try:
                    socketio.emit('tag_detected', tag_data)
                except Exception as e:
                    logger.error(f"❌ WebSocket emit failed: {e}")

            def inventory_worker():
                try:         
                    # Start inventory with callbacks
                    self.reader.start_inventory_with_mode(antenna_mask=antenna_mask,callback=tag_callback)
                except Exception as e:
                    logger.error(f"Inventory worker error: {e}")
                finally:
                    logger.info("Inventory worker finished")

            inventory_thread = threading.Thread(target=inventory_worker, daemon=True)
            inventory_thread.start()

            logger.info("Started inventory thread.")
            return {"success": True, "message": "Inventory đã bắt đầu"}
        except Exception as e:
            logger.error(f"Start inventory error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    
    def stop_inventory(self) -> Dict:
        """Dừng inventory"""
        global stop_inventory_flag
        
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            # Set flag để dừng inventory
            stop_inventory_flag = True
            
            # Gửi lệnh stop đến reader
            if self.reader:
                # Gửi lệnh stop nhiều lần để đảm bảo reader nhận được
                for i in range(3):
                    try:
                        self.reader.stop_inventory()
                        time.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Stop command attempt {i+1} failed: {e}")
                
                # Đợi reader xử lý lệnh stop
                time.sleep(0.5)
                
                # Clear buffer sau khi stop
                try:
                    self.reader.uart.flush_input()
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Buffer clear warning: {e}")
            
            # Đợi thread dừng (tối đa 3 giây)
            if inventory_thread and inventory_thread.is_alive():
                inventory_thread.join(timeout=3.0)
                if inventory_thread.is_alive():
                    logger.warning("Inventory thread không dừng trong thời gian chờ")
                    # Force stop bằng cách set flag và đợi thêm
                    stop_inventory_flag = True
                    time.sleep(0.5)
            
            logger.info("Stopped inventory")
            return {"success": True, "message": "Đã dừng inventory"}
        except Exception as e:
            logger.error(f"Stop inventory error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def set_power(self,  antenna_powers: dict[int, int], preserve_config: bool = True) -> Dict:
        """Thiết lập công suất RF"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        # if not config.MIN_POWER <= antenna_powers <= config.MAX_POWER:
        #     return {"success": False, "message": f"Công suất phải từ {config.MIN_POWER} đến {config.MAX_POWER} dBm"}
        
        try:
            # Set power for all enabled antennas, or just antenna 1 if you want
            # Example: {1: power}
            
            result = self.reader.configure_reader_power(antenna_powers, persistence=preserve_config)
            
            if result:
                logger.info(f"Set power to {antenna_powers} dBm")
                return {"success": True, "message": f"Đã thiết lập công suất: {antenna_powers} dBm"}
            else:
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Set power error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def get_antenna_power(self) -> Dict:
        """Lấy công suất antennas"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            power_levels = self.reader.query_reader_power()
            print(power_levels)  # Raw dict output
            # Pretty print for each antenna
            if power_levels:
                for ant, val in power_levels.items():
                    print(f"  🔧 Antenna {ant}: {val} dBm")
                self.antenna_power = power_levels
                return {"success": True, "data": power_levels}
            else:
                return {"success": False, "message": "Không thể lấy công suất antennas"}
        except Exception as e:
            logger.error(f"Get antenna power error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
  
    def set_buzzer(self, enable: bool) -> Dict:
        """Bật/tắt buzzer dựa trên NationReader.set_beeper"""
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            # Mode: 1 = continuous beep, 0 = off, 2 = beep on new tag (optional)
            mode = 1 if enable else 0
            result = self.reader.set_beeper(mode)
            if result:
                status = "bật" if enable else "tắt"
                logger.info(f"{'Enabled' if enable else 'Disabled'} buzzer")
                return {"success": True, "message": f"Đã {status} buzzer"}
            else:
                return {"success": False, "message": "Không thể thiết lập buzzer"}
        except Exception as e:
            logger.error(f"Set buzzer error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def get_current_profile(self) -> Dict:
        """Lấy profile hiện tại"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            profile = get_profile(self.reader)
            if profile is not None:
                self.current_profile = profile
                return {"success": True, "data": {"profile": profile}}
            else:
                return {"success": False, "message": "Không thể lấy profile"}
        except Exception as e:
            logger.error(f"Get profile error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def set_profile(self, profile_num: int, save_on_power_down: bool = True) -> Dict:
        """Thiết lập profile"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        if profile_num not in config.PROFILE_CONFIGS:
            return {"success": False, "message": "Profile không hợp lệ"}
        
        try:
            result = set_profile(self.reader, profile_num, save_on_power_down)
            if result:
                self.current_profile = profile_num
                logger.info(f"Set profile to {profile_num}")
                return {"success": True, "message": f"Đã thiết lập profile: {profile_num}"}
            else:
                return {"success": False, "message": "Không thể thiết lập profile"}
        except Exception as e:
            logger.error(f"Set profile error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def enable_antennas(self, antennas: List[int], save_on_power_down: bool = True) -> Dict:
        """Bật antennas"""
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        # Validate antenna numbers
        if not all(1 <= ant <= 32 for ant in antennas):
            return {"success": False, "message": "Antenna phải từ 1 đến 32"}

        try:
            # Use NationReader method to enable antennas
            # This assumes NationReader has a method enable_ant(ant_id: int, save: bool)
            for ant in antennas:
                self.reader.enable_ant(ant, save_on_power_down)
            logger.info(f"Enabled antennas: {antennas}")
            return {"success": True, "message": f"Đã bật antennas: {antennas}"}
        except Exception as e:
            logger.error(f"Enable antennas error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def disable_antennas(self, antennas: List[int], save_on_power_down: bool = True) -> Dict:
        """Tắt antennas"""
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        # Validate antenna numbers
        if not all(1 <= ant <= 32 for ant in antennas):
            return {"success": False, "message": "Antenna phải từ 1 đến 32"}

        try:
            # Use NationReader method to disable antennas
            # This assumes NationReader has a method disable_ant(ant_id: int, save: bool)
            for ant in antennas:
                self.reader.disable_ant(ant, save_on_power_down)
            logger.info(f"Disabled antennas: {antennas}")
            return {"success": True, "message": f"Đã tắt antennas: {antennas}"}
        except Exception as e:
            logger.error(f"Disable antennas error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
        
    def set_power_for_antenna(self, antenna: int, power: int, preserve_config: bool = True) -> Dict:
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            result = self.reader.configure_reader_power({antenna: power}, persistence=preserve_config)
            if result:
                logger.info(f"Set power for antenna {antenna} to {power} dBm")
                return {"success": True, "message": f"Đã thiết lập công suất Antenna {antenna}: {power} dBm"}
            else:
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Set power error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
        
    def set_power_multi(self, powers: dict, preserve_config: bool = True) -> Dict:
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        try:
            # Convert string keys to int
            powers_int = {int(k): int(v) for k, v in powers.items()}
            result = self.reader.configure_reader_power(powers_int, persistence=preserve_config)
            if result:
                logger.info(f"Set power for all antennas: {powers_int}")
                return {"success": True, "message": f"Đã thiết lập công suất cho tất cả antennas"}
            else:
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Set power error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}

    def write_to_target_tag(
        self,
        target_tag_epc: str,
        new_epc_hex: str,
        access_pwd: int = None,
        overwrite_pc: bool = False,
        prefix_words: int = 0,
        timeout: float = 2.0,
        scan_timeout: float = 2.0,
    ):
        """
        Scan for a tag with EPC `target_tag_epc`, then write `new_epc_hex` to it.
        Uses NationReader.write_to_target_tag and returns its result.
        """
        if not self.is_connected or not self.reader:
            return {"success": False, "message": "Chưa kết nối đến reader"}

        try:
            result = self.reader.write_to_target_tag(
                target_tag_epc=target_tag_epc,
                new_epc_hex=new_epc_hex,
                access_pwd=access_pwd,
                overwrite_pc=overwrite_pc,
                prefix_words=prefix_words,
                timeout=timeout,
                scan_timeout=scan_timeout,
            )
            if result is None:
                return {"success": False, "message": "Không thể ghi EPC vào tag"}
            return result
        except Exception as e:
            logger.error(f"Write to target tag error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    


    
            
        
# Khởi tạo controller
rfid_controller = RFIDWebController()

@app.route('/')
def index():
    """Trang chủ"""
    return render_template('index.html', config=config)

@app.route('/api/connect', methods=['POST'])
def api_connect():
    """API kết nối reader"""
    data = request.get_json()
    port = data.get('port', config.DEFAULT_PORT)
    baudrate = data.get('baudrate', config.DEFAULT_BAUDRATE)
    print(f"Connecting to RFID reader on port {port} with baudrate {baudrate}")
    result = rfid_controller.connect(port, baudrate)
    return jsonify(result)

@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    """API ngắt kết nối reader"""
    result = rfid_controller.disconnect()
    return jsonify(result)

@app.route('/api/reader_info', methods=['GET'])
def api_reader_info():
    """API lấy thông tin reader"""
    result = rfid_controller.get_reader_info()
    return jsonify(result)

@app.route('/api/start_inventory', methods=['POST'])
def api_start_inventory():
    """API bắt đầu inventory"""
    data = request.get_json()
    antenna_mask = data.get('selectedAntennas')
    result = rfid_controller.start_inventory(antenna_mask)
    return jsonify(result)

@app.route('/api/stop_inventory', methods=['POST'])
def api_stop_inventory():
    """API dừng inventory"""
    result = rfid_controller.stop_inventory()
    return jsonify(result)

@app.route('/api/stop_tags_inventory', methods=['POST'])
def api_stop_tags_inventory():
    """API dừng tags inventory"""
    global stop_inventory_flag
    
    try:
        # Set flag để dừng inventory
        stop_inventory_flag = True
        
        # Đợi thread kết thúc
        if inventory_thread and inventory_thread.is_alive():
            logger.info("Waiting for tags inventory thread to finish...")
            inventory_thread.join(timeout=3.0)  # Đợi tối đa 3 giây
        
        logger.info("Tags inventory stopped successfully")
        return {"success": True, "message": "Đã dừng tags inventory thành công"}
    except Exception as e:
        logger.error(f"Stop tags inventory error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}

@app.route('/api/set_power', methods=['POST'])
def api_set_power():
    data = request.get_json()
    powers = data.get('powers')
    preserve_config = data.get('preserveConfig', True)  # <-- Fix key to match frontend
    if powers:
        # Convert string keys to int for backend compatibility
        powers_int = {int(k): int(v) for k, v in powers.items()}
        result = rfid_controller.set_power_multi(powers_int, preserve_config)
    else:
        # Fallback: single antenna (legacy)
        power = data.get('power')
        antenna = data.get('antenna', 1)
        result = rfid_controller.set_power_for_antenna(antenna, power, preserve_config)
    return jsonify(result)

@app.route('/api/set_buzzer', methods=['POST'])
def api_set_buzzer():
    """API thiết lập buzzer"""
    data = request.get_json()
    enable = data.get('enable', True)
    
    result = rfid_controller.set_buzzer(enable)
    return jsonify(result)

@app.route('/api/get_profile', methods=['GET'])
def api_get_profile():
    """API lấy profile hiện tại"""
    result = rfid_controller.get_current_profile()
    return jsonify(result)

@app.route('/api/set_profile', methods=['POST'])
def api_set_profile():
    """API thiết lập profile"""
    data = request.get_json()
    profile_num = data.get('profile_num', 1)
    save_on_power_down = data.get('save_on_power_down', True)
    
    result = rfid_controller.set_profile(profile_num, save_on_power_down)
    return jsonify(result)

@app.route('/api/get_enabled_antennas', methods=['GET'])
def api_get_enabled_antennas():
    if not rfid_controller.is_connected:
        return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
    try:
        ants = rfid_controller.reader.get_enabled_ants()
        return jsonify({"success": True, "antennas": ants})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/disable_antennas', methods=['POST'])
def api_disable_antennas():
    """API tắt antennas"""
    data = request.get_json()
    antennas = data.get('antennas', [1])
    save_on_power_down = data.get('save_on_power_down', True)
    
    result = rfid_controller.disable_antennas(antennas, save_on_power_down)
    return jsonify(result)

@app.route('/api/get_antenna_power', methods=['GET'])
def api_get_antenna_power():
    """API lấy công suất antennas"""
    result = rfid_controller.get_antenna_power()
    return jsonify(result)

# @app.route('/api/get_tags', methods=['GET'])
# def api_get_tags():
#     """API lấy danh sách tags đã phát hiện"""
#     return jsonify({
#         "success": True,
#         "data": detected_tags,
#         "stats": inventory_stats
#     })

@app.route('/api/config', methods=['GET'])
def api_get_config():
    """API lấy cấu hình"""
    try:
        config_data = {
            "default_port": config.DEFAULT_PORT,
            "default_baudrate": config.DEFAULT_BAUDRATE,
            "max_power": config.MAX_POWER,
            "min_power": config.MIN_POWER,
            "max_antennas": config.MAX_ANTENNAS,
            "profiles": config.PROFILE_CONFIGS,
            "max_tags_display": config.MAX_TAGS_DISPLAY
        }
        return {"success": True, "data": config_data}
    except Exception as e:
        logger.error(f"Config API error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}


# @app.route('/api/debug', methods=['GET'])
# def api_debug():
#     """API debug info"""
#     try:
#         data = {
#             "is_connected": rfid_controller.is_connected,
#             "inventory_thread_alive": inventory_thread.is_alive() if inventory_thread else False,
#             "stop_inventory_flag": stop_inventory_flag,
#             "detected_tags_count": len(detected_tags),
#             "inventory_stats": inventory_stats,
#             "recent_tags": detected_tags[-10:] if detected_tags else []  # 10 tags gần nhất
#         }
#         return {"success": True, "data": data}
#     except Exception as e:
#         logger.error(f"Debug API error: {e}")
#         return {"success": False, "message": f"Lỗi: {str(e)}"}


@app.route('/api/configure_baseband', methods=['POST'])
def api_configure_baseband():
    """API cấu hình baseband"""
    data = request.get_json()
    speed = int(data.get('speed', 0))
    q_value = int(data.get('q_value', 1))
    session = int(data.get('session', 2))
    inventory_flag = int(data.get('inventory_flag', 0))
    result = rfid_controller.configure_baseband(speed, q_value, session, inventory_flag)
    return jsonify(result)

@app.route('/api/query_baseband_profile', methods=['GET'])
def api_query_baseband_profile():
    """API lấy thông tin baseband profile"""
    result = rfid_controller.query_baseband_profile()
    return jsonify(result)


@socketio.on('connect')
def handle_connect():
    """Xử lý khi client kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client connected: {request.sid}")
    socketio.emit('status', {'message': 'Connected to server'})
    connected_clients.add(request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Xử lý khi client ngắt kết nối WebSocket"""
    logger.info(f"🔌 WebSocket client disconnected: {request.sid}")
    connected_clients.remove(request.sid)

@socketio.on('message')
def handle_message(message):
    """Xử lý message từ client"""
    logger.info(f"📨 Received WebSocket message: {message}")

@app.route('/api/tags_inventory', methods=['POST'])
def api_tags_inventory():
    """API bắt đầu tags inventory với cấu hình tuỳ chọn (liên tục)"""
    global inventory_thread, stop_inventory_flag, detected_tags, inventory_stats

    if not rfid_controller.is_connected:
        return {"success": False, "message": "Chưa kết nối đến reader"}

    # Nếu inventory đang chạy, dừng rồi chờ thread kết thúc
    if inventory_thread and inventory_thread.is_alive():
        logger.info("Inventory đang chạy, dừng trước khi start lại")
        rfid_controller.reader.stop_inventory()
        time.sleep(1.0)  # Đảm bảo reader ổn định

    try:
        # Reset trạng thái
        stop_inventory_flag = False
        detected_tags.clear()
        inventory_stats = {"read_rate": 0, "total_count": 0}

        # Lấy tham số từ request
        data      = request.get_json()
        q_value   = int(data.get("q_value", 4))
        session   = int(data.get("session", 0))
        inventory_flag = int(data.get("inventory_flag", 0))  # 0: Single, 1: Continuous, 2: Fast
        scan_time = int(data.get("scan_time", 10))  # Not used directly in NationReader, but can be used for sleep

        # Cấu hình baseband trước khi inventory
        if not rfid_controller.reader.configure_baseband(
            speed=255,  # Or another value if you want to expose this
            q_value=q_value,
            session=session,
            inventory_flag=inventory_flag
        ):
            return {"success": False, "message": "Không thể cấu hình baseband"}

        # Callback khi có tag mới
        def tag_callback(tag: dict):
            tag_data = {
                "epc":       tag.get("epc"),
                "rssi":      tag.get("rssi"),
                "antenna":   tag.get("antenna_id"),
                "timestamp": time.strftime("%H:%M:%S")
            }
            detected_tags.append(tag_data)
            if len(detected_tags) > config.MAX_TAGS_DISPLAY:
                detected_tags.pop(0)
            try:
                socketio.emit("tag_detected", tag_data)
            except Exception as e:
                logger.error(f"❌ WebSocket emit failed: {e}")

        # Thread worker: run inventory for scan_time*100ms, then stop
        def inventory_worker():
            try:
                rfid_controller.reader.uart.flush_input()
                rfid_controller.reader.start_inventory(on_tag=tag_callback)
                logger.info("▶️ Inventory started (custom tags inventory mode)")
                
                time.sleep(scan_time * 0.1)
                rfid_controller.reader.stop_inventory()
                logger.info("⏹️ Inventory stopped after scan_time")
            except Exception as e:
                logger.error(f"Tags inventory worker error: {e}")
            finally:
                logger.info("Tags inventory worker finished")

        # Khởi thread
        inventory_thread = threading.Thread(target=inventory_worker)
        inventory_thread.daemon = True
        inventory_thread.start()

        logger.info(f"Started tags inventory (Q={q_value}, Session={session}, Flag={inventory_flag}, Scan={scan_time})")
        return {
            "success": True,
            "message": f"Tags inventory đã bắt đầu (Q={q_value}, Session={session}, Flag={inventory_flag}, Scan={scan_time})"
        }

    except Exception as e:
        logger.error(f"Start tags inventory error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}
    

@app.route('/api/write_epc_tag_auto', methods=['POST'])
def api_write_epc_tag_auto():
    """
    API ghi EPC vào tag sử dụng auto PC bits, word length, v.v.
    Body: {
        "epc": "ABCD1111",
        "match_epc": null,
        "antenna_id": 1,
        "access_pwd": null,
        "timeout": 1
    }
    """
    data = request.get_json()
    epc = data.get('epc')
    match_epc = data.get('match_epc')
    antenna_id = data.get('antenna_id', 1)
    access_pwd = data.get('access_pwd')
    timeout = data.get('timeout')
    if not epc:
        return jsonify({"success": False, "message": "EPC không được để trống"})
    if not rfid_controller.is_connected or not rfid_controller.reader:
        return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
    try:
        result = rfid_controller.reader.write_epc_tag_auto(
            new_epc_hex=epc,
            match_epc_hex=match_epc,
            antenna_id=antenna_id,
            access_password=access_pwd,
            timeout=timeout
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"Write EPC auto error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})
    
@app.route('/api/check_write_epc', methods=['POST'])
def check_write_epc():
    """
    API kiểm tra khả năng ghi EPC vào tag
    Body: {
        "epc": "ABCD1111",
        "match_epc": null,
        "antenna_id": 1,
        "access_pwd": null,
        "timeout": 1
    }
    """
    data = request.get_json()
    epc = data.get('epc')
    antenna_id = data.get('antenna_id', 1)

    
    if not epc:
        return jsonify({"success": False, "message": "EPC không được để trống"})
    
    if not rfid_controller.is_connected or not rfid_controller.reader:
        return jsonify({"success": False, "message": "Chưa kết nối đến reader"})
    
    try:
        result = rfid_controller.reader.check_write_epc(
            epcHex=epc,
        )
        if result is None:
            return jsonify({"success": False, "message": "Không thể kiểm tra khả năng ghi EPC"})
        if result is True:
            return jsonify({"success": True, "message": "Matching"})
    except Exception as e:
        logger.error(f"Check write EPC error: {e}")
        return jsonify({"success": False, "message": f"Lỗi: {str(e)}"})
    
    
if __name__ == '__main__':
    logger.info(f"Starting RFID Web Control Panel on {config.HOST}:{config.PORT}")
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT)