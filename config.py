"""
Cấu hình cho ứng dụng RFID Reader Web Control Panel
"""

import os

class Config:
    """Cấu hình cơ bản"""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'rfid_web_app_secret_key'
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    # Server Configuration
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 3000))
    
    # Serial Configuration
    DEFAULT_PORT = os.environ.get('DEFAULT_SERIAL_PORT', 'COM1')
    DEFAULT_BAUDRATE = int(os.environ.get('DEFAULT_BAUDRATE', 57600))
    
    # RFID Reader Configuration
    DEFAULT_ADDRESS = 0x00
    DEFAULT_Q_VALUE = 4
    DEFAULT_SESSION = 0
    DEFAULT_ANTENNA = 1
    DEFAULT_SCAN_TIME = 10
    
    # WebSocket Configuration
    SOCKETIO_ASYNC_MODE = 'eventlet'
    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"
    
    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # UI Configuration
    MAX_TAGS_DISPLAY = 100  # Số lượng tags tối đa hiển thị
    AUTO_REFRESH_INTERVAL = 5000  # Tự động làm mới (ms)
    
    # Profile Configurations
    PROFILE_CONFIGS = {
        11: "640kHz, FM0, Tari 7.5μs",
        1: "640kHz, Miller2, Tari 7.5μs",
        15: "640kHz, Miller4, Tari 7.5μs",
        12: "320kHz, Miller2, Tari 15μs",
        3: "320kHz, Miller2, Tari 20μs",
        5: "320kHz, Miller4, Tari 20μs",
        7: "250kHz, Miller4, Tari 20μs",
        13: "160kHz, Miller8, Tari 20μs",
        50: "640kHz, FM0, Tari 6.25μs",
        51: "640kHz, Miller2, Tari 6.25μs",
        52: "426kHz, FM0, Tari 15μs",
        53: "640kHz, Miller4, Tari 7.5μs"
    }
    
    # Antenna Configuration
    MAX_ANTENNAS = 4
    DEFAULT_ANTENNA_POWER = 20  # dBm
    
    # Power Configuration
    MIN_POWER = 0
    MAX_POWER = 30
    
    # Session Configuration
    MIN_SESSION = 0
    MAX_SESSION = 3
    
    # Q-Value Configuration
    MIN_Q_VALUE = 0
    MAX_Q_VALUE = 15
    
    # Scan Time Configuration
    MIN_SCAN_TIME = 1
    MAX_SCAN_TIME = 255

class DevelopmentConfig(Config):
    """Cấu hình cho môi trường development"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """Cấu hình cho môi trường production"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    
    # Production settings
    HOST = os.environ.get('HOST', '127.0.0.1')
    PORT = int(os.environ.get('PORT', 5000))

class TestingConfig(Config):
    """Cấu hình cho môi trường testing"""
    TESTING = True
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Lấy cấu hình dựa trên môi trường"""
    config_name = os.environ.get('FLASK_ENV', 'default')
    return config.get(config_name, config['default']) 