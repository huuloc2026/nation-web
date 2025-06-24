from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import threading
import time
import json
from typing import Optional, Dict, List
import serial
import logging

# Import các hàm từ zk.py
from zk import (
    RFIDTag, InventoryResult, connect_reader, get_reader_info, 
    start_inventory, stop_inventory, set_power, set_buzzer,
    get_profile, set_profile, enable_antenna, disable_antenna,
    get_power, start_tags_inventory
)

# Import configuration
from config import get_config

# Load configuration
config = get_config()

app = Flask(__name__)
app.config.from_object(config)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

# Global variables
reader: Optional[serial.Serial] = None
inventory_thread: Optional[threading.Thread] = None
stop_inventory_flag = False
detected_tags = []
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
        """Kết nối đến RFID reader"""
        if baudrate is None:
            baudrate = config.DEFAULT_BAUDRATE
            
        try:
            self.reader = connect_reader(port, baudrate)
            if self.reader:
                self.is_connected = True
                logger.info(f"Connected to RFID reader on {port}")
                return {"success": True, "message": f"Đã kết nối thành công đến {port}"}
            else:
                logger.error(f"Failed to connect to {port}")
                return {"success": False, "message": "Không thể kết nối đến reader"}
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return {"success": False, "message": f"Lỗi kết nối: {str(e)}"}
    
    def disconnect(self) -> Dict:
        """Ngắt kết nối RFID reader"""
        try:
            if self.reader and self.reader.is_open:
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
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            info = get_reader_info(self.reader)
            if info:
                return {"success": True, "data": info}
            else:
                return {"success": False, "message": "Không thể lấy thông tin reader"}
        except Exception as e:
            logger.error(f"Get reader info error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def start_inventory(self, target: int = 0) -> Dict:
        """Bắt đầu inventory"""
        global inventory_thread, stop_inventory_flag, detected_tags, inventory_stats
        
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        # Nếu inventory đang chạy, dừng nó trước
        if inventory_thread and inventory_thread.is_alive():
            logger.info("Inventory đang chạy, dừng trước khi start lại")
            self.stop_inventory()
            time.sleep(1.0)  # Tăng thời gian chờ để đảm bảo reader ổn định
        
        try:
            stop_inventory_flag = False
            detected_tags.clear()
            inventory_stats = {"read_rate": 0, "total_count": 0}
            
            # Clear buffer và đợi reader ổn định
            try:
                self.reader.reset_input_buffer()
                self.reader.reset_output_buffer()
                time.sleep(0.2)
            except Exception as e:
                logger.warning(f"Buffer clear warning: {e}")
            
            def tag_callback(tag: RFIDTag):
                logger.info(f"🔍 Tag callback called: EPC={tag.epc}, RSSI={tag.rssi}, Antenna={tag.antenna}")
                tag_data = {
                    "epc": tag.epc,
                    "rssi": tag.rssi,
                    "antenna": tag.antenna,
                    "timestamp": time.strftime("%H:%M:%S")
                }
                detected_tags.append(tag_data)
                
                # Giới hạn số lượng tags hiển thị
                if len(detected_tags) > config.MAX_TAGS_DISPLAY:
                    detected_tags.pop(0)
                
                logger.info(f"📡 Emitting tag_detected via WebSocket: {tag_data}")
                try:
                    # Thử emit với broadcast=True
                    socketio.emit('tag_detected', tag_data, broadcast=True)
                    logger.info("✅ WebSocket emit successful with broadcast")
                except Exception as e:
                    logger.error(f"❌ WebSocket emit failed: {e}")
                    # Thử emit không có broadcast
                    try:
                        socketio.emit('tag_detected', tag_data)
                        logger.info("✅ WebSocket emit successful without broadcast")
                    except Exception as e2:
                        logger.error(f"❌ WebSocket emit failed again: {e2}")
            
            def stats_callback(read_rate: int, total_count: int):
                logger.info(f"📊 Stats callback called: read_rate={read_rate}, total_count={total_count}")
                inventory_stats["read_rate"] = read_rate
                inventory_stats["total_count"] = total_count
                try:
                    socketio.emit('stats_update', inventory_stats)
                    logger.info("✅ Stats WebSocket emit successful")
                except Exception as e:
                    logger.error(f"❌ Stats WebSocket emit failed: {e}")
            
            # Tạo thread mới với logic cải thiện
            def inventory_worker():
                try:
                    # Clear buffer trước khi start
                    self.reader.reset_input_buffer()
                    time.sleep(0.2)  # Tăng thời gian chờ
                    
                    # Gọi hàm start_inventory từ SDK với stop_flag
                    start_inventory(
                        self.reader, 
                        config.DEFAULT_ADDRESS, 
                        target,
                        tag_callback=tag_callback,
                        stats_callback=stats_callback,
                        stop_flag=lambda: stop_inventory_flag
                    )
                except Exception as e:
                    logger.error(f"Inventory worker error: {e}")
                finally:
                    logger.info("Inventory worker finished")
            
            inventory_thread = threading.Thread(target=inventory_worker)
            inventory_thread.daemon = True
            inventory_thread.start()
            
            logger.info(f"Started inventory with target {'A' if target == 0 else 'B'}")
            return {"success": True, "message": f"Inventory đã bắt đầu (Target {'A' if target == 0 else 'B'})"}
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
                        stop_inventory(self.reader)
                        time.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Stop command attempt {i+1} failed: {e}")
                
                # Đợi reader xử lý lệnh stop
                time.sleep(0.5)
                
                # Clear buffer sau khi stop
                try:
                    self.reader.reset_input_buffer()
                    self.reader.reset_output_buffer()
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
    
    def set_power(self, power: int, preserve_config: bool = True) -> Dict:
        """Thiết lập công suất RF"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        if not config.MIN_POWER <= power <= config.MAX_POWER:
            return {"success": False, "message": f"Công suất phải từ {config.MIN_POWER} đến {config.MAX_POWER} dBm"}
        
        try:
            result = set_power(self.reader, power, preserve_config=preserve_config)
            if result:
                logger.info(f"Set power to {power} dBm")
                return {"success": True, "message": f"Đã thiết lập công suất: {power} dBm"}
            else:
                return {"success": False, "message": "Không thể thiết lập công suất"}
        except Exception as e:
            logger.error(f"Set power error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def set_buzzer(self, enable: bool) -> Dict:
        """Bật/tắt buzzer"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            result = set_buzzer(self.reader, enable)
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
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        if not all(1 <= ant <= config.MAX_ANTENNAS for ant in antennas):
            return {"success": False, "message": f"Antenna phải từ 1 đến {config.MAX_ANTENNAS}"}
        
        try:
            result = enable_antenna(self.reader, antennas, save_on_power_down)
            if result:
                logger.info(f"Enabled antennas: {antennas}")
                return {"success": True, "message": f"Đã bật antennas: {antennas}"}
            else:
                return {"success": False, "message": "Không thể bật antennas"}
        except Exception as e:
            logger.error(f"Enable antennas error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def disable_antennas(self, antennas: List[int], save_on_power_down: bool = True) -> Dict:
        """Tắt antennas"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        if not all(1 <= ant <= config.MAX_ANTENNAS for ant in antennas):
            return {"success": False, "message": f"Antenna phải từ 1 đến {config.MAX_ANTENNAS}"}
        
        try:
            result = disable_antenna(self.reader, antennas, save_on_power_down)
            if result:
                logger.info(f"Disabled antennas: {antennas}")
                return {"success": True, "message": f"Đã tắt antennas: {antennas}"}
            else:
                return {"success": False, "message": "Không thể tắt antennas"}
        except Exception as e:
            logger.error(f"Disable antennas error: {e}")
            return {"success": False, "message": f"Lỗi: {str(e)}"}
    
    def get_antenna_power(self) -> Dict:
        """Lấy công suất antennas"""
        if not self.is_connected:
            return {"success": False, "message": "Chưa kết nối đến reader"}
        
        try:
            power_levels = get_power(self.reader)
            if power_levels:
                self.antenna_power = power_levels
                return {"success": True, "data": power_levels}
            else:
                return {"success": False, "message": "Không thể lấy công suất antennas"}
        except Exception as e:
            logger.error(f"Get antenna power error: {e}")
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
    target = data.get('target', 0)
    
    result = rfid_controller.start_inventory(target)
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
    """API thiết lập công suất"""
    data = request.get_json()
    power = data.get('power', config.DEFAULT_ANTENNA_POWER)
    preserve_config = data.get('preserve_config', True)
    
    result = rfid_controller.set_power(power, preserve_config)
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

@app.route('/api/enable_antennas', methods=['POST'])
def api_enable_antennas():
    """API bật antennas"""
    data = request.get_json()
    antennas = data.get('antennas', [1])
    save_on_power_down = data.get('save_on_power_down', True)
    
    result = rfid_controller.enable_antennas(antennas, save_on_power_down)
    return jsonify(result)

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

@app.route('/api/get_tags', methods=['GET'])
def api_get_tags():
    """API lấy danh sách tags đã phát hiện"""
    return jsonify({
        "success": True,
        "data": detected_tags,
        "stats": inventory_stats
    })

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

@app.route('/api/debug', methods=['GET'])
def api_debug():
    """API debug info"""
    try:
        data = {
            "is_connected": rfid_controller.is_connected,
            "inventory_thread_alive": inventory_thread.is_alive() if inventory_thread else False,
            "stop_inventory_flag": stop_inventory_flag,
            "detected_tags_count": len(detected_tags),
            "inventory_stats": inventory_stats,
            "recent_tags": detected_tags[-10:] if detected_tags else []  # 10 tags gần nhất
        }
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Debug API error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}

@app.route('/api/reset_reader', methods=['POST'])
def api_reset_reader():
    """API reset reader"""
    try:
        # Dừng inventory nếu đang chạy
        if inventory_thread and inventory_thread.is_alive():
            logger.info("Dừng inventory trước khi reset reader")
            rfid_controller.stop_inventory()
            time.sleep(1.0)  # Đợi thread dừng hoàn toàn
        
        # Clear data
        detected_tags.clear()
        inventory_stats = {"read_rate": 0, "total_count": 0}
        
        # Reset reader nếu đã kết nối
        if rfid_controller.is_connected and rfid_controller.reader:
            try:
                logger.info("Đang reset reader...")
                
                # Clear buffers
                rfid_controller.reader.reset_input_buffer()
                rfid_controller.reader.reset_output_buffer()
                time.sleep(0.2)
                
                # Gửi lệnh stop nhiều lần để đảm bảo reader dừng hoàn toàn
                for i in range(3):
                    try:
                        stop_inventory(rfid_controller.reader)
                        time.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Stop command attempt {i+1} failed: {e}")
                
                # Đợi reader ổn định
                time.sleep(0.5)
                
                # Clear buffers một lần nữa
                rfid_controller.reader.reset_input_buffer()
                rfid_controller.reader.reset_output_buffer()
                time.sleep(0.2)
                
                logger.info("Reader reset completed successfully")
            except Exception as e:
                logger.warning(f"Reader reset warning: {e}")
        
        logger.info("Reader reset completed")
        return {"success": True, "message": "Đã reset reader thành công"}
    except Exception as e:
        logger.error(f"Reset reader error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}

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
        rfid_controller.stop_inventory()
        time.sleep(1.0)  # Tăng thời gian chờ để đảm bảo reader ổn định

    try:
        # Reset trạng thái
        stop_inventory_flag = False
        detected_tags.clear()
        inventory_stats = {"read_rate": 0, "total_count": 0}

        # Lấy tham số từ request
        data      = request.get_json()
        q_value   = int(data.get("q_value", 4))
        session   = int(data.get("session", 0))
        antenna   = int(data.get("antenna", 1))
        scan_time = int(data.get("scan_time", 10))

        # Clear buffer và đợi reader ổn định trước khi bắt đầu
        try:
            rfid_controller.reader.reset_input_buffer()
            rfid_controller.reader.reset_output_buffer()
            time.sleep(0.3)  # Tăng thời gian chờ khi chuyển session
        except Exception as e:
            logger.warning(f"Buffer clear warning: {e}")

        # Callback khi có tag mới
        def tag_callback(tag: RFIDTag):
            tag_data = {
                "epc":       tag.epc,
                "rssi":      tag.rssi,
                "antenna":   tag.antenna,
                "timestamp": time.strftime("%H:%M:%S")
            }
            detected_tags.append(tag_data)
            if len(detected_tags) > config.MAX_TAGS_DISPLAY:
                detected_tags.pop(0)
            # Emit không có broadcast
            try:
                socketio.emit("tag_detected", tag_data)
            except Exception as e:
                logger.error(f"❌ WebSocket emit failed: {e}")

        # Callback khi có stats
        def stats_callback(read_rate: int, total_count: int):
            inventory_stats["read_rate"]   = read_rate
            inventory_stats["total_count"] = total_count
            try:
                socketio.emit("stats_update", inventory_stats)
            except Exception as e:
                logger.error(f"❌ Stats WebSocket emit failed: {e}")

        # Thread worker: loop liên tục cho đến khi stop_inventory_flag = True
        def inventory_worker():
            cycle_count = 0
            switch_target = 0
            try:
                while not stop_inventory_flag:
                    cycle_count += 1
                    logger.info(f"\n--- Starting inventory cycle #{cycle_count} at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                    
                    # Xóa buffer, đợi 0.2s để ổn định
                    try:
                        rfid_controller.reader.reset_input_buffer()
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Buffer clear warning in cycle {cycle_count}: {e}")
                    
                    # Thực hiện 1 lượt scan
                    if session < 2:
                        start_tags_inventory(
                        rfid_controller.reader,
                        address=config.DEFAULT_ADDRESS,
                        q_value=q_value,
                        session=session,
                        target=0,
                        antenna=antenna,
                        scan_time=scan_time,
                        tag_callback=tag_callback,
                        stats_callback=stats_callback
                    )
                    else:
                        start_tags_inventory(
                        rfid_controller.reader,
                        address=config.DEFAULT_ADDRESS,
                        q_value=q_value,
                        session=session,
                        target=switch_target,
                        antenna=antenna,
                        scan_time=scan_time,
                        tag_callback=tag_callback,
                        stats_callback=stats_callback
                        )
                    switch_target = abs(switch_target-1)
                    
                    # Nếu đã được yêu cầu dừng, break
                    if stop_inventory_flag:
                        break
                        
                    logger.info(f"\n--- Inventory cycle #{cycle_count} completed at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                    logger.info("🔄 Starting next cycle immediately...")
                    
                    # Không có delay giữa các cycle để quét nhanh nhất có thể
            
            except Exception as e:
                logger.error(f"Tags inventory worker error: {e}")
            finally:
                logger.info("Tags inventory worker finished (continuous mode)")

        # Khởi thread
        inventory_thread = threading.Thread(target=inventory_worker)
        inventory_thread.daemon = True
        inventory_thread.start()

        logger.info(f"Started continuous tags inventory (Q={q_value}, Session={session}, Antenna={antenna}, Scan={scan_time})")
        return {
            "success": True,
            "message": f"Tags inventory đã bắt đầu (Q={q_value}, Session={session}, Antenna={antenna}, Scan={scan_time})"
        }

    except Exception as e:
        logger.error(f"Start tags inventory error: {e}")
        return {"success": False, "message": f"Lỗi: {str(e)}"}



if __name__ == '__main__':
    logger.info(f"Starting RFID Web Control Panel on {config.HOST}:{config.PORT}")
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT) 