"""
Cấu hình cho ứng dụng RFID Reader Web Control Panel
"""

import os

class Config:
    """
    Base configuration for the RFID Reader Web Control Panel.
    Defines common settings inherited by all environments.
    """
    # --- Flask Application Settings ---
    # SECRET_KEY: Crucial for session management and security.
    # It's highly recommended to set a strong, unique value via environment variable in production.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a_strong_default_secret_key_for_dev')

    # --- Server Host and Port ---
    # HOST: The IP address the Flask server listens on. '0.0.0.0' makes it accessible externally.
    # PORT: The port number the Flask server runs on.
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 3000))

    # --- Serial Communication Settings ---
    # DEFAULT_SERIAL_PORT: The default serial port path for the RFID reader (e.g., /dev/ttyUSB0 on Linux, COM3 on Windows).
    # DEFAULT_BAUDRATE: The default baud rate for serial communication with the reader.
    DEFAULT_SERIAL_PORT = os.environ.get('DEFAULT_SERIAL_PORT', '/dev/ttyUSB0')
    DEFAULT_BAUDRATE = int(os.environ.get('DEFAULT_BAUDRATE', 115200))

    # --- RFID Reader Protocol Defaults ---
    # These values are often used as fallback or initial settings for reader commands
    # when specific parameters are not provided by the client (e.g., UI).
    DEFAULT_READER_ADDRESS = 0x00 # Standard address for many RS485/UART readers
    DEFAULT_Q_VALUE = 4           # Default Q value for inventory rounds (0-15)
    DEFAULT_SESSION = 0           # Default Session (S0, S1, S2, S3) for inventory (0-3)
    DEFAULT_ANTENNA_ID = 1        # Default antenna port to use (1-based)
    DEFAULT_INVENTORY_SCAN_TIME_SECONDS = 10 # Default duration for a continuous inventory scan

    # --- WebSocket Configuration (for Flask-SocketIO) ---
    # SOCKETIO_ASYNC_MODE: Specifies the asynchronous mode. 'threading' is common for simple Flask apps.
    # SOCKETIO_CORS_ALLOWED_ORIGINS: Defines which origins (frontends) are allowed to connect via WebSocket.
    # Use '*' for development; specify concrete origins (e.g., "http://localhost:3001") for production.
    SOCKETIO_ASYNC_MODE = 'threading' 
    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"

    # --- Logging Settings ---
    # LOG_LEVEL: Minimum logging level to capture (e.g., 'INFO', 'DEBUG', 'WARNING', 'ERROR').
    # LOG_FORMAT: Format string for log messages.
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # --- Frontend/UI Behavior Settings ---
    # MAX_TAGS_DISPLAY: Maximum number of tags to keep in the UI display buffer (uses deque).
    # AUTO_REFRESH_INTERVAL_MS: Interval (in milliseconds) for UI elements to auto-refresh (if applicable).
    MAX_TAGS_DISPLAY = 100
    AUTO_REFRESH_INTERVAL_MS = 5000

    # --- RFID Hardware Capabilities & Constraints ---
    # These define the valid operating ranges and limits for the RFID reader,
    # used for input validation in the application logic.
    MAX_ANTENNAS = 4
    DEFAULT_ANTENNA_POWER_DBM = 12 # Default transmit power in dBm

    # Power Configuration Limits (dBm)
    POWER_MIN_DBM = 0
    POWER_MAX_DBM = 30 
    
    # Session Configuration Limits
    SESSION_MIN = 0
    SESSION_MAX = 3
    
    # Q-Value Configuration Limits
    Q_VALUE_MIN = 0
    Q_VALUE_MAX = 15
    
    # Scan Time Configuration Limits (seconds)
    SCAN_TIME_MIN_SECONDS = 1
    SCAN_TIME_MAX_SECONDS = 255

    # --- Example Profile Configurations ---
    # Define sets of baseband parameters for different operating scenarios (e.g., speed vs. density).
    # These can be customized to match your specific reader's capabilities or application needs.
    PROFILE_CONFIGS = {
        1: {"name": "Performance", "speed": 0, "q_value": 7, "session": 0, "inventory_flag": 1},
        2: {"name": "Density", "speed": 1, "q_value": 4, "session": 1, "inventory_flag": 0},
        3: {"name": "Balanced", "speed": 2, "q_value": 5, "session": 2, "inventory_flag": 2},
    }

class DevelopmentConfig(Config):
    """
    Configuration specifically for the development environment.
    Enables debugging, sets a more verbose log level, and can use a different port.
    """
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    # Optional: Override HOST/PORT here if you want a different address
    # or port specifically for development, e.g., '127.0.0.1' for local access only.
    # PORT = 5000 # Example: run development on a different port than default 3000


class ProductionConfig(Config):
    """
    Configuration specifically for the production environment.
    Disables debugging, sets a less verbose log level (INFO), and ensures
    appropriate host/port defaults for deployment.
    """
    DEBUG = False
    LOG_LEVEL = 'INFO' # Changed from 'WARNING' to 'INFO' for better operational visibility.
                       # 'WARNING' can miss important system health details.
    
    # In production, it's common to listen on all interfaces but use environment
    # variables for the port, defaulting to a standard HTTP port like 5000 or 80.
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))


class TestingConfig(Config):
    """
    Configuration specifically for the testing environment.
    Enables debugging and sets a verbose log level suitable for automated tests.
    Uses Flask's built-in `TESTING` flag.
    """
    TESTING = True # Activates Flask's testing mode
    DEBUG = True   # Enables debugging during tests
    LOG_LEVEL = 'DEBUG'
    # Use ephemeral ports or specific testing ports to avoid conflicts with development/production.
    PORT = int(os.environ.get('TEST_PORT', 5001)) # Often uses a different port for tests


# --- Configuration Mapping ---
# This dictionary maps environment names (typically from FLASK_ENV) to their
# corresponding configuration class instances.
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig # 'default' will use DevelopmentConfig if FLASK_ENV is not set
}

def get_config() -> Config:
    """
    Retrieves the configuration class instance based on the 'FLASK_ENV'
    environment variable. If 'FLASK_ENV' is not set or its value
    does not match a defined configuration, it defaults to 'development'.
    """
    config_name = os.environ.get('FLASK_ENV', 'default')
    # Retrieve the configuration class from the map,
    # and then instantiate it by calling it (e.g., DevelopmentConfig()).
    return config_map.get(config_name, config_map['default'])()