import serial
import serial.tools.list_ports
import time
import threading
import struct
from enum import IntEnum, unique
from typing import Callable, Optional, Tuple, Dict, List, Any

# --- Constants ---
# CRC-16 CCITT (XMODEM) parameters
CRC16_CCITT_INIT: int = 0x0000
CRC16_CCITT_POLY: int = 0x8005

# Frame Protocol constants
FRAME_HEADER: int = 0x5A
PROTO_TYPE: int = 0x00
PROTO_VER: int = 0x01

# Flags used in the Protocol Control Word (PCW)
RS485_FLAG: int = 0x00 # Indicates RS485 communication (0x00 means not RS485 for upper computer commands)
READER_NOTIFY_FLAG: int = 0x00 # Set to 0 for upper computer commands (i.e., not a notification from reader)

# --- UART Connection Class ---
class UARTConnection:
    """
    Manages the serial (UART) communication with an RFID reader.
    Handles opening, closing, sending, and receiving raw bytes,
    and managing a thread-safe lock for serial port access.
    """
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.5):
        """
        Initializes the UARTConnection class.

        Args:
            port (str): Serial port path (e.g., 'COM3' on Windows, '/dev/ttyUSB0' on Linux).
            baudrate (int): Baud rate for the serial connection (default: 115200).
            timeout (float): Read timeout in seconds.
        """
        self.port_name: str = port
        self.baudrate: int = baudrate
        self.timeout: float = timeout
        self.ser: Optional[serial.Serial] = None
        self.lock: threading.Lock = threading.Lock() # Ensures thread-safe access to the serial port

        # These attributes are primarily managed by NationReader, but initialized here as per original code.
        self._inventory_running: bool = False # Flag to control inventory loop
        self._inventory_thread: Optional[threading.Thread] = None # Reference to inventory thread
        self.beeper_mode: int = 0 # 0 = No Beep, 1 = Always Beep, 2 = Beep on New Tag

    def open(self) -> None:
        """
        Opens and configures the serial port.
        If the port is already open, it does nothing.
        Raises RuntimeError if the serial port cannot be opened.
        """
        if self.ser and self.ser.is_open:
            print(f"ℹ️ UART port {self.port_name} is already open.")
            return

        try:
            # Initialize the serial port with specified parameters
            self.ser = serial.Serial(
                port=self.port_name,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                xonxoff=False, # Disable software flow control
                rtscts=False,  # Disable hardware flow control
                dsrdtr=False   # Disable DSR/DTR flow control
            )
            # Explicitly open the port if it was just created but not auto-opened
            if not self.ser.is_open:
                self.ser.open()
            print(f"✅ UART Connected to {self.port_name} @ {self.baudrate}bps")
        except serial.SerialException as e:
            # Catch specific serial exceptions and re-raise as a generic runtime error
            raise RuntimeError(f"❌ Failed to open serial port {self.port_name}: {e}")
        except Exception as e:
            # Catch any other unexpected errors during port opening
            raise RuntimeError(f"❌ An unexpected error occurred while opening serial port {self.port_name}: {e}")


    def close(self) -> None:
        """
        Closes the serial port if it is currently open.
        """
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                print(f"🔌 UART Disconnected from {self.port_name}")
            except Exception as e:
                print(f"⚠️ Error closing serial port {self.port_name}: {e}")
        else:
            print(f"ℹ️ UART port {self.port_name} is not open, nothing to close.")

    def send(self, data: bytes) -> None:
        """
        Sends raw bytes data through the UART serial port.
        Ensures thread-safe access to the serial port.

        Args:
            data (bytes): Byte array to send.

        Raises:
            RuntimeError: If the UART port is not open.
            IOError: If there's an error writing to the serial port.
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("❌ UART port is not open. Cannot send data.")
        
        with self.lock: # Acquire lock for thread-safe write
            try:
                self.ser.write(data)
                # print(f"➡️ Sent ({len(data)} bytes): {data.hex().upper()}") # Optional: for verbose debug
            except serial.SerialTimeoutException as e:
                raise IOError(f"❌ Serial write timeout: {e}")
            except serial.SerialException as e:
                raise IOError(f"❌ Serial communication error during write: {e}")
            except Exception as e:
                raise IOError(f"❌ An unexpected error occurred during serial write: {e}")


    def receive(self, size: int = 64) -> bytes:
        """
        Receives a fixed number of bytes from the UART serial port.
        Ensures thread-safe access to the serial port.

        Args:
            size (int): Number of bytes to read (default: 64).

        Returns:
            bytes: Bytes read from the port. Returns fewer bytes if timeout occurs.

        Raises:
            RuntimeError: If the UART port is not open.
            IOError: If there's an error reading from the serial port.
        """
        if not self.ser or not self.ser.is_open:
            raise RuntimeError("❌ UART port is not open. Cannot receive data.")
        
        with self.lock: # Acquire lock for thread-safe read
            try:
                # `ser.read()` will block up to `self.timeout` seconds
                data_read = self.ser.read(size)
                # print(f"⬅️ Received ({len(data_read)} bytes): {data_read.hex().upper()}") # Optional: for verbose debug
                return data_read
            except serial.SerialTimeoutException as e:
                # print(f"⚠️ Serial read timeout: {e}") # This can be expected if no data
                return b"" # Return empty bytes on timeout
            except serial.SerialException as e:
                raise IOError(f"❌ Serial communication error during read: {e}")
            except Exception as e:
                raise IOError(f"❌ An unexpected error occurred during serial read: {e}")


    def send_raw_bytes(self, frame: bytes) -> None:
        """
        Sends raw bytes through UART. This method appears to be a duplicate
        of `send` but with added print statements and a `serial_port` attribute.
        It's included for refactoring only as per the instruction.
        NOTE: This method refers to `self.serial_port` which is not defined
        in `__init__`, it should likely be `self.ser`. Assuming `self.ser`.
        """
        if not self.ser or not self.ser.is_open:
            raise IOError("❌ Serial port not open. Cannot send raw bytes.")
        
        print(f"➡️ Sending ({len(frame)} bytes): {frame.hex()}")
        try:
            self.ser.write(frame)
            self.ser.flush() # Ensure all buffered data is written
        except serial.SerialTimeoutException as e:
            raise IOError(f"❌ Serial write timeout in send_raw_bytes: {e}")
        except serial.SerialException as e:
            raise IOError(f"❌ Serial communication error in send_raw_bytes: {e}")
        except Exception as e:
            raise IOError(f"❌ An unexpected error occurred in send_raw_bytes: {e}")


    def flush_input(self) -> None:
        """
        Flushes the input buffer of the serial port to discard old, unread data.
        """
        if self.ser:
            try:
                self.ser.reset_input_buffer()
                # print("Buffer input cleared.") # Optional: for verbose debug
            except serial.SerialException as e:
                print(f"⚠️ Error flushing input buffer: {e}")
            except Exception as e:
                print(f"⚠️ An unexpected error occurred while flushing input buffer: {e}")


    def is_open(self) -> bool:
        """
        Checks if the serial port is currently open.

        Returns:
            bool: True if the serial port is open, False otherwise.
        """
        return self.ser.is_open if self.ser else False

# --- MID (Message ID) Enum ---
@unique
class MID(IntEnum):
    """
    Enumeration of Message IDs (MIDs) used in the RFID reader's protocol.
    Each MID represents a specific command or response type.
    MIDs can be composed of a Category (high byte) and a Code (low byte).
    """
    # Reader Configuration Commands (Category 0x01)
    QUERY_INFO: int = 0x0100 # Query basic reader information (e.g., serial, firmware)
    CONFIRM_CONNECTION: int = 0x12 # Not explicitly used as a direct command in all flows

    # RFID Inventory Commands (Category 0x02)
    READ_EPC_TAG: int = (0x02 << 8) | 0x10 # Command to start EPC tag inventory
    STOP_INVENTORY: int = (0x02 << 8) | 0xFF # Command to stop ongoing inventory

    # General Operation Codes (often used as low byte for responses/notifications)
    STOP_OPERATION: int = 0xFF # Response MID for successful stop operations
    READ_END: int = 0x1231 # Notification MID indicating end of a read/inventory cycle (composite MID)
    ERROR_NOTIFICATION: int = 0x00 # Generic error notification MID

    # RFID Baseband Commands (Category 0x02)
    CONFIG_BASEBAND: int = 0x020B # Configure baseband parameters (e.g., Q-value, session)
    QUERY_BASEBAND: int = 0x020C # Query current baseband parameters

    # Power Control Commands (Category 0x02)
    CONFIGURE_READER_POWER: int = 0x0201 # Configure transmit power for antennas
    QUERY_READER_POWER: int = 0x0202 # Query current transmit power for antennas
    SET_READER_POWER_CALIBRATION: int = 0x0103 # (Not fully implemented in provided code, for reference)

    # Buzzer Control Commands (Category 0x01)
    BUZZER_SWITCH: int = (0x01 << 8) | 0x1E # Command to control the reader's buzzer

    # Filter Settings (Category 0x02)
    QUERY_FILTER: int = 0x020A # Query tag filtering settings (e.g., repeat time, RSSI threshold)
    SET_FILTER: int = 0x0209 # Set tag filtering parameters

    # Write EPC Tag (Category 0x02)
    WRITE_EPC_TAG_COMMAND: int = 0x0211 # Command to write EPC data to a tag (renamed to avoid conflict with MID enum name)

    # RF Band Control (Category 0x02)
    QUERY_RF_BAND_COMMAND: int = 0x0204 # Query current RF frequency band (renamed to avoid conflict)
    SET_RF_BAND_COMMAND: int = 0x0203 # Set RF frequency band (renamed to avoid conflict)

    # Working Frequency Channels (Category 0x02)
    QUERY_WORKING_FREQUENCY: int = 0x0206 # Query working frequency channels (auto/manual)


# --- NationReader Class ---
class NationReader:
    """
    Provides a high-level interface for interacting with a Nation RFID reader,
    handling protocol framing, CRC calculation, and specific reader commands.
    """
    # Class-level default timeout
    DEFAULT_TIMEOUT: float = 0.5

    # Class-level defaults for port and baudrate (can be set dynamically)
    # These are commented out as they are often handled by a separate configuration system (e.g., config.py)
    # DEFAULT_PORT: Optional[str] = None
    # DEFAULT_BAUDRATE: Optional[int] = None

    @classmethod
    def set_uart_defaults(cls, port: str, baudrate: int, timeout: float = 0.5) -> None:
        """
        Sets class-level default values for UART connection parameters.
        These are typically used if no values are provided during instantiation.

        Args:
            port (str): Default serial port path.
            baudrate (int): Default baud rate.
            timeout (float): Default read timeout in seconds.
        """
        cls.DEFAULT_PORT: str = port
        cls.DEFAULT_BAUDRATE: int = baudrate
        cls.DEFAULT_TIMEOUT: float = timeout

    def __init__(self, port: str, baudrate: int, timeout: Optional[float] = None):
        """
        Initializes the NationReader instance.

        Args:
            port (str): Serial port path for the reader.
            baudrate (int): Baud rate for communication.
            timeout (Optional[float]): Read timeout in seconds. If None, uses class default.
        """
        # Assign port and baudrate, falling back to class defaults if available
        self.port: str = port or getattr(NationReader, 'DEFAULT_PORT', '/dev/ttyUSB0')
        self.baudrate: int = baudrate or getattr(NationReader, 'DEFAULT_BAUDRATE', 115200)
        self.timeout: float = timeout or NationReader.DEFAULT_TIMEOUT

        # Initialize the underlying UART communication layer
        self.uart: UARTConnection = UARTConnection(self.port, self.baudrate, self.timeout)
        
        self.rs485: bool = False # Flag indicating if RS485 mode is active
        # Dictionary to store extended antenna hub masks (e.g., for external antenna multiplexers)
        self._ext_ant_masks: Dict[int, int] = {i: 0 for i in range(1, 33)} # Main Ant 1–32
        self.antenna_mask: int = 0x00000001 # Current active antenna mask (default to Antenna 1)


    def open(self) -> None:
        """
        Opens the underlying UART connection to the reader.
        Delegates to the UARTConnection's open method.
        """
        self.uart.open()

    def close(self) -> None:
        """
        Closes the underlying UART connection to the reader.
        Also flushes any pending input data.
        """
        self.uart.flush_input()
        self.uart.close()

    def send(self, data: bytes) -> None:
        """
        Sends raw bytes data through the reader's UART connection.
        Delegates to the UARTConnection's send method.

        Args:
            data (bytes): The byte array to send.
        """
        self.uart.send(data)

    def receive(self, size: int) -> bytes:
        """
        Receives a fixed number of bytes from the reader's UART connection.
        Delegates to the UARTConnection's receive method.

        Args:
            size (int): The number of bytes to read.

        Returns:
            bytes: The bytes received from the port.
        """
        return self.uart.receive(size)

    @staticmethod
    def crc16_ccitt(data: bytes) -> int:
        """
        Calculates the CRC-16 CCITT (XMODEM) checksum for a given byte sequence.

        Args:
            data (bytes): The input byte sequence.

        Returns:
            int: The calculated 16-bit CRC checksum.
        """
        crc: int = CRC16_CCITT_INIT
        for byte_val in data:
            crc ^= byte_val << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ CRC16_CCITT_POLY) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc


    @classmethod
    def build_frame(cls, mid: Any, payload: bytes = b"", rs485: bool = False, notify: bool = False) -> bytes:
        """
        Constructs a complete protocol frame for communication with the RFID reader.

        Args:
            mid (Any): The Message ID (MID), can be an IntEnum member or an integer value.
            payload (bytes): The data payload of the frame (default: empty bytes).
            rs485 (bool): True if RS485 mode is active, requiring an address byte (default: False).
            notify (bool): True if this frame is a notification from the reader (default: False).

        Returns:
            bytes: The complete framed byte sequence including header, PCW, address (if RS485),
                   length, payload, and CRC.
        """
        frame_header_byte: bytes = b'\x5A'

        # Extract MID value from IntEnum if applicable, otherwise use directly
        mid_value: int = getattr(mid, 'value', mid)
        category: int = (mid_value >> 8) & 0xFF
        mid_code: int = mid_value & 0xFF

        # Build Protocol Control Word (PCW)
        pcw: int = cls.build_pcw(category, mid_code, rs485=rs485, notify=notify)
        pcw_bytes: bytes = pcw.to_bytes(4, 'big')

        # Add RS485 address byte if RS485 mode is enabled
        addr_bytes: bytes = b'\x00' if rs485 else b'' # Default address 0x00 for RS485

        # Calculate payload length and convert to 2-byte big-endian
        length_bytes: bytes = len(payload).to_bytes(2, 'big')

        # Assemble the content for CRC calculation
        frame_content_for_crc: bytes = pcw_bytes + addr_bytes + length_bytes + payload
        
        # Calculate CRC and convert to 2-byte big-endian
        crc_bytes: bytes = cls.crc16_ccitt(frame_content_for_crc).to_bytes(2, 'big')

        # Assemble the final frame
        return frame_header_byte + frame_content_for_crc + crc_bytes


    @classmethod
    def build_pcw(cls, category: int, mid: int, rs485: bool = False, notify: bool = False) -> int:
        """
        Constructs the 4-byte Protocol Control Word (PCW) for a frame.

        Args:
            category (int): The category byte of the command (high byte of MID).
            mid (int): The Message ID code (low byte of MID).
            rs485 (bool): True if RS485 flag should be set in PCW (bit 13).
            notify (bool): True if reader notification flag should be set in PCW (bit 12).

        Returns:
            int: The 32-bit integer representing the PCW.
        """
        # Initialize PCW with Protocol Type (bits 24-31) and Protocol Version (bits 16-23)
        pcw: int = (PROTO_TYPE << 24) | (PROTO_VER << 16)
        
        # Set RS485 flag if active
        if rs485:
            pcw |= (1 << 13) # Set bit 13
        
        # Set Notification flag if active
        if notify:
            pcw |= (1 << 12) # Set bit 12
        
        # Combine category (bits 8-15) and MID code (bits 0-7)
        pcw |= (category << 8) | mid
        return pcw

    @classmethod
    def parse_frame(cls, raw: bytes) -> Dict[str, Any]:
        """
        Parses a raw byte sequence received from the RFID reader into a structured dictionary.
        Performs header validation, extracts PCW fields, data length, payload, and verifies CRC.

        Args:
            raw (bytes): The full raw frame bytes, including the header.

        Returns:
            dict: A dictionary containing parsed frame components (e.g., 'valid', 'type', 'mid', 'data').

        Raises:
            ValueError: If the frame is too short, has an invalid header, or CRC mismatch.
        """
        if len(raw) < 9: # Minimum frame length: Header (1) + PCW (4) + Length (2) + CRC (2)
            raise ValueError("Frame too short. Minimum 9 bytes required.")

        if raw[0] != FRAME_HEADER:
            raise ValueError(f"Invalid frame header. Expected 0x{FRAME_HEADER:02X}, got 0x{raw[0]:02X}.")

        offset: int = 1 # Start parsing after the frame header

        # --- Protocol Control Word (PCW) ---
        pcw_bytes: bytes = raw[offset:offset+4]
        pcw: int = int.from_bytes(pcw_bytes, 'big')
        offset += 4

        # Extract individual fields from PCW
        proto_type: int = (pcw >> 24) & 0xFF
        proto_ver: int = (pcw >> 16) & 0xFF
        rs485_flag: int = (pcw >> 13) & 0x01
        notify_flag: int = (pcw >> 12) & 0x01
        category: int = (pcw >> 8) & 0xFF
        mid: int = pcw & 0xFF

        response_type: str = "notification" if notify_flag else "response"

        # --- Optional Serial Address (for RS485) ---
        addr: Optional[int] = None
        if rs485_flag:
            if offset >= len(raw):
                raise ValueError("Frame truncated: Missing RS485 address byte.")
            addr = raw[offset]
            offset += 1

        # --- Data Length ---
        if offset + 2 > len(raw):
            raise ValueError("Frame truncated: Missing data length bytes.")
        data_len: int = int.from_bytes(raw[offset:offset+2], 'big')
        offset += 2

        # --- Data Payload ---
        # Check if entire payload and CRC can fit within the remaining raw bytes
        if offset + data_len + 2 > len(raw): # +2 for CRC bytes
            raise ValueError(f"Frame length mismatch or truncated. Expected {data_len} data bytes + 2 CRC, but only {len(raw) - offset - 2} available.")
        
        data_payload: bytes = raw[offset:offset + data_len]
        offset += data_len

        # --- CRC Checksum ---
        received_crc: int = int.from_bytes(raw[offset:offset+2], 'big')
        calculated_crc: int = cls.crc16_ccitt(raw[1:offset]) # CRC is calculated from PCW onwards, excluding header

        if received_crc != calculated_crc:
            raise ValueError(f"CRC mismatch! Got 0x{received_crc:04X}, expected 0x{calculated_crc:04X}.")

        # Return parsed components as a dictionary
        return {
            "valid": True,
            "type": response_type,
            "proto_type": proto_type,
            "proto_ver": proto_ver,
            "rs485": bool(rs485_flag),
            "notify": bool(notify_flag),
            "pcw": pcw,
            "category": category,
            "mid": mid,
            "address": addr,
            "data_length": data_len,
            "data": data_payload,
            "crc": received_crc,
            "raw": raw
        }

    def extract_valid_frames(self, data: bytes) -> List[bytes]:
        """
        Extracts all complete and valid protocol frames from a raw byte stream.
        This function is crucial for handling fragmented or concatenated messages
        from the serial port.

        Args:
            data (bytes): The raw byte stream to parse.

        Returns:
            list[bytes]: A list of valid, complete frames found in the stream.
        """
        frames: List[bytes] = []
        i: int = 0
        
        while i < len(data):
            # Find the start of a frame (FRAME_HEADER)
            if data[i] != FRAME_HEADER:
                i += 1
                continue # Skip to the next byte if not a header

            # Check if enough bytes are available for minimum frame length (Header + PCW + Length + CRC)
            if i + 9 > len(data):
                # Not enough data for a complete minimum frame, break and wait for more data
                break

            # Peek into PCW to determine if RS485 address byte is present
            pcw_peek: int = int.from_bytes(data[i+1:i+5], 'big')
            rs485_flag_peek: int = (pcw_peek >> 13) & 0x01
            
            # Extract payload length
            length_bytes_peek: bytes = data[i+5:i+7]
            length: int = int.from_bytes(length_bytes_peek, 'big')
            
            # Calculate full expected frame length
            addr_len: int = 1 if rs485_flag_peek else 0
            full_len: int = 1 + 4 + addr_len + 2 + length + 2 # Header + PCW + Addr + Length + Payload + CRC

            # Check if entire expected frame fits in the current buffer
            if i + full_len > len(data):
                # Not enough data for this specific frame, break and wait for more
                break

            # Extract the potential frame
            frame: bytes = data[i : i + full_len]
            
            # Calculate CRC for validation (excluding header and final CRC bytes)
            calculated_crc: int = self.crc16_ccitt(frame[1:-2])
            # Extract received CRC (last 2 bytes of the frame)
            received_crc: int = int.from_bytes(frame[-2:], 'big')

            if calculated_crc == received_crc:
                frames.append(frame) # Add valid frame to the list
            else:
                # Log CRC mismatch but continue searching for other frames
                print(f"⚠️ CRC mismatch at index {i}: expected=0x{calculated_crc:04X}, got=0x{received_crc:04X}. Discarding frame.")
            
            # Move index past the processed (valid or invalid) frame
            i += full_len

        return frames

    def Connect_Reader_And_Initialize(self) -> bool:
        """
        Attempts to connect to the RFID reader and initialize it by sending a STOP command.
        This ensures the reader is in an idle state before further operations.

        Returns:
            bool: True if initialization is successful, False otherwise.
        """
        try:
            # Clear any stale data in the input buffer
            self.uart.flush_input()

            print("🚀 Sending STOP command to ensure Idle state...")
            # Build and send the STOP INVENTORY command frame
            stop_frame: bytes = self.build_frame(MID.STOP_INVENTORY, payload=b'', rs485=self.rs485, notify=False)
            self.uart.send(stop_frame)

            time.sleep(0.1) # Give the reader a moment to process and respond
            raw_response: bytes = self.uart.receive(64) # Read expected response size

            if not raw_response:
                print("❌ No response received after sending STOP command.")
                return False

            # Parse the received response frame
            frame: Dict[str, Any] = self.parse_frame(raw_response)
            print(f"🔍 Response MID: 0x{frame['mid']:02X}, Data: {frame['data'].hex().upper()}")

            # Check if the response is a successful STOP_OPERATION confirmation
            # MID.STOP_OPERATION is 0xFF. If a category is combined, we check only the low byte.
            if (frame["mid"] == MID.STOP_OPERATION or frame["mid"] == (MID.STOP_INVENTORY & 0xFF)) and \
               len(frame["data"]) > 0 and frame["data"][0] == 0x00: # Check for success code 0x00
                print("✅ Reader successfully initialized (STOP confirmed and idle).")
                return True
            else:
                print("❌ Invalid STOP response received. Reader might not be idle.")
                return False

        except Exception as e:
            print(f"❌ Exception during reader initialization (Connect_Reader_And_Initialize): {e}")
            return False

    def query_rfid_ability(self) -> Dict[str, Any]:
        """
        Sends the 'Query RFID Ability' command (MID=0x00, Category=0x10) to the reader
        to retrieve its capabilities, such as power range, antenna count, and supported protocols/frequencies.

        Returns:
            dict: A dictionary containing reader capabilities, or an empty dictionary on failure.
        """
        try:
            self.uart.flush_input() # Clear input buffer before sending command
            
            # Build the command frame (Category 0x10, MID 0x00)
            frame: bytes = self.build_frame(mid=0x1000, payload=b'', rs485=self.rs485, notify=False)
            self.uart.send(frame)

            time.sleep(0.1) # Short delay to await response
            raw_response: bytes = self.uart.receive(128) # Receive enough bytes for ability data
            if not raw_response:
                print("❌ No response received from reader for RFID ability query.")
                return {}

            frames: List[bytes] = self.extract_valid_frames(raw_response)
            print(f"📦 Raw frames count received for RFID ability: {len(frames)}")

            for idx, received_frame in enumerate(frames):
                print(f"📦 Processing Frame[{idx}]: {received_frame.hex().upper()}")
                try:
                    parsed_frame: Dict[str, Any] = self.parse_frame(received_frame)
                    mid_response: int = parsed_frame.get("mid", -1)
                    cat_response: int = parsed_frame.get("category", -1)
                    
                    print(f"🔎 Parsed MID: 0x{mid_response:02X}, CAT: 0x{cat_response:02X}")
                    
                    # Check if the response matches the expected MID (Category 0x10, Code 0x00)
                    if cat_response == 0x10 and mid_response == 0x00:
                        payload_data: bytes = parsed_frame.get("data", b"")
                        print(f"🔍 Payload Bytes: {payload_data.hex().upper()}")

                        if len(payload_data) < 3:
                            print("❌ Payload too short for RFID ability. Expected at least 3 bytes.")
                            continue # Continue to next frame if current is too short

                        # Extract core ability parameters
                        max_power: int = payload_data[0]
                        min_power: int = payload_data[1]
                        antenna_count: int = payload_data[2]

                        freq_list: List[int] = []
                        protocols: List[int] = []

                        # Attempt to parse optional frequency and protocol lists
                        try:
                            # Frequency List (starts at offset 3, 1 byte length, then data)
                            if len(payload_data) > 3:
                                freq_list_len: int = payload_data[3]
                                if 4 + freq_list_len <= len(payload_data):
                                    freq_list = list(payload_data[4 : 4 + freq_list_len])
                                    print(f"📡 Frequency List Length: {freq_list_len}, Data: {freq_list}")

                                    # Protocol List (starts after freq_list, 1 byte length, then data)
                                    protocol_offset: int = 4 + freq_list_len
                                    if protocol_offset < len(payload_data):
                                        protocol_list_len: int = payload_data[protocol_offset]
                                        if protocol_offset + 1 + protocol_list_len <= len(payload_data):
                                            protocols = list(payload_data[protocol_offset + 1 : protocol_offset + 1 + protocol_list_len])
                                            print(f"📚 Protocol List Length: {protocol_list_len}, Data: {protocols}")
                                        else:
                                            print("ℹ️ Protocol list data truncated.")
                                else:
                                    print("ℹ️ Frequency list data truncated.")
                        except IndexError:
                            # This can happen if payload is shorter than expected for lists
                            print("ℹ️ Reader reports no frequencies or protocols (payload too short for lists).")

                        # Return the parsed ability data
                        return {
                            "min_power_dbm": min_power,
                            "max_power_dbm": max_power,
                            "antenna_count": antenna_count,
                            "frequencies": freq_list,
                            "rfid_protocols": protocols
                        }
                except ValueError as ve:
                    print(f"⚠️ Frame parsing error for frame[{idx}]: {ve}. Skipping.")
                except Exception as ex:
                    print(f"⚠️ An unexpected error occurred parsing frame[{idx}]: {ex}. Skipping.")

            print("❌ No matching response frame found for RFID ability after checking all frames.")
            return {}

        except Exception as e:
            print(f"❌ Error in query_rfid_ability: {e}")
            return {}


    def Query_Reader_Information(self) -> Dict[str, Any]:
        """
        Sends the 'Query Reader Information' command (MID=0x00, Category=0x01)
        and parses the response to extract reader details like serial number,
        firmware versions, and uptime.

        Returns:
            dict: A dictionary containing parsed reader information, or an empty dict on failure.
        """
        try:
            self.uart.flush_input() # Clear input buffer

            # Build the query info frame
            frame: bytes = self.build_frame(MID.QUERY_INFO, payload=b'', rs485=self.rs485, notify=False)
            self.uart.send(frame)

            time.sleep(0.1) # Short delay for response
            raw_response: bytes = self.uart.receive(128) # Receive enough bytes for info
            if not raw_response:
                print("❌ No response received from reader for Query_Reader_Information.")
                return {}

            parsed_frame_data: Dict[str, Any] = self.parse_frame(raw_response)

            # Check for the expected response MID (0x00) and Category (0x01)
            if parsed_frame_data['mid'] != 0x00 or parsed_frame_data['category'] != 0x01:
                print(f"❌ Unexpected MID (0x{parsed_frame_data['mid']:02X}) or Category (0x{parsed_frame_data['category']:02X}) "
                      f"in response to Query_Reader_Information. Expected MID 0x00, CAT 0x01.")
                return {}

            # Parse the data payload using the static helper method
            return self._parse_query_info_data(parsed_frame_data['data']) or {}

        except Exception as e:
            print(f"❌ Exception in Query_Reader_Information: {e}")
            return {}

    @staticmethod
    def _parse_query_info_data(data: bytes) -> Dict[str, Any]:
        """
        Parses the data payload from a 'Query Reader Information' response.
        This static method extracts serial number, power-on time, and software versions.

        Args:
            data (bytes): The data payload from the reader information response.

        Returns:
            dict: A dictionary containing the parsed information.
        """
        result: Dict[str, Any] = {}
        offset: int = 0

        try:
            # 1. Serial Number (Tag: 0x00, then 1-byte length, then ASCII string)
            # The protocol doc shows this as `TAG | LEN | SN_BYTES`.
            # The Python code assumes data[offset] is TAG and data[offset+1] is LEN.
            # Assuming implicit TAG 0x00 for SN
            if offset + 2 > len(data): # Need at least 2 bytes for (implicit_TAG + SN_LENGTH)
                print("⚠️  Data too short for Serial Number length.")
                return result
            
            # The Python code implicitly assumes the first section is Serial Number,
            # where data[offset+1] is the length.
            # If the protocol uses a PID before length, this needs adjustment.
            # Sticking to the original logic: assuming PID is implicitly handled or not present here.
            sn_length: int = data[offset + 1] 
            if offset + 2 + sn_length > len(data):
                print(f"⚠️  Data too short for Serial Number payload (expected {sn_length} bytes).")
                return result
            serial_num: str = data[offset + 2:offset + 2 + sn_length].decode('ascii', errors='ignore')
            result['serial_number'] = serial_num.strip()
            offset += 2 + sn_length # Advance past (implicit_TAG + SN_LENGTH + SN_BYTES)

            # 2. Power-on time (U32) (4 bytes)
            if offset + 4 > len(data):
                print("⚠️  Data too short for Power-on Time.")
                return result
            result['power_on_time_sec'] = int.from_bytes(data[offset:offset + 4], 'big')
            offset += 4

            # 3. Baseband compile time (Tag 0x00, then 1-byte length, then ASCII string)
            # Note: This is a tagged field, but the original code assumes it directly follows power-on time
            # and that data[offset] is implicitly its PID (0x00) and data[offset+1] its length.
            if offset + 2 > len(data):
                print("⚠️  Data too short for Baseband Compile Time length.")
                return result
            bb_len: int = data[offset + 1] # Length of baseband compile time string
            if offset + 2 + bb_len > len(data):
                print(f"⚠️  Data too short for Baseband Compile Time payload (expected {bb_len} bytes).")
                return result
            baseband_time: str = data[offset + 2:offset + 2 + bb_len].decode('ascii', errors='ignore')
            result['baseband_compile_time'] = baseband_time.strip()
            offset += 2 + bb_len # Advance past (TAG + LEN + BB_TIME_BYTES)

            # 4. Optional tagged fields (e.g., app_version, os_version, app_compile_time)
            # These are typically in TLV (Tag-Length-Value) format
            while offset + 2 <= len(data): # Ensure there's at least TAG (1) + LENGTH (1) bytes left
                tag_id: int = data[offset]
                length: int = data[offset + 1]
                
                if offset + 2 + length > len(data):
                    print(f"⚠️  Optional tag 0x{tag_id:02X} data truncated (expected {length} bytes, but not enough remain).")
                    break # Break if remaining data is insufficient for declared length
                
                value_bytes: bytes = data[offset + 2:offset + 2 + length]
                offset += 2 + length # Advance past (TAG + LEN + VALUE_BYTES)

                if tag_id == 0x01 and len(value_bytes) == 4:
                    # Application Version (U32, major.minor.patch.build)
                    version_val: int = int.from_bytes(value_bytes, 'big')
                    result['app_version'] = f"V{(version_val>>24)&0xFF}.{(version_val>>16)&0xFF}.{(version_val>>8)&0xFF}.{version_val&0xFF}"
                elif tag_id == 0x02:
                    # OS Version (ASCII string)
                    result['os_version'] = value_bytes.decode('ascii', errors='ignore').strip()
                elif tag_id == 0x03:
                    # Application Compile Time (ASCII string)
                    result['app_compile_time'] = value_bytes.decode('ascii', errors='ignore').strip()
                else:
                    # print(f"ℹ️ Unknown optional tag 0x{tag_id:02X} with length {length} encountered. Skipping.")
                    continue # Skip unknown tags

        except Exception as e:
            result['error'] = f"Parsing exception in _parse_query_info_data: {e}"
            print(f"❌ Error during _parse_query_info_data: {e}")

        return result

    def save_antenna_mask(self, antenna_mask: int) -> bool:
        """
        Saves the 32-bit antenna mask. This is a local variable assignment
        and does not send a command to the reader.

        Args:
            antenna_mask (int): A 32-bit integer representing the antenna mask.

        Returns:
            bool: True if the mask was successfully saved (always True if input is valid).

        Raises:
            ValueError: If the antenna mask is not within the 32-bit unsigned integer range.
        """
        if not (0 <= antenna_mask <= 0xFFFFFFFF):
            raise ValueError("Antenna mask must be a 32-bit unsigned integer (0 to 0xFFFFFFFF).")
        self.antenna_mask = antenna_mask
        print(f"✅ Local antenna mask set to: 0x{self.antenna_mask:08X}")
        return True


    def build_epc_read_payload(self, antenna_mask: int, continuous: bool = True) -> bytes:
        """
        Builds the data payload for the 'Read EPC Tag' command (MID=0x10).

        Args:
            antenna_mask (int): A 32-bit integer bitmask indicating which antennas to use.
            continuous (bool): If True, performs continuous inventory (0x01); if False, single read (0x00).

        Returns:
            bytes: The constructed payload bytes.

        Raises:
            ValueError: If the antenna mask is out of the valid 32-bit range.
        """
        # If antenna_mask is 0 (no antennas selected), default to the first antenna
        if antenna_mask == 0:
            antenna_mask = 0x00000001
            print("⚠️ Antenna mask was 0, defaulting to Antenna 1 (0x00000001).")

        if not (0 <= antenna_mask <= 0xFFFFFFFF):
            raise ValueError("Antenna mask must be a 32-bit unsigned integer (0 to 0xFFFFFFFF).")
        
        mask_bytes: bytes = antenna_mask.to_bytes(4, byteorder='big')
        mode_byte: bytes = b'\x01' if continuous else b'\x00'
        
        return mask_bytes + mode_byte

    def parse_epc(self, data: bytes) -> Dict[str, Any]:
        """
        Parses the data payload received from an EPC tag read response.
        Extracts EPC, PC, Antenna ID, and optional RSSI.

        Args:
            data (bytes): The raw data payload from the EPC tag read.

        Returns:
            dict: A dictionary containing the parsed tag data, or an error key if parsing fails.
        """
        result: Dict[str, Any] = {}
        try:
            # EPC Length (2 bytes, big-endian)
            if len(data) < 2:
                raise ValueError("Data too short to extract EPC length.")
            epc_len: int = int.from_bytes(data[0:2], 'big')

            # EPC Data (variable length based on epc_len)
            if 2 + epc_len > len(data):
                raise ValueError(f"EPC data truncated. Expected {epc_len} bytes, but only {len(data) - 2} available.")
            epc: str = data[2:2 + epc_len].hex().upper()
            result["epc"] = epc

            # PC (Protocol Control) Bits (2 bytes)
            pc_offset: int = 2 + epc_len
            if pc_offset + 2 > len(data):
                raise ValueError("Data too short to extract PC bits.")
            pc: str = data[pc_offset : pc_offset + 2].hex().upper()
            result["pc"] = pc

            # Antenna ID (1 byte)
            antenna_id_offset: int = pc_offset + 2
            if antenna_id_offset >= len(data):
                raise ValueError("Data too short to extract Antenna ID.")
            antenna_id: int = data[antenna_id_offset]
            result["antenna_id"] = antenna_id

            # Optional RSSI (if PID 0x01 and value follows)
            rssi: Optional[int] = None
            if len(data) > antenna_id_offset + 1: # Check if PID byte exists
                pid_offset: int = antenna_id_offset + 1
                pid: int = data[pid_offset]
                if pid == 0x01 and len(data) > pid_offset + 1: # Check if RSSI value exists after PID
                    rssi = data[pid_offset + 1]
            result["rssi"] = rssi
            
            return result
        except Exception as e:
            error_message: str = f"Parse error in parse_epc: {e}"
            print(f"❌ {error_message}")
            return {"error": error_message}

    def query_reader_power(self) -> Dict[int, int]:
        """
        Queries the current RF transmit power settings for all antenna ports.

        Returns:
            dict[int, int]: A dictionary where keys are antenna IDs (1-64)
                            and values are power levels in dBm. Returns an empty dict on failure.
        """
        try:
            self.stop_inventory() # Ensure reader is idle before querying
            print("🚀 Sending Query Reader Power command...")
            
            # Build command frame for QUERY_READER_POWER (MID 0x0202)
            command_frame: bytes = self.build_frame(MID.QUERY_READER_POWER, payload=b'', rs485=self.rs485, notify=False)
            self.uart.flush_input() # Clear input buffer
            self.uart.send(command_frame)

            time.sleep(0.1) # Give reader time to respond
            raw_response: bytes = self.uart.receive(128) # Receive enough bytes for multiple antenna responses

            if not raw_response:
                print("❌ No response received from reader for power query.")
                return {}

            parsed_frame: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_frame["mid"]
            data_payload: bytes = parsed_frame["data"]

            print(f"🔍 Response MID: 0x{mid_response:02X}, Data: {data_payload.hex().upper()}")

            # Expected response MID is the low byte of QUERY_READER_POWER (0x02)
            if mid_response == (MID.QUERY_READER_POWER & 0xFF):
                power_settings: Dict[int, int] = {}
                offset: int = 0
                while offset + 2 <= len(data_payload): # Each power entry is 2 bytes (Antenna ID + Value)
                    ant_id: int = data_payload[offset]   # PID is antenna ID [Protocol Spec]
                    power_dbm: int = data_payload[offset + 1] # Value is power in dBm [Protocol Spec]
                    power_settings[ant_id] = power_dbm
                    offset += 2
                return power_settings
            else:
                print(f"❌ Unexpected response MID (0x{mid_response:02X}) for power query. Expected 0x{(MID.QUERY_READER_POWER & 0xFF):02X}.")
                return {}

        except ValueError as ve:
            print(f"❌ Data parsing error during power query: {ve}")
            return {}
        except Exception as e:
            print(f"❌ An unexpected exception occurred during power query: {e}")
            return {}

    def configure_reader_power(self, antenna_powers: Dict[int, int], persistence: Optional[bool] = None) -> bool:
        """
        Configures the RF transmit power for specified antenna ports.

        Args:
            antenna_powers (dict[int, int]): A dictionary where keys are antenna IDs (1-64)
                                             and values are power levels in dBm (e.g., 0-33 for some readers).
            persistence (Optional[bool]): If True, settings are saved after power-down.
                                          If False, settings are temporary. If None, uses reader default behavior.

        Returns:
            bool: True if configuration was successful, False otherwise.
        """
        if not antenna_powers:
            print("❌ No antenna powers provided for configuration. Nothing to do.")
            return False
        
        if not isinstance(antenna_powers, dict):
            print("❌ Invalid argument: antenna_powers must be a dictionary of {int: int}.")
            return False
        
        # Build payload parts for each antenna power setting
        payload_parts: List[bytes] = []
        for ant_id, power_dbm in antenna_powers.items():
            if not isinstance(ant_id, int) or not isinstance(power_dbm, int):
                print(f"❌ Invalid types: antenna ID ({type(ant_id)}) and power ({type(power_dbm)}) must both be integers.")
                return False
            
            if not (1 <= ant_id <= 64): # Validate antenna ID range
                print(f"❌ Invalid antenna ID: {ant_id}. Must be between 1 and 64.")
                return False
            
            # The protocol spec often states max power in dBm. 36dBm is common, but 33dBm often means actual limit.
            # Sticking to original 33dBm validation as per the original code's comment.
            if not (0 <= power_dbm <= 33): 
                print(f"❌ Invalid power level for antenna {ant_id}: {power_dbm}dBm. Must be between 0 and 33dBm.")
                return False
            
            # Append PID (Antenna ID) and Value (Power dBm) bytes
            payload_parts.append(ant_id.to_bytes(1, 'big')) 
            payload_parts.append(power_dbm.to_bytes(1, 'big')) 
        
        # Add persistence parameter if specified
        if persistence is not None:
            payload_parts.append(b'\xFF') # PID for Parameter persistence [Protocol Spec]
            payload_parts.append((0x01 if persistence else 0x00).to_bytes(1, 'big')) # Value for persistence (0x01=save, 0x00=temporary)
        
        full_payload: bytes = b''.join(payload_parts)

        try:
            self.uart.flush_input() # Clear input buffer before sending
            
            # Build and send the CONFIGURE_READER_POWER command frame (MID 0x0201)
            # print(f"🚀 Sending Configure Reader Power command with payload: {full_payload.hex().upper()}") # Verbose debug
            command_frame: bytes = self.build_frame(MID.CONFIGURE_READER_POWER, payload=full_payload, rs485=self.rs485, notify=False)
            self.uart.send(command_frame)
            
            time.sleep(0.1) # Give reader time to respond
            raw_response: bytes = self.uart.receive(64) # Receive response

            if not raw_response:
                print("❌ No response received from reader for power configuration.")
                return False
            
            parsed_frame: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_frame["mid"]
            data_payload: bytes = parsed_frame["data"]
            
            print(f"🔍 Response MID: 0x{mid_response:02X}, Data: {data_payload.hex().upper()}")

            # Expected response MID is the low byte of CONFIGURE_READER_POWER (0x01)
            # Data payload should contain the result code (0x00 for success)
            if mid_response == (MID.CONFIGURE_READER_POWER & 0xFF) and len(data_payload) >= 1:
                result_code: int = data_payload[0]
                if result_code == 0x00:
                    print("✅ Reader power configured successfully.")
                    return True
                else:
                    # Map error codes to descriptive messages as per protocol spec
                    error_map: Dict[int, str] = {
                        0x01: "The reader hardware does not support the port parameter.",
                        0x02: "The reader does not support the power parameter.",
                        0x03: "Save failed (error saving configuration to non-volatile memory)."
                    }
                    error_msg: str = error_map.get(result_code, "Unknown error.")
                    print(f"❌ Failed to configure reader power. Result code: 0x{result_code:02X} ({error_msg})")
                    return False
            else:
                print(f"❌ Unexpected response MID (0x{mid_response:02X}) or insufficient data for power configuration. Expected 0x{(MID.CONFIGURE_READER_POWER & 0xFF):02X}.")
                return False

        except ValueError as ve:
            print(f"❌ Data validation/parsing error during power configuration: {ve}")
            return False
        except Exception as e:
            print(f"❌ An unexpected exception occurred during power configuration: {e}")
            return False

    # --- Inventory Control Methods ---

    def is_inventory_running(self) -> bool:
        """
        Checks if the internal inventory flag is set, indicating an inventory operation is intended to be active.
        Note: This reflects the application's intent, not necessarily the reader's actual state.
        """
        return self._inventory_running

    def start_inventory_with_mode(self, antenna_mask: List[int], callback: Optional[Callable[[Dict], None]] = None) -> bool:
        """
        Initiates an RFID tag inventory operation with a specified antenna mask and an optional callback.
        It first attempts to stop any existing inventory to ensure a clean start.

        Args:
            antenna_mask (list[int]): A list of 1-based antenna IDs to activate for inventory.
            callback (Optional[Callable[[Dict], None]]): A callable function to be invoked for each detected tag.

        Returns:
            bool: True if the inventory command was sent successfully and the background thread started, False otherwise.
        """
        try:
            # Ensure any previous inventory operation is stopped
            if not self.stop_inventory():
                print("❌ Failed to stop previous inventory. Aborting new start.")
                return False
            
            # Set internal flag and callback
            self._inventory_running = True
            self._on_tag = callback # Callback for tag detections
            self._on_inventory_end = None # Reset end callback, if used separately

            # Convert list of antenna IDs to a 32-bit bitmask
            actual_antenna_mask: int = self.build_antenna_mask(antenna_mask)
            print(f"🚀 Starting inventory with antenna mask: 0x{actual_antenna_mask:08X}")
            
            # Build the payload for the READ_EPC_TAG command (MID 0x0210)
            # `continuous=True` indicates ongoing inventory until stopped
            payload: bytes = self.build_epc_read_payload(actual_antenna_mask, continuous=True)
            frame: bytes = self.build_frame(mid=MID.READ_EPC_TAG, payload=payload, rs485=self.rs485, notify=False)
            
            self.send(frame) # Send the inventory start command

            # Start a background thread to continuously receive and parse inventory data
            self._inventory_thread = threading.Thread(target=self._receive_inventory_loop_optimized, daemon=True)
            self._inventory_thread.start()
            
            print("✅ Inventory command sent and reception thread started.")
            return True
        except ValueError as ve:
            print(f"❌ Input validation error in start_inventory_with_mode: {ve}")
            return False
        except Exception as e:
            print(f"❌ An unexpected exception occurred in start_inventory_with_mode: {e}")
            return False

    def _receive_inventory_loop_optimized(self) -> None:
        """
        Optimized background loop for receiving and processing inventory data from the reader.
        It uses a buffer to handle fragmented or concatenated serial data, extracts valid frames,
        and invokes the `_on_tag` callback for each detected EPC tag.
        """
        buffer: bytes = b"" # Buffer to accumulate incoming serial data
        
        while self._inventory_running: # Loop as long as inventory is expected to run
            try:
                # Read a chunk of raw bytes from the serial port
                raw_data: bytes = self.receive(128) # Read more bytes per call for efficiency
                
                if not raw_data:
                    # If no data is received (e.g., timeout), wait briefly and continue
                    time.sleep(0.01) 
                    continue
                
                buffer += raw_data # Append new data to the buffer
                
                # Attempt to extract all valid frames from the current buffer
                frames: List[bytes] = self.extract_valid_frames(buffer)
                
                if frames:
                    # If valid frames were extracted, remove their bytes from the buffer
                    # by finding the position right after the last extracted frame.
                    last_frame: bytes = frames[-1]
                    # This `find` might be inefficient for very large buffers or many small frames.
                    # A more robust approach might be to track the total bytes consumed by frames.
                    # For simplicity, keeping original logic.
                    idx_of_last_frame_end: int = buffer.find(last_frame) + len(last_frame)
                    buffer = buffer[idx_of_last_frame_end:]

                for frame in frames:
                    try:
                        parsed_frame: Dict[str, Any] = self.parse_frame(frame)
                        category: int = parsed_frame.get("category", -1)
                        mid: int = parsed_frame.get("mid", -1)
                        data_payload: bytes = parsed_frame.get("data", b"")

                        if category == 0x10 or mid == 0x00: # Specific pattern for EPC tag data (Category 0x10, MID 0x00 for response)
                            tag: Dict[str, Any] = self.parse_epc(data_payload)
                            if "error" in tag:
                                # print(f"⚠️ EPC parse error: {tag['error']}") # Often too noisy for continuous logging
                                continue # Skip this tag if parsing failed
                            else:
                                if self._on_tag:
                                    self._on_tag(tag) # Invoke the registered callback for the detected tag
                        
                        elif mid in NationReader.all_read_end_mids(): # Check for any 'read end' notification MIDs
                            reason: Optional[int] = data_payload[0] if data_payload else None
                            print(f"✅ Inventory ended. Reason code: {reason}.")
                            if self._on_inventory_end:
                                self._on_inventory_end(reason) # Invoke end callback if registered
                            self._inventory_running = False # Signal loop to terminate
                            return # Exit the loop and thread function
                    except ValueError as ve:
                        # print(f"⚠️ Frame parsing error in _receive_inventory_loop_optimized: {ve}. Skipping frame.")
                        continue # Continue to next frame if current one caused parsing error
                    except Exception as ex:
                        # print(f"⚠️ An unexpected error occurred processing frame in inventory loop: {ex}. Skipping frame.")
                        continue # Catch other unexpected errors but keep loop running
            
            except serial.SerialException as se:
                print(f"❌ Serial communication error in inventory loop: {se}. Attempting to recover or stop.")
                self._inventory_running = False # Stop loop on persistent serial error
            except Exception as e:
                print(f"⚠️ An general error occurred in inventory loop: {e}. Waiting briefly.")
                time.sleep(0.01) # Small pause on general error to prevent busy-waiting

    # This method seems to be an older/alternative inventory loop, not used by start_inventory_with_mode.
    # Included for refactoring as per instructions.
    def _receive_inventory_loop(self) -> None:
        """
        A simpler background loop for receiving and parsing inventory data.
        It processes one frame at a time, assuming full frames are always received.
        (Less robust than _receive_inventory_loop_optimized for fragmented data).
        """
        while self._inventory_running:
            try:
                raw_data: bytes = self.receive(128)
                if not raw_data:
                    time.sleep(0.01) # Wait briefly if no data
                    continue

                try:
                    parsed_frame: Dict[str, Any] = self.parse_frame(raw_data)
                except ValueError as ve:
                    # print(f"⚠️ Frame parsing error in _receive_inventory_loop: {ve}. Skipping raw data.")
                    continue # Skip current raw data if it can't be parsed as a whole frame

                mid: int = parsed_frame.get("mid", -1)
                data_payload: bytes = parsed_frame.get("data", b"")

                if mid == 0x00: # Standard EPC tag data MID
                    tag: Dict[str, Any] = self.parse_epc(data_payload)
                    if "error" in tag:
                        print(f"⚠️ EPC parse error: {tag['error']}")
                    else:
                        if self._on_tag:
                            self._on_tag(tag) # Invoke tag callback
                
                elif mid in NationReader.all_read_end_mids(): # Check for 'read end' notification MIDs
                    reason: Optional[int] = data_payload[0] if data_payload else None
                    print(f"✅ Inventory ended. Reason: {reason}.")
                    if self._on_inventory_end:
                        self._on_inventory_end(reason) # Invoke end callback
                    self._inventory_running = False # Signal loop to terminate
                    break # Exit the loop

            except serial.SerialException as se:
                print(f"❌ Serial communication error in simple inventory loop: {se}.")
                self._inventory_running = False # Stop loop on serial error
            except Exception as e:
                # print(f"⚠️ General error in simple inventory loop: {e}")
                time.sleep(0.01) # Small pause on error

    def stop_inventory(self) -> bool:
        """
        Sends the STOP command (MID=0xFF) to the RFID reader to halt any ongoing
        RFID operations (like inventory) and attempts to confirm the reader enters an idle state.
        It also signals and waits for any associated inventory thread to stop.

        Returns:
            bool: True if the reader acknowledges the stop command and enters idle state,
                  or issues a valid 'read end' notification as a result of the stop. False otherwise.
        """
        # Step 1: Signal any running internal inventory thread to stop and wait for it to join.
        self._inventory_running = False # Set the flag to terminate the internal receive loop
        if hasattr(self, '_inventory_thread') and self._inventory_thread and self._inventory_thread.is_alive():
            print("🧵 Signaling inventory thread to stop and waiting for join (timeout 1s).")
            self._inventory_thread.join(timeout=1) # Wait for the thread to finish
            if self._inventory_thread.is_alive():
                print("⚠️ Inventory thread did not stop gracefully within timeout.")
            else:
                print("🧵 Inventory thread successfully stopped.")
        else:
            print("ℹ️ No active inventory thread found to stop.")

        # Step 2: Clear any unread data from the UART input buffer.
        try:
            self.uart.flush_input()
            print("Buffer input flushed.")
        except Exception as e:
            print(f"⚠️ UART input buffer flush failed: {e}")

        # Step 3: Send the explicit STOP command frame to the reader.
        stop_frame: bytes = self.build_frame(mid=MID.STOP_INVENTORY, payload=b'', rs485=self.rs485, notify=False)
        print(f"📤 Sending STOP command frame: {stop_frame.hex().upper()}")
        try:
            self.send(stop_frame)
        except Exception as e:
            print(f"❌ Failed to send STOP command to reader: {e}")
            return False

        # Step 4: Wait for confirmation from the reader (response or notification).
        # We try multiple times as responses can sometimes be delayed or fragmented.
        for attempt in range(10): # Max 10 attempts to get a valid stop confirmation
            time.sleep(0.2) # Wait briefly between receive attempts
            try:
                raw_response: bytes = self.receive(256) # Read potential response bytes
                if not raw_response:
                    # print(f"ℹ️ No raw response on attempt {attempt+1} for STOP confirmation.") # Often too noisy
                    continue # Continue to next attempt if no data received

                frames: List[bytes] = self.extract_valid_frames(raw_response)
                
                for idx, received_frame in enumerate(frames):
                    try:
                        parsed_response: Dict[str, Any] = self.parse_frame(received_frame)
                        response_mid: int = parsed_response.get("mid", -1)
                        response_data: bytes = parsed_response.get("data", b"")

                        # Check for a direct STOP_OPERATION (0xFF) response
                        if response_mid == MID.STOP_OPERATION: 
                            result_code: int = response_data[0] if response_data else -1
                            if result_code == 0x00: # 0x00 typically indicates success
                                print("✅ Reader responded: STOP successful, now IDLE.")
                                return True
                            else:
                                print(f"⚠️ Reader responded: STOP error code 0x{result_code:02x}.")
                                return False # STOP command failed with an error code

                        # Check for a 'read end' notification that occurred due to the STOP command
                        elif response_mid in NationReader.all_read_end_mids():
                            reason_code: int = response_data[0] if response_data else -1
                            if reason_code == 1: # Reason code 1 often means "stopped by command"
                                print("✅ Read end notification received: Inventory stopped by STOP command.")
                                return True
                            else:
                                print(f"↪️ Read ended with reason code {reason_code} (not direct STOP confirmation).")
                                # This is still a form of stop, so we might consider it successful here
                                return True 
                        else:
                            # print(f"🔍 Unrelated frame received (MID=0x{response_mid:04x}) on attempt {attempt+1}.") # Often too noisy
                            pass # Ignore other frames and continue searching for a STOP confirmation

                    except ValueError as ve:
                        # print(f"⚠️ Frame parse error for received frame [{idx}] during STOP confirmation: {ve}. Skipping frame.")
                        continue # Skip this frame if parsing fails
                    except Exception as ex:
                        # print(f"⚠️ An unexpected error occurred processing received frame during STOP confirmation: {ex}. Skipping.")
                        continue

            except serial.SerialException as se:
                print(f"❌ Serial communication error during STOP confirmation (attempt {attempt+1}): {se}. Retrying.")
                # Don't return False immediately, allow retries for transient errors
            except Exception as e:
                print(f"❌ An unexpected exception occurred during STOP confirmation (attempt {attempt+1}): {e}. Retrying.")
                
        print("❌ STOP failed: No valid response or reading end notification received after multiple attempts.")
        return False

    @staticmethod
    def all_read_end_mids() -> List[int]:
        """
        Returns a list of all Message IDs (MIDs) that signify the end of a read operation or inventory cycle.
        These are typically notification MIDs sent by the reader when an inventory ends (e.g., due to stop command, timeout).
        """
        # The MIDs are typically the low bytes of composite MIDs like 0x0201, 0x0221, 0x0231 etc.
        # Original has [0x01, 0x21, 0x31]
        return [0x01, 0x21, 0x31]

    # --- EPC Write Operations ---

    def write_epc_tag(
        self,
        epc_hex: str,
        antenna_id: int = 1,
        match_epc_hex: Optional[str] = None,
        access_password: Optional[int] = None,
        start_word: int = 2,
        timeout: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Writes a specified EPC (Electronic Product Code) value to an RFID tag.

        Args:
            epc_hex (str): The new EPC value as a hexadecimal string (e.g., 'ABCD9999').
            antenna_id (int): The 1-based antenna port to use for the write operation (default: 1).
            match_epc_hex (Optional[str]): An optional EPC hexadecimal string. If provided,
                                           the write operation will only proceed if the tag's current EPC matches this value.
            access_password (Optional[int]): An optional 32-bit integer access password for the tag.
            start_word (int): The starting word address in the EPC memory bank where the data will be written (default: 2, after PC word).
            timeout (float): The maximum time (in seconds) to wait for a response from the reader after sending the write command.

        Returns:
            dict: A dictionary containing the result of the write operation,
                  including 'success' (bool), 'result_code' (int), 'result_msg' (str),
                  and optionally 'failed_addr' (int) if the write fails at a specific address.
        """
        result: Dict[str, Any] = {
            "success": False,
            "result_code": -1,
            "result_msg": "Unknown error or timeout",
            "failed_addr": None,
        }
        try:
            # 1. Ensure the reader is in an idle state before attempting to write.
            if not self.stop_inventory():
                result["result_msg"] = "Failed to stop previous inventory before write. Reader not idle."
                print(f"❌ {result['result_msg']}")
                return result
            self.uart.flush_input() # Clear any lingering data in the input buffer
            time.sleep(0.2) # Short delay for stability

            # 2. Build the payload for the write EPC command.
            payload: bytearray = bytearray()
            
            # Antenna mask (4 bytes, big-endian): A bitmask indicating the target antenna.
            # Only one bit should be set for a single antenna.
            if not (1 <= antenna_id <= 32): # Assuming max 32 antennas for antenna mask
                raise ValueError(f"Invalid antenna_id: {antenna_id}. Must be between 1 and 32.")
            antenna_mask: int = 1 << (antenna_id - 1)
            payload.extend(antenna_mask.to_bytes(4, "big"))

            # Data area (1 byte): 0x01 typically represents the EPC memory bank.
            payload.extend(b"\x01") 

            # Word starting address (2 bytes, U16, big-endian): Where to begin writing in the memory bank.
            payload.extend(start_word.to_bytes(2, "big"))

            # EPC Data content: Length (2 bytes, U16) + EPC bytes.
            epc_bytes: bytes = bytes.fromhex(epc_hex)
            payload.extend(len(epc_bytes).to_bytes(2, "big"))
            payload.extend(epc_bytes)

            # Optional: Match parameter (PID 0x01)
            # If a match_epc_hex is provided, the write only occurs if the tag's current EPC matches.
            if match_epc_hex:
                match_bytes: bytes = bytes.fromhex(match_epc_hex)
                match_area: int = 0x01 # EPC memory bank
                match_start: int = start_word # Match starts at the same word as write for EPC
                match_bitlen: int = len(match_bytes) * 8 # Length in bits
                
                # Construct the match content payload part: [area][start_addr][bit_len][data]
                match_content: bytes = (
                    bytes([match_area]) +
                    match_start.to_bytes(2, "big") +
                    bytes([match_bitlen]) +
                    match_bytes
                )
                payload.extend(b"\x01") # PID for Match parameter
                payload.extend(len(match_content).to_bytes(2, "big")) # Length of match content
                payload.extend(match_content)

            # Optional: Access password (PID 0x02)
            # If an access password is provided, it's used to authenticate the write operation.
            if access_password is not None:
                if not (0 <= access_password <= 0xFFFFFFFF):
                    raise ValueError("Access password must be a 32-bit unsigned integer.")
                payload.extend(b"\x02\x00\x04") # PID for Password (0x02), Length (0x0004 for 4 bytes)
                payload.extend(access_password.to_bytes(4, "big")) # 4-byte password

            # 3. Build the complete frame for the write EPC command (MID 0x0211).
            frame: bytes = self.build_frame(mid=0x0211, payload=bytes(payload), rs485=self.rs485, notify=False)
            print(f"📤 Sending write frame: {frame.hex().upper()}")

            # 4. Send the write command frame to the reader.
            self.send(frame)

            # 5. Wait for the response from the reader within the specified timeout.
            deadline: float = time.time() + timeout
            receive_buffer: bytes = b"" # Buffer for incoming responses
            while time.time() < deadline:
                raw_received: bytes = self.receive(256) # Read a chunk of data
                if not raw_received:
                    continue # No data received, continue waiting
                
                receive_buffer += raw_received
                frames_received: List[bytes] = self.extract_valid_frames(receive_buffer)
                
                if frames_received:
                    # Remove processed frames from buffer (advanced for multi-frame handling)
                    last_frame_processed = frames_received[-1]
                    buffer_index = receive_buffer.find(last_frame_processed) + len(last_frame_processed)
                    receive_buffer = receive_buffer[buffer_index:]

                for received_frame in frames_received:
                    try:
                        resp: Dict[str, Any] = self.parse_frame(received_frame)
                        print(f"📥 [WRITE-EPC-TAG] Received frame: MID=0x{resp.get('mid', -1):02X}, Data={resp.get('data', b'').hex().upper()}")

                        response_mid: int = resp.get("mid", -1)
                        response_data: bytes = resp.get("data", b"")

                        # Success/Status Response (MID 0x11, which is the low byte of 0x0211)
                        if response_mid == (MID.WRITE_EPC_TAG_COMMAND & 0xFF):
                            if not response_data:
                                result["result_msg"] = "Empty response data for write command."
                                print(f"❌ {result['result_msg']}")
                                return result

                            # The first byte of data_payload is the result code
                            write_result_code: int = response_data[0]
                            result["result_code"] = write_result_code

                            # Map result codes to human-readable messages
                            result_map: Dict[int, str] = {
                                0x00: "Write successful",
                                0x01: "Antenna parameter error",
                                0x02: "Match parameter error",
                                0x03: "Write parameter error",
                                0x04: "CRC check error",
                                0x05: "Insufficient power (tag not powered sufficiently for write)",
                                0x06: "Data area overflow (tried to write beyond memory capacity)",
                                0x07: "Data area locked",
                                0x08: "Password error",
                                0x09: "Other tag error (general tag-related error)",
                                0x0A: "Tag lost (tag moved out of field during operation)",
                                0x0B: "Reader send error (internal reader issue sending command to tag)",
                            }
                            result["result_msg"] = result_map.get(write_result_code, f"Unknown write error code 0x{write_result_code:02X}")

                            if write_result_code == 0x00:
                                result["success"] = True
                            
                            # Optional: Failed word address (PID 0x01, U16)
                            # This specific structure (data[1]==0x01 and data[2]==0x02) suggests a TLV
                            # structure for optional error details, specifically the address.
                            if len(response_data) >= 5 and response_data[1] == 0x01 and response_data[2] == 0x02:
                                result["failed_addr"] = int.from_bytes(response_data[3:5], "big")
                            
                            print(f"✅ Write EPC result: {result['result_msg']}")
                            return result

                        # Generic Error/Illegal Instruction Response (MID 0x00)
                        elif response_mid == MID.ERROR_NOTIFICATION: 
                            error_code: int = response_data[0] if response_data else -1
                            error_map_generic: Dict[int, str] = {
                                0x01: "Unsupported instruction",
                                0x02: "CRC or mode error",
                                0x03: "Parameter error",
                                0x04: "Busy (reader is performing another operation)",
                                0x05: "Invalid state (reader not in correct state for this command)",
                            }
                            result["result_code"] = error_code
                            result["result_msg"] = f"Reader error: {error_map_generic.get(error_code, f'Unknown error code 0x{error_code:02X}')}"
                            print(f"❌ {result['result_msg']}")
                            return result
                    finally:
                        # Ensure we handle any exceptions during frame parsing or processing
                        pass
            
            # If the loop finishes without a valid response (timeout)
            result["result_code"] = -2
            result["result_msg"] = "Timeout waiting for write response from reader."
            print(f"❌ {result['result_msg']}")
            return result

        except ValueError as ve:
            result["result_code"] = -3
            result["result_msg"] = f"Validation or parsing error: {ve}"
            print(f"❌ {result['result_msg']}")
            return result
        except Exception as e:
            result["result_code"] = -99
            result["result_msg"] = f"An unexpected exception occurred during write_epc_tag: {e}"
            print(f"❌ {result['result_msg']}")
            return result


    def write_epc_tag_auto(
        self,
        new_epc_hex: str,
        match_epc_hex: Optional[str] = None,
        antenna_id: int = 1,
        access_password: Optional[int] = None,
        timeout: float = 0, # Note: original code uses 0, usually a positive float is expected.
                            # If 0 means "no timeout", it would wait indefinitely or rely on serial port timeout.
    ) -> Dict[str, Any]:
        """
        Writes a new EPC (Electronic Product Code) to a tag,
        automatically calculating the PC (Protocol Control) bits and determining the start word.
        This simplifies writing by handling EPC length formatting.

        Args:
            new_epc_hex (str): The new EPC value as a hexadecimal string (e.g., '4321').
            match_epc_hex (Optional[str]): An optional EPC hex string to match. The write only
                                           occurs if the tag's current EPC matches this.
            antenna_id (int): The 1-based antenna number to use (default: 1).
            access_password (Optional[int]): An optional 32-bit access password for the tag.
            timeout (float): The maximum time (in seconds) to wait for a write response.

        Returns:
            dict: A dictionary containing the result of the write operation (success, message, code).
        """
        initial_timeout: float = timeout if timeout > 0 else 5.0 # Ensure a minimum timeout if 0 is passed for practical purposes

        result: Dict[str, Any] = {
            "success": False,
            "result_code": -1,
            "result_msg": "Initial state",
            "failed_addr": None,
        }
        try:
            # 1. Prepare reader by stopping any active inventory and flushing buffers.
            if not self.stop_inventory():
                result["result_msg"] = "Failed to stop previous inventory before auto write."
                print(f"❌ {result['result_msg']}")
                return result
            self.uart.flush_input()
            time.sleep(0.2)

            # Step 1 (revisited): Format the new EPC content for writing.
            # This involves calculating the PC word based on EPC length and padding.
            epc_hex_formatted: str = new_epc_hex.strip().upper()
            # Calculate word length: each word is 2 bytes or 4 hex characters.
            # `(len(epc_hex_formatted) + 3) // 4` ensures correct word count, rounding up.
            word_len: int = (len(epc_hex_formatted) + 3) // 4 
            # PC word bits: bits 11-15 typically represent the EPC word length.
            pc_bits: int = word_len << 11 
            pc_hex: str = f"{pc_bits:04X}" # Format PC bits as 4 hex characters
            
            # Combine PC hex with EPC hex, padding the EPC with '0's to align to word length.
            # Ensures the final hex string has a length divisible by 4 (for byte pairs).
            full_epc_hex: str = pc_hex + epc_hex_formatted.ljust(word_len * 4, '0')
            epc_bytes_to_write: bytes = bytes.fromhex(full_epc_hex)

            # Step 2: Build the payload for the write operation.
            payload: bytearray = bytearray()
            
            # Antenna mask: Bitmask for the target antenna.
            if not (1 <= antenna_id <= 32): # Assuming max 32 antennas
                raise ValueError(f"Invalid antenna_id for write: {antenna_id}. Must be between 1 and 32.")
            antenna_mask_int: int = 1 << (antenna_id - 1)
            payload.extend(antenna_mask_int.to_bytes(4, "big")) 

            payload.extend(b"\x01") # EPC memory bank (0x01)
            payload.extend((1).to_bytes(2, "big")) # Start word = 1 (to include PC word + EPC data)
            payload.extend(len(epc_bytes_to_write).to_bytes(2, "big")) # Length of PC + EPC bytes
            payload.extend(epc_bytes_to_write) # The actual PC + EPC data

            # Step 3: Add optional match EPC filter if provided.
            if match_epc_hex:
                match_hex_formatted: str = match_epc_hex.strip().upper()
                match_bytes: bytes = bytes.fromhex(match_hex_formatted)
                bit_len: int = len(match_bytes) * 8 # Length in bits for match
                
                # Match content format: [Area][Start_Address][Bit_Length][Data]
                match_content: bytes = (
                    b"\x01" + # Match in EPC area (0x01)
                    (1).to_bytes(2, "big") + # Match starts at word 1 (PC + EPC)
                    bytes([bit_len]) +
                    match_bytes
                )
                payload.extend(b"\x01") # PID for Match parameter
                payload.extend(len(match_content).to_bytes(2, "big")) # Length of match content
                payload.extend(match_content)

            # Step 4: Add optional access password if provided.
            if access_password is not None:
                if not (0 <= access_password <= 0xFFFFFFFF):
                    raise ValueError("Access password must be a 32-bit unsigned integer.")
                payload.extend(b"\x02\x00\x04") # PID (0x02), Length (0x0004 for 4 bytes)
                payload.extend(access_password.to_bytes(4, "big"))

            # Step 5: Build and send the complete write command frame.
            frame: bytes = self.build_frame(mid=0x0211, payload=bytes(payload), rs485=self.rs485, notify=False)
            print(f"📤 Write EPC frame: {frame.hex().upper()}")
            self.send(frame)

            # Step 6: Await and parse the response from the reader.
            deadline: float = time.time() + initial_timeout
            response_buffer: bytes = b""
            while time.time() < deadline:
                raw_response_chunk: bytes = self.receive(256)
                if not raw_response_chunk:
                    continue
                
                response_buffer += raw_response_chunk
                frames_in_buffer: List[bytes] = self.extract_valid_frames(response_buffer)
                
                if frames_in_buffer:
                    # Clear processed frames from buffer
                    last_frame_extracted = frames_in_buffer[-1]
                    buffer_idx = response_buffer.find(last_frame_extracted) + len(last_frame_extracted)
                    response_buffer = response_buffer[buffer_idx:]

                for frame_in_buffer in frames_in_buffer:
                    try:
                        resp: Dict[str, Any] = self.parse_frame(frame_in_buffer)
                        print(f"📥 Write-EPC response: MID=0x{resp.get('mid', -1):02X}, Data={resp.get('data', b'').hex().upper()}")
                        
                        response_mid: int = resp.get("mid", -1)
                        response_data: bytes = resp.get("data", b"")

                        # Handle successful write response (MID 0x11)
                        if response_mid == (MID.WRITE_EPC_TAG_COMMAND & 0xFF):
                            if not response_data:
                                result["result_msg"] = "Empty response data from reader after write."
                                print(f"❌ {result['result_msg']}")
                                return result

                            write_result_code: int = response_data[0]
                            result["result_code"] = write_result_code
                            
                            # Map result codes
                            result_map: Dict[int, str] = {
                                0x00: "Write successful", 0x01: "Antenna error",
                                0x02: "Match error", 0x03: "Write parameter error",
                                0x04: "CRC error", 0x05: "Low power (tag)",
                                0x06: "Overflow", 0x07: "Locked (data area)",
                                0x08: "Password error", 0x09: "Tag error (other)",
                                0x0A: "Tag lost (during operation)", 0x0B: "Send error (reader internal)",
                            }
                            result["result_msg"] = result_map.get(write_result_code, f"Unknown error code 0x{write_result_code:02X}")
                            result["success"] = (write_result_code == 0x00)

                            # Extract optional failed word address
                            failed_addr: Optional[int] = None
                            if len(response_data) >= 5 and response_data[1] == 0x01: # PID 0x01
                                if len(response_data) >= 3 and response_data[2] == 0x02: # Length 0x02
                                    failed_addr = int.from_bytes(response_data[3:5], "big")
                            result["failed_addr"] = failed_addr
                            
                            print(f"✅ Auto Write EPC Result: {result['result_msg']}")
                            return result
                        
                        # Handle generic error response (MID 0x00)
                        elif response_mid == MID.ERROR_NOTIFICATION: 
                            error_code: int = response_data[0] if response_data else -1
                            result["success"] = False
                            result["result_code"] = error_code
                            result["result_msg"] = f"Reader error: 0x{error_code:02X}"
                            print(f"❌ Reader error: {result['result_msg']}")
                            return result

                    except ValueError as ve:
                        print(f"⚠️ Frame parse error during write_epc_tag_auto processing: {ve}. Skipping frame.")
                        continue # Continue to next frame
                    except Exception as ex:
                        print(f"⚠️ An unexpected error occurred processing frame in write_epc_tag_auto: {ex}. Skipping.")
                        continue
            
            # If timeout occurred without a valid response
            result["result_code"] = -2
            result["result_msg"] = "Timeout waiting for write response."
            print(f"❌ {result['result_msg']}")
            return result

        except ValueError as ve:
            result["result_code"] = -3
            result["result_msg"] = f"Validation or parsing error in write_epc_tag_auto: {ve}"
            print(f"❌ {result['result_msg']}")
            return result
        except Exception as e:
            result["result_code"] = -99
            result["result_msg"] = f"An unexpected exception occurred in write_epc_tag_auto: {e}"
            print(f"❌ {result['result_msg']}")
            return result

    def check_write_epc(self, epcHex: str) -> bool:
        """
        Checks if the reader can successfully write/detect a specific EPC tag.
        This function performs a temporary inventory to verify tag presence and readability,
        which implicitly tests the reader's basic RFID operation capabilities required for writing.

        Args:
            epcHex (str): The EPC hex string to check for.

        Returns:
            bool: True if the specified EPC tag is found during the check, False otherwise.
        """
        # Ensure reader is idle before starting a new check inventory
        if not self.stop_inventory():
            print("❌ Failed to stop inventory before check_write_epc.")
            return False
        self.uart.flush_input() # Clear buffers

        found_target_epc: bool = False # Flag to indicate if the target EPC was found

        def on_tag_callback(tag: Dict[str, Any]) -> None:
            """
            Internal callback for `start_inventory_with_mode` during the check operation.
            It sets `found_target_epc` if the desired EPC is seen.
            """
            nonlocal found_target_epc # Allows modification of `found_target_epc` in outer scope
            
            epc: str = tag.get("epc", "").upper()
            if epc == epcHex.upper():
                print(f"✅ Tag with EPC {epc} found during write check.")
                found_target_epc = True # Set flag to True
            else:
                print(f"👀 Tag with EPC {epc} found, but it's not the one we are checking for.")
        
        try:
            # Start a temporary inventory using antenna 1 and the custom callback
            # This inventory runs continuously until explicitly stopped or `found_target_epc` is True.
            # A timeout for this check needs to be managed externally or by the inventory loop.
            if not self.start_inventory_with_mode(antenna_mask=[1], callback=on_tag_callback):
                print("❌ Failed to start inventory for check_write_epc.")
                return False
            
            # Wait for a short period to allow tags to be read
            # In a real scenario, you might have a more sophisticated event-driven wait
            # or a longer scan time depending on environment.
            start_time: float = time.time()
            check_duration: float = 3.0 # Check for 3 seconds
            while time.time() - start_time < check_duration and not found_target_epc:
                time.sleep(0.1) # Briefly sleep to yield control

            # Stop the inventory after the check duration or if tag is found
            if not self.stop_inventory():
                print("❌ Failed to stop inventory after check_write_epc.")

            return found_target_epc # Return the result of the check
        except Exception as e:
            print(f"❌ Exception during check_write_epc: {e}")
            return False

    def write_epc_to_target_auto(
        self,
        target_tag_epc: str,
        new_epc_hex: str,
        access_pwd: Optional[int] = None,
        timeout: float = 2.0,
        scan_timeout: float = 2.0,
        verify: bool = True,
        overwrite_pc: bool = True,
        prefix_words: int = 0,
    ) -> Dict[str, Any]:
        """
        Scans for a tag with a specific `target_tag_epc`, then attempts to write
        a `new_epc_hex` value to it, automatically handling PC bits and word length.
        Includes optional verification after writing.

        Args:
            target_tag_epc (str): The current EPC of the tag to target (used for matching).
            new_epc_hex (str): The new EPC value to write (hex string).
            access_pwd (Optional[int]): Optional 32-bit access password for the tag.
            timeout (float): Timeout in seconds for the write operation itself.
            scan_timeout (float): Maximum time in seconds to scan for the target tag before writing.
            verify (bool): If True, attempts to re-read the tag with the new EPC after writing.
            overwrite_pc (bool): If True, the write operation will overwrite the PC word (starts at word 1).
                                 If False, write starts after PC word (typically word 2).
            prefix_words (int): Number of words to skip before the actual EPC data in memory.

        Returns:
            dict: A dictionary containing the result of the overall operation (scan, write, verify).
        """
        result: Dict[str, Any] = {
            "success": False,
            "result_code": -1,
            "result_msg": "Operation failed",
            "failed_addr": None,
        }
        
        print(f"🔍 Scanning for target tag with EPC '{target_tag_epc.upper()}' (up to {scan_timeout}s)...")
        found_event: threading.Event = threading.Event() # Event to signal when target tag is found

        def tag_callback_for_scan(tag: Dict[str, Any]) -> None:
            """Internal callback during the initial scan to find the target tag."""
            epc: str = tag.get("epc", "").upper()
            # print(f"👀 Tag seen during scan: {epc}") # Verbose logging for every tag seen during scan
            if epc == target_tag_epc.upper():
                print(f"  ✅ Found target tag: EPC={epc} (RSSI={tag.get('rssi')}, Antenna={tag.get('antenna_id')})")
                found_event.set() # Signal that the target tag has been found

        # Step 1: Start inventory to find the target tag.
        # This uses the `start_inventory_with_mode` with a temporary callback.
        # The `mode=0` in the original Python might refer to an internal mode not directly mapped.
        # For `start_inventory_with_mode`, it takes `antenna_mask` (list of ints) and `callback`.
        # Assuming `antenna_mask=[1]` for default scanning.
        if not self.start_inventory_with_mode(antenna_mask=[1], callback=tag_callback_for_scan):
            result["result_msg"] = "Failed to start scan for target tag."
            print(f"❌ {result['result_msg']}")
            return result

        try:
            # Wait for the target tag to be found or for the scan timeout to expire.
            if not found_event.wait(timeout=scan_timeout):
                result["result_msg"] = (f"❌ Target tag '{target_tag_epc.upper()}' not found within {scan_timeout}s. "
                                        "Please place the tag closer to the antenna and try again.")
                print(result["result_msg"])
                return result

            # Stop the initial scan inventory after the target tag is found.
            if not self.stop_inventory():
                print("⚠️ Failed to stop scan inventory, but found target. Proceeding with write.")

            # Step 2: Validate EPCs and calculate the starting word for the write operation.
            try:
                # `validate_epc_hex` ensures correct hex format and word alignment.
                self.validate_epc_hex(new_epc_hex)
                self.validate_epc_hex(target_tag_epc)
            except ValueError as ve:
                result["result_msg"] = f"❌ EPC validation error: {ve}"
                print(result["result_msg"])
                return result

            # Calculate the start word (where in the EPC memory bank the write begins).
            start_word: int = self.calculate_start_word(
                new_epc_hex,
                overwrite_pc=overwrite_pc,
                prefix_words=prefix_words
            )

            # --- Auto-calculate PC bits and full EPC hex for writing ---
            # This logic is copied directly from `write_epc_tag_auto` (single write)
            epc_hex_normalized: str = new_epc_hex.strip().upper()
            word_len: int = (len(epc_hex_normalized) + 3) // 4 
            pc_bits: int = word_len << 11
            pc_hex: str = f"{pc_bits:04X}"
            full_epc_hex_for_write: str = pc_hex + epc_hex_normalized.ljust(word_len * 4, '0')

            print(f"📝 Writing new EPC '{new_epc_hex.upper()}' (full hex including PC: {full_epc_hex_for_write}, start_word={start_word})…")
            
            # Step 3: Perform the actual write operation.
            write_result: Dict[str, Any] = self.write_epc_tag(
                epc_hex=full_epc_hex_for_write, # The full EPC including PC word
                antenna_id=1, # Assuming write on antenna 1 after scan
                match_epc_hex=target_tag_epc, # Match against the tag's current EPC
                access_password=access_pwd,
                start_word=start_word,
                timeout=timeout, # Timeout for the write response itself
            )
            print("Write EPC result:", write_result)

            # Update the overall result based on the write operation's success.
            result.update(write_result) 

            # Step 4: Optional post-write verification.
            if verify and result.get("success"):
                print("🔄 Verifying new EPC…")
                verified_event: threading.Event = threading.Event() # Event to signal new EPC verification

                def verify_callback(tag: Dict[str, Any]) -> None:
                    """Internal callback during verification scan."""
                    if tag.get("epc", "").upper() == new_epc_hex.upper():
                        verified_event.set() # Signal new EPC found

                # Start a temporary inventory to verify the new EPC
                if not self.start_inventory_with_mode(antenna_mask=[1], callback=verify_callback):
                    print("❌ Failed to start verification inventory.")
                    return result # Return previous result if verification can't start

                if verified_event.wait(timeout=1.5): # Wait briefly for verification
                    print("✅ Verification OK — tag now reports new EPC.")
                else:
                    print("⚠️ Write may have succeeded, but tag not seen with new EPC yet during verification.")
                
                # Stop the verification inventory
                if not self.stop_inventory():
                    print("⚠️ Failed to stop verification inventory.")
            elif not result.get("success"):
                print("⚠️ Write failed; no verification performed.")

        except Exception as e:
            result["result_msg"] = f"An unexpected exception occurred during write_epc_to_target_auto: {e}"
            result["result_code"] = -99
            print(f"❌ {result['result_msg']}")
        finally:
            # Ensure inventory is stopped regardless of outcome.
            # This is critical to prevent leaving the reader in an active state.
            if self.is_inventory_running(): # Check if it's still running from previous attempts
                self.stop_inventory()
            print("Cleanup: Ensuring reader is idle.")
        return result

    @staticmethod    
    def validate_epc_hex(epc_hex: str) -> bytes:
        """
        Validates and converts an EPC hexadecimal string to a byte sequence,
        ensuring it contains only valid hex characters, has an even number of digits,
        and is word-aligned (padded with 0x00 if necessary to make it an even number of bytes).

        Args:
            epc_hex (str): The EPC value as a hexadecimal string.

        Returns:
            bytes: A word-aligned bytes object suitable for protocol commands.

        Raises:
            ValueError: If the input string contains non-hex characters or has an odd number of digits.
        """
        epc_hex = epc_hex.strip().replace(" ", "") # Remove whitespace
        
        # Check if all characters are valid hexadecimal digits
        if not all(c in "0123456789abcdefABCDEF" for c in epc_hex):
            raise ValueError("EPC hex contains non-hex characters.")
        
        # Ensure an even number of hex digits (each byte requires 2 hex chars)
        if len(epc_hex) % 2 != 0:
            raise ValueError("EPC hex must contain an even number of characters (each byte is 2 hex chars).")

        data_bytes: bytes = bytes.fromhex(epc_hex)
        
        # Ensure byte sequence is word-aligned (multiple of 2 bytes)
        if len(data_bytes) % 2 != 0:
            data_bytes += b"\x00" # Pad with a null byte to make it 16-bit (2-byte) aligned

        return data_bytes
    
    @staticmethod
    def calculate_start_word(epc_hex: str, *, overwrite_pc: bool = False, prefix_words: int = 0) -> int:
        """
        Calculates the appropriate starting word address for writing EPC data to a tag.
        This depends on whether the PC (Protocol Control) word is being overwritten
        and any additional prefix words that need to be skipped.

        Args:
            epc_hex (str): The EPC value (as a hex string) that will be written.
            overwrite_pc (bool): If True, the write includes the PC word (starts at word 1).
                                 If False, write starts after the PC word (typically word 2, safe zone).
            prefix_words (int): Additional number of 16-bit words to skip before writing.
                                 Useful if there are locked or reserved words at the beginning of EPC memory.

        Returns:
            int: The calculated 16-bit word address to use in the write command.

        Raises:
            ValueError: If the `epc_hex` is invalid (checked by `validate_epc_hex`).
        """
        # Validate the EPC hex string; the actual value isn't used, but its validity is important.
        _ = NationReader.validate_epc_hex(epc_hex)
        
        # Base word address: 1 if overwriting PC, 2 if starting after PC.
        base_word: int = 1 if overwrite_pc else 2
        
        # Add any additional prefix words
        return base_word + prefix_words

    # --- Antenna Configuration Methods ---

    def query_enabled_ant_mask(self) -> int:
        """
        Queries the current 32-bit antenna mask from the reader.
        Each bit in the mask corresponds to an antenna, indicating if it's enabled.

        Returns:
            int: An integer representing the 32-bit mask of enabled antennas. Returns 0 on failure.
        """
        try:
            self.uart.flush_input() # Clear buffer before sending
            
            # The protocol uses MID 0x0202 for Query Reader Power, but its data includes antenna status.
            # Assuming the same MID queries the enabled mask as per original code.
            frame: bytes = self.build_frame(mid=0x0202, payload=b'', rs485=False, notify=False)
            print(f"📤 Sent query_enabled_ant_mask frame: {frame.hex().upper()}")
            self.uart.send(frame)
            
            time.sleep(0.1) # Short delay for response
            raw_response: bytes = self.uart.receive(64) # Receive potential response
            if not raw_response:
                print("❌ No response received for enabled antenna mask query.")
                return 0

            frames: List[bytes] = self.extract_valid_frames(raw_response)
            if not frames:
                print("❌ No valid frames extracted for enabled antenna mask query.")
                return 0

            for received_frame in frames:
                parsed_frame: Dict[str, Any] = self.parse_frame(received_frame)
                mid_response: int = parsed_frame.get("mid", -1)
                data_payload: bytes = parsed_frame.get("data", b"")

                # Expected response MID is 0x02 (low byte of 0x0202)
                if mid_response == 0x02:
                    if len(data_payload) < 2:
                        print("❌ Invalid data length in response for enabled antenna mask. Expected at least 2 bytes.")
                        continue # Skip this frame, continue checking others

                    # The antenna mask is usually the first 4 bytes of the data payload.
                    # Original Python code `data[:2]` suggests 2 bytes were expected, but `build_antenna_mask` creates 4.
                    # Assuming 4 bytes as the mask is 32-bit.
                    if len(data_payload) < 4:
                        print("⚠️ Received data for antenna mask is less than 4 bytes, interpreting as available.")
                        # Pad with zeros if less than 4 bytes to ensure it's 4 bytes for parsing
                        padded_data = data_payload + b'\x00' * (4 - len(data_payload))
                        mask: int = int.from_bytes(padded_data[:4], byteorder="big")
                    else:
                        mask = int.from_bytes(data_payload[:4], byteorder="big") # Read 4 bytes for 32-bit mask

                    print(f"📥 Queried enabled antenna mask: 0x{mask:08X}")
                    return mask
                else:
                    print(f"❌ Unexpected MID (0x{mid_response:02X}) in response for enabled antenna mask query.")
                    continue

            print("❌ No MID=0x02 frame found (or valid mask extracted) in responses.")
            return 0
        except Exception as e:
            print(f"❌ Exception in query_enabled_ant_mask: {e}")
            return 0

    def parse_reader_power_response(self, payload: bytes) -> List[Tuple[int, int]]:
        """
        Parses the data payload received from a 'Query Reader Power' command (MID=0x02).
        The payload is expected to be a list of (Antenna ID, Power dBm) pairs.

        Args:
            payload (bytes): The data payload from the reader's power response.

        Returns:
            List[Tuple[int, int]]: A list of (antenna_id, power_dbm) tuples.

        Raises:
            ValueError: If the payload length is not an even number (indicating incomplete pairs).
        """
        if len(payload) % 2 != 0:
            raise ValueError("Payload length is odd, invalid format for antenna power pairs (expected multiple of 2).")

        antenna_power_list: List[Tuple[int, int]] = []

        for i in range(0, len(payload), 2):
            antenna_id: int = payload[i]
            power_dbm: int = payload[i + 1]
            antenna_power_list.append((antenna_id, power_dbm))

        return antenna_power_list
    
    def enable_ant(self, ant_id: int, save: bool = True) -> bool:
        """
        Enables a single antenna port on the reader.
        Updates the global antenna mask and optionally saves the configuration to non-volatile memory.

        Args:
            ant_id (int): The 1-based ID of the antenna to enable (1-32).
            save (bool): If True, attempts to save the configuration (default: True).

        Returns:
            bool: True if the antenna was successfully enabled, False otherwise.
        """
        if not (1 <= ant_id <= 32): # Validate antenna ID range
            print(f"❌ Invalid antenna ID: {ant_id}. Must be between 1 and 32.")
            return False
        
        try:
            # Query the current enabled antenna mask
            current_mask: int = self.query_enabled_ant_mask()
            # Calculate the new mask by setting the bit corresponding to ant_id
            new_mask: int = current_mask | (1 << (ant_id - 1))
            
            # Build payload: 4 bytes for new_mask + optional 2 bytes for persistence flag
            payload: bytes = new_mask.to_bytes(4, 'big')
            if save: # If save is True, append the persistence PID and value
                payload += b'\xFF' # PID for Parameter persistence (save configuration)
                payload += (0x01).to_bytes(1, 'big') # Value 0x01 means save
            else: # If save is False, append the persistence PID and value 0x00 (temporary)
                payload += b'\xFF'
                payload += (0x00).to_bytes(1, 'big')

            # Build and send the command frame (MID 0x0203 for antenna configuration)
            frame: bytes = self.build_frame(mid=0x0203, payload=payload, notify=False)
            self.uart.flush_input()
            self.uart.send(frame)
            
            raw_response: bytes = self.uart.receive(64) # Receive response
            if not raw_response:
                print(f"❌ No response received after sending enable antenna {ant_id} command.")
                return False
            
            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_response.get("mid", -1)
            data_payload: bytes = parsed_response.get("data", b"")

            # Expected response MID is 0x03 (low byte of 0x0203) and success code 0x00
            if mid_response == 0x03 and len(data_payload) > 0 and data_payload[0] == 0x00:
                print(f"✅ Enabled antenna {ant_id} (new mask=0x{new_mask:08X}, save={save}).")
                return True
            else:
                print(f"❌ Failed to enable antenna {ant_id}. Response MID: 0x{mid_response:02X}, Data: {data_payload.hex().upper()}.")
                return False
        except Exception as e:
            print(f"❌ Exception in enable_ant for ID {ant_id}: {e}")
            return False

    def disable_ant(self, ant_id: int, save: bool = True) -> bool:
        """
        Disables a single antenna port on the reader.
        Updates the global antenna mask and optionally saves the configuration.

        Args:
            ant_id (int): The 1-based ID of the antenna to disable (1-32).
            save (bool): If True, attempts to save the configuration (default: True).

        Returns:
            bool: True if the antenna was successfully disabled, False otherwise.
        """
        if not (1 <= ant_id <= 32): # Validate antenna ID range
            print(f"❌ Invalid antenna ID: {ant_id}. Must be between 1 and 32.")
            return False
        
        try:
            # Query the current enabled antenna mask
            current_mask: int = self.query_enabled_ant_mask()
            # Calculate the new mask by clearing the bit corresponding to ant_id
            new_mask: int = current_mask & ~(1 << (ant_id - 1))
            
            # Build payload: 4 bytes for new_mask + optional 2 bytes for persistence flag
            payload: bytes = new_mask.to_bytes(4, 'big')
            if save: # If save is True, append the persistence PID and value
                payload += b'\xFF' 
                payload += (0x01).to_bytes(1, 'big') 
            else: # If save is False, append the persistence PID and value 0x00 (temporary)
                payload += b'\xFF'
                payload += (0x00).to_bytes(1, 'big')

            # Build and send the command frame (MID 0x0203 for antenna configuration)
            frame: bytes = self.build_frame(mid=0x0203, payload=payload, notify=False)
            self.uart.flush_input()
            self.uart.send(frame)
            
            raw_response: bytes = self.uart.receive(64) # Receive response
            if not raw_response:
                print(f"❌ No response received after sending disable antenna {ant_id} command.")
                return False
            
            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_response.get("mid", -1)
            data_payload: bytes = parsed_response.get("data", b"")

            # Expected response MID is 0x03 (low byte of 0x0203) and success code 0x00
            if mid_response == 0x03 and len(data_payload) > 0 and data_payload[0] == 0x00:
                print(f"✅ Disabled antenna {ant_id} (new mask=0x{new_mask:08X}, save={save}).")
                return True
            else:
                print(f"❌ Failed to disable antenna {ant_id}. Response MID: 0x{mid_response:02X}, Data: {data_payload.hex().upper()}.")
                return False
        except Exception as e:
            print(f"❌ Exception in disable_ant for ID {ant_id}: {e}")
            return False

    def build_antenna_mask(self, antenna_ids: List[int]) -> int:
        """
        Converts a list of 1-based antenna IDs into a single 32-bit antenna mask.

        Args:
            antenna_ids (list[int]): A list of 1-based antenna IDs (e.g., [1, 2, 4]).

        Returns:
            int: The calculated 32-bit integer mask.

        Raises:
            ValueError: If any antenna ID is outside the valid range (1-32).
        """
        mask: int = 0
        for ant_id in antenna_ids:
            if not (1 <= ant_id <= 32): # Assuming antennas 1-32 are controllable by this mask
                raise ValueError(f"Antenna ID {ant_id} is out of valid range (1-32).")
            mask |= (1 << (ant_id - 1)) # Set the corresponding bit
        return mask

    # --- Profile Management Methods ---

    def select_profile(self, profile_id: int) -> bool:
        """
        Selects a baseband profile by its ID on the RFID reader.
        Typically, profiles are numbered 0, 1, or 2.

        Args:
            profile_id (int): The ID of the profile to select (e.g., 0, 1, 2).

        Returns:
            bool: True if the profile was successfully selected, False otherwise.
        """
        if profile_id not in (0, 1, 2): # Validate profile ID range
            print(f"❌ Invalid profile ID: {profile_id}. Must be 0, 1, or 2.")
            return False

        try:
            self.uart.flush_input() # Clear input buffer
            payload: bytes = bytes([profile_id]) # Payload is simply the profile ID byte
            
            # Build and send the command frame (MID 0x020A for Select Baseband Profile)
            frame: bytes = self.build_frame(mid=0x020A, payload=payload, rs485=self.rs485, notify=False)
            self.uart.send(frame)

            time.sleep(0.1) # Short delay for response
            raw_response: bytes = self.uart.receive(64)
            if not raw_response:
                print("❌ No response received from reader for profile selection.")
                return False

            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_response.get("mid", -1)
            data_payload: bytes = parsed_response.get("data", b"")

            # Expected response MID is 0x0A (low byte of 0x020A)
            if mid_response == 0x0A:
                if len(data_payload) > 0 and data_payload[0] == profile_id:
                    print(f"✅ Profile {profile_id} selected successfully.")
                    return True
                else:
                    actual_id: Any = data_payload[0] if data_payload else 'N/A'
                    print(f"❌ Profile selection failed. Expected ID {profile_id}, but response indicated {actual_id}.")
                    return False
            else:
                print(f"❌ Unexpected MID (0x{mid_response:02X}) in response to profile selection. Expected 0x0A.")
                return False

        except Exception as e:
            print(f"❌ Exception during profile selection (profile ID {profile_id}): {e}")
            return False
            
    def get_profile(self) -> Dict[str, Any]:
        """
        Retrieves a comprehensive profile of the reader's current configuration,
        including enabled antennas, power levels, baseband settings, RF band,
        working frequencies, tag filtering, and general reader information.

        Returns:
            dict: A dictionary containing the full reader profile.
                  Returns a dictionary with an 'error' key on failure.
        """
        profile: Dict[str, Any] = {}

        try:
            # 1. Enabled Antennas
            enabled_mask: int = self.query_enabled_ant_mask()
            # Construct a list of 1-based antenna IDs from the mask
            # The range should ideally be up to MAX_ANTENNAS from a config, or 32/64 as per reader.
            # Using 65 as in original code, implying max 64 antennas.
            profile["enabled_antennas"] = [i for i in range(1, 65) if (enabled_mask >> (i - 1)) & 1]

            # 2. Antenna Powers
            powers: Dict[int, int] = self.query_reader_power()
            profile["antenna_powers"] = powers

            # 3. Baseband Parameters
            baseband_info: Dict[str, Any] = self.query_baseband_profile()
            profile["baseband"] = {
                "speed": baseband_info.get("speed"),
                "q_value": baseband_info.get("q_value"),
                "session": baseband_info.get("session"),
                "inventory_flag": baseband_info.get("inventory_flag")
            }
            
            # 4. Frequency Band
            freq_band_info: Optional[Dict[str, Any]] = self.query_rf_band()
            profile["rf_band"] = freq_band_info

            # 5. Working Frequency Channels
            working_freq_info: Dict[str, Any] = self.query_working_frequency()
            profile["working_frequency"] = working_freq_info

            # 6. Tag Filtering Settings
            filtering_info: Dict[str, Any] = self.query_filter_settings()
            profile["filtering"] = {
                "repeat_time_ms": filtering_info.get("repeat_time", 0) * 10, # Convert from 10ms units to ms
                "rssi_threshold": filtering_info.get("rssi_threshold")
            }

            # 7. Optional: General Reader Information (Serial, Firmware, etc.)
            reader_info: Dict[str, Any] = self.Query_Reader_Information()
            profile["reader_info"] = reader_info

            return profile

        except Exception as e:
            print(f"❌ Failed to get complete reader profile: {e}")
            return {"error": str(e)}

    # --- RF Band Control Methods ---

    def query_rf_band(self) -> Optional[Dict[str, Any]]:
        """
        Queries the RFID reader's currently configured RF frequency band.

        Returns:
            Optional[dict]: A dictionary containing 'band_code' (int) and 'band_name' (str),
                            or None if the query fails.
        """
        # Mapping of RF band codes to human-readable names as per protocol specification
        RF_BAND_CODES: Dict[int, str] = {
            0: "CN 920–925 MHz",
            1: "CN 840–845 MHz",
            2: "CN Dual-band 840–845 + 920–925 MHz",
            3: "FCC 902–928 MHz",
            4: "ETSI 866–868 MHz",
            5: "JP 916.8–920.4 MHz",
            6: "TW 922.25–927.75 MHz",
            7: "ID 923.125–925.125 MHz",
            8: "RUS 866.6–867.4 MHz"
        }
        CAT_RF_BAND: int = 0x02 # Category for RF Band commands
        MID_RF_BAND: int = 0x04 # MID for Query RF Band

        try:
            self.uart.flush_input() # Clear input buffer
            
            # Build and send the command frame
            frame: bytes = self.build_frame(mid=(CAT_RF_BAND << 8) | MID_RF_BAND, payload=b'', rs485=self.rs485, notify=False)
            print(f"📤 Sending query_rf_band frame: {frame.hex().upper()}")
            self.send(frame)
            
            raw_response: bytes = self.receive(64) # Receive response
            if not raw_response:
                print("❌ No response received for RF band query.")
                return None
            
            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_response.get("mid", -1)
            cat_response: int = parsed_response.get("category", -1)
            data_payload: bytes = parsed_response.get("data", b"")

            print(f"📥 Parsed RF Band response: CAT=0x{cat_response:02X}, MID=0x{mid_response:02X}, Data={data_payload.hex().upper()}")

            # Validate the response MID and Category
            if cat_response != CAT_RF_BAND or mid_response != MID_RF_BAND:
                raise ValueError(f"❌ Unexpected response for RF band query: CAT=0x{cat_response:02X}, MID=0x{mid_response:02X}. Expected CAT=0x{CAT_RF_BAND:02X}, MID=0x{MID_RF_BAND:02X}.")

            if len(data_payload) < 1:
                raise ValueError("⚠️ Invalid response length for RF band query. Expected at least 1 byte.")

            band_code: int = data_payload[0]
            band_name: str = RF_BAND_CODES.get(band_code, f"Unknown Band Code ({band_code})")
            
            print(f"📡 Current RF Band: {band_name} [Code={band_code}].")
            return {
                "band_code": band_code,
                "band_name": band_name
            }
        except Exception as e:
            print(f"❌ Error querying RF band: {e}")
            return None

    def set_rf_band(self, band_code: int, persist: bool = True) -> bool:
        """
        Sets the RF frequency band of the reader.

        Args:
            band_code (int): The numerical code for the RF band (0-8, as per protocol).
            persist (bool): If True, saves the setting to non-volatile memory (default: True).

        Returns:
            bool: True if the RF band was successfully set, False otherwise.
        """
        # Mapping of RF band codes for logging purposes
        RF_BAND_CODES: Dict[int, str] = {
            0: "CN 920–925 MHz", 1: "CN 840–845 MHz",
            2: "CN Dual-band 840–845 + 920–925 MHz", 3: "FCC 902–928 MHz",
            4: "ETSI 866–868 MHz", 5: "JP 916.8–920.4 MHz",
            6: "TW 922.25–927.75 MHz", 7: "ID 923.125–925.125 MHz",
            8: "RUS 866.6–867.4 MHz"
        }
        CAT_SET_RF_BAND: int = 0x02 # Category for RF Band commands
        MID_SET_RF_BAND: int = 0x03 # MID for Set RF Band

        try:
            if not (0 <= band_code <= 8):
                raise ValueError(f"Invalid band_code: {band_code}. Must be between 0 and 8.")

            # Ensure reader is idle before changing critical RF settings
            if not self.stop_inventory():
                print("❌ Failed to stop inventory before setting RF band.")
                return False
            
            # Check if reader is truly idle and stable
            if not self.is_idle():
                print("❌ Reader is not idle. Cannot safely set RF band.")
                return False
            
            self.uart.flush_input() # Clear input buffer
            time.sleep(0.5) # Additional delay for reader to settle

            # Build payload and frame
            payload: bytes = bytes([band_code])
            frame: bytes = self.build_frame(mid=(CAT_SET_RF_BAND << 8) | MID_SET_RF_BAND, payload=payload, rs485=self.rs485, notify=False)
            
            band_name_log: str = RF_BAND_CODES.get(band_code, 'Unknown')
            print(f"📤 Setting RF Band to {band_name_log} [Persist={'Yes' if persist else 'No'}].")
            print(f"📤 Sending frame: {frame.hex().upper()}")
            self.send(frame)

            # Wait and parse response within a timeout
            response_timeout: float = 1.0
            start_time: float = time.time()
            receive_buffer: bytes = b""

            while time.time() - start_time < response_timeout:
                raw_response_chunk: bytes = self.receive(64)
                if not raw_response_chunk:
                    time.sleep(0.01) # Small delay if no data
                    continue

                receive_buffer += raw_response_chunk
                frames_in_buffer: List[bytes] = self.extract_valid_frames(receive_buffer)

                if frames_in_buffer:
                    # Clear processed frames from buffer
                    last_extracted = frames_in_buffer[-1]
                    idx_end_last = receive_buffer.find(last_extracted) + len(last_extracted)
                    receive_buffer = receive_buffer[idx_end_last:]

                for frame_in_buffer in frames_in_buffer:
                    try:
                        parsed_response: Dict[str, Any] = self.parse_frame(frame_in_buffer)
                        mid_response: int = parsed_response.get("mid", -1)
                        cat_response: int = parsed_response.get("category", -1)
                        data_payload: bytes = parsed_response.get("data", b"")

                        # Check if the response matches the expected MID and Category
                        if cat_response == CAT_SET_RF_BAND and mid_response == MID_SET_RF_BAND:
                            print(f"📥 RF Band set response received: {data_payload.hex().upper()}.")

                            if len(data_payload) < 1:
                                raise ValueError("⚠️ Invalid response length for set RF band. Expected at least 1 byte.")

                            status_code: int = data_payload[0]
                            if status_code == 0x00:
                                print(f"✅ RF Band successfully set to {band_name_log} [Persist={'Yes' if persist else 'No'}].")
                                return True
                            else:
                                error_map: Dict[int, str] = {
                                    0x01: "Unsupported frequency by hardware.",
                                    0x02: "Save failed (error saving configuration)."
                                }
                                reason_msg: str = error_map.get(status_code, "Unknown error.")
                                print(f"❌ Failed to set RF band (status=0x{status_code:02X}): {reason_msg}.")
                                return False
                        else:
                            print(f"⚠️ Ignored frame with CAT=0x{cat_response:02X}, MID=0x{mid_response:02X} (expecting CAT=0x{CAT_SET_RF_BAND:02X}, MID=0x{MID_SET_RF_BAND:02X}).")
                            continue # Ignore unrelated frames and continue waiting

                    except ValueError as ve:
                        print(f"⚠️ Frame parsing error during set_rf_band response processing: {ve}. Skipping frame.")
                        continue
                    except Exception as ex:
                        print(f"⚠️ An unexpected error occurred processing frame in set_rf_band: {ex}. Skipping.")
                        continue

            print("❌ No valid response for set_rf_band within timeout.")
            return False

        except ValueError as ve:
            print(f"❌ Input validation error in set_rf_band: {ve}")
            return False
        except Exception as e:
            print(f"❌ An unexpected exception occurred while setting RF band: {e}")
            return False
            
    def query_working_frequency(self) -> Dict[str, Any]:
        """
        Queries the reader's working frequency configuration (e.g., auto-hopping or manual channels).

        Returns:
            dict: A dictionary containing the 'mode' ('auto' | 'manual' | 'unknown')
                  and 'channels' (list of channel numbers if manual).
        """
        try:
            self.uart.flush_input() # Clear input buffer
            
            # Build and send the command frame (MID 0x0206)
            frame: bytes = self.build_frame(mid=MID.QUERY_WORKING_FREQUENCY, payload=b'', rs485=self.rs485, notify=False)
            self.uart.send(frame)

            time.sleep(0.1) # Short delay for response
            raw_response: bytes = self.uart.receive(64) # Receive response
            if not raw_response:
                print("❌ No response received for working frequency query.")
                return {"mode": "error", "channels": []} # Return error state

            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_response.get("mid", -1)
            data_payload: bytes = parsed_response.get("data", b"")

            # Validate response MID
            if mid_response != (MID.QUERY_WORKING_FREQUENCY & 0xFF):
                print(f"❌ Unexpected MID (0x{mid_response:02X}) for working frequency query. Expected 0x{(MID.QUERY_WORKING_FREQUENCY & 0xFF):02X}.")
                return {"mode": "error", "channels": []}

            if not data_payload:
                return {"mode": "unknown", "channels": []} # No data, unknown mode

            mode_byte: int = data_payload[0]
            if mode_byte == 0x00: # Auto mode
                return {"mode": "auto", "channels": []}
            elif mode_byte == 0x01: # Manual mode, followed by channel list
                channels: List[int] = list(data_payload[1:]) # Remaining bytes are channel numbers
                return {"mode": "manual", "channels": channels}
            else:
                # Unknown mode byte
                return {"mode": f"unknown (0x{mode_byte:02X})", "channels": []}

        except ValueError as ve:
            print(f"❌ Data parsing error in query_working_frequency: {ve}")
            return {"mode": "error", "channels": []}
        except Exception as e:
            print(f"❌ An unexpected exception occurred in query_working_frequency: {e}")
            return {"mode": "error", "channels": []}


    def query_filter_settings(self) -> Dict[str, Any]:
        """
        Queries the reader's tag filtering settings, including:
        - Repeat tag suppression time (in 10ms units)
        - RSSI (Received Signal Strength Indicator) threshold

        Returns:
            dict: A dictionary containing 'repeat_time' (int, in 10ms units) and 'rssi_threshold' (Optional[int]).
                  Returns a dictionary with default/error values on failure.
        """
        try:
            self.uart.flush_input() # Clear input buffer
            
            # Build and send the command frame (MID 0x020A)
            frame: bytes = self.build_frame(mid=MID.QUERY_FILTER, payload=b'', rs485=self.rs485, notify=False)
            self.uart.send(frame)

            time.sleep(0.1) # Short delay for response
            raw_response: bytes = self.uart.receive(64) # Receive response
            if not raw_response:
                print("❌ No response received for filter settings query.")
                return {"repeat_time": 0, "rssi_threshold": None}

            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            mid_response: int = parsed_response.get("mid", -1)
            data_payload: bytes = parsed_response.get("data", b"")

            # Validate response MID
            if mid_response != (MID.QUERY_FILTER & 0xFF):
                print(f"❌ Unexpected MID (0x{mid_response:02X}) for filter settings query. Expected 0x{(MID.QUERY_FILTER & 0xFF):02X}.")
                return {"repeat_time": 0, "rssi_threshold": None}

            if len(data_payload) < 2:
                # Need at least 2 bytes for repeat_time (U16)
                print("❌ Insufficient data in response for filter settings (expected at least 2 bytes).")
                return {"repeat_time": 0, "rssi_threshold": None}

            # Repeat tag suppression time (2 bytes, U16, in 10ms units)
            repeat_time: int = int.from_bytes(data_payload[0:2], 'big')
            
            # RSSI threshold (1 byte, U8, optional if payload is shorter)
            rssi_threshold: Optional[int] = data_payload[2] if len(data_payload) >= 3 else None

            return {
                "repeat_time": repeat_time,
                "rssi_threshold": rssi_threshold
            }

        except ValueError as ve:
            print(f"❌ Data parsing error in query_filter_settings: {ve}")
            return {"repeat_time": 0, "rssi_threshold": None}
        except Exception as e:
            print(f"❌ An unexpected exception occurred in query_filter_settings: {e}")
            return {"repeat_time": 0, "rssi_threshold": None}

    # --- Beeper Control Methods ---

    def get_beeper(self) -> bool:
        """
        Determines if beeping is enabled based on the internally stored beeper mode.
        Returns True if beeper mode is set to 'Always Beep' (1) or 'Beep on New Tag' (2).

        Returns:
            bool: True if beeping is expected, False otherwise.
        """
        return self.beeper_mode in (1, 2)


    def set_beeper(self, mode: int) -> bool:
        """
        Sets the reader's beeper mode.

        Args:
            mode (int): The desired beeper mode:
                        0 = No Beep (stop buzzer immediately)
                        1 = Continuous Beep (start buzzing immediately)
                        2 = Beep on New Tag (buzzer will only activate upon new tag detection)

        Returns:
            bool: True if the internal mode was set and the hardware command (if any) succeeded.

        Raises:
            ValueError: If an invalid mode is provided.
        """
        if mode not in (0, 1, 2):
            raise ValueError(f"Invalid mode: {mode}. Must be 0 (No Beep), 1 (Continuous), or 2 (New Tag).")

        success: bool = True

        if mode == 0: # No Beep: send stop command
            print("Setting beeper mode to 'No Beep' (stopping buzzer).")
            success = self._send_beeper_command(ring=0, duration=0) 
        elif mode == 1: # Continuous Beep: send ring continuously command
            print("Setting beeper mode to 'Continuous Beep'.")
            success = self._send_beeper_command(ring=1, duration=1) 
        elif mode == 2:
            # Beep on New Tag: No immediate hardware command is sent.
            # The beeper will be controlled by tag detection logic.
            print("Setting beeper mode to 'Beep on New Tag' (no immediate buzzer action).")
            pass 

        # Update internal beeper_mode only if the command succeeded or it's mode 2 (no command needed).
        if success or mode == 2:
            self.beeper_mode = mode 
        else:
            print(f"⚠️ Failed to apply buzzer command for mode {mode}. Internal mode not updated.")

        return success

    def _send_beeper_command(self, ring: int, duration: int) -> bool:
        """
        Sends a direct command to control the reader's buzzer.

        Args:
            ring (int): 0 to stop buzzing, 1 to start buzzing.
            duration (int): 0 for a single beep, 1 to keep buzzing continuously.

        Returns:
            bool: True if the command successfully triggered the buzzer action, False otherwise.

        Raises:
            ValueError: If `ring` or `duration` parameters are invalid.
        """
        if ring not in (0, 1) or duration not in (0, 1):
            raise ValueError(f"Invalid parameters: ring ({ring}) and duration ({duration}) must be 0 or 1.")

        try:
            self.uart.flush_input() # Clear any previous data in the UART buffer
            
            # Build the payload (2 bytes: ring_flag, duration_flag)
            payload: bytes = bytes([ring, duration])
            # print(f"📦 Buzzer control payload: {payload.hex().upper()}") # Verbose debug

            # Build the communication frame (Category 0x01, MID 0x1F)
            mid: int = MID.BUZZER_SWITCH # MID 0x011E
            frame: bytes = self.build_frame(mid=mid, payload=payload, rs485=self.rs485, notify=False)
            # print(f"📤 Sending buzzer control frame: {frame.hex().upper()}") # Verbose debug

            self.send(frame) # Send the frame to the reader

            raw_response: bytes = self.receive(64) # Receive and parse the response
            # print(f"📥 Received raw response for buzzer control: {raw_response.hex().upper()}") # Verbose debug

            # Basic validation of the response frame structure
            if len(raw_response) < 9:
                print("❌ Buzzer control response frame too short.")
                return False
            if raw_response[0] != FRAME_HEADER:
                print("❌ Buzzer control response frame has invalid header.")
                return False

            parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
            response_mid: int = parsed_response.get("mid", -1)
            response_data: bytes = parsed_response.get("data", b"")

            # Check the response MID (expecting low byte of BUZZER_SWITCH, i.e., 0x1E) and result code
            if response_mid == (mid & 0xFF): # Compare only the low byte of the MID
                result_code: int = response_data[0] if len(response_data) > 0 else -1
                if result_code == 0x00:
                    print("✅ Buzzer control succeeded.")
                    return True
                else:
                    print(f"❌ Buzzer control failed. Result code: 0x{result_code:02X}.")
                    return False
            elif response_mid == MID.ERROR_NOTIFICATION: # Handle generic error/illegal instruction (MID 0x00)
                error_code: int = response_data[0] if len(response_data) > 0 else -1
                print(f"🚨 Illegal instruction response for buzzer control. Error code: 0x{error_code:02X}.")
                return False
            else:
                print(f"❌ Unexpected MID (0x{response_mid:02X}) in buzzer control response.")
                return False

        except ValueError as ve:
            print(f"❌ Data validation/parsing error in _send_beeper_command: {ve}.")
            return False
        except Exception as e:
            print(f"❌ An unexpected exception occurred in _send_beeper_command: {e}.")
            return False
            
    # --- Session Management Methods ---

    def get_session(self) -> Optional[int]:
        """
        Queries the current inventory session (S0, S1, S2, S3) configured on the reader.

        Returns:
            Optional[int]: The current session ID (0-3) if successful, None otherwise.
        """
        try:
            self.uart.flush_input() # Clear input buffer
            
            # Build and send the QUERY_BASEBAND command frame (MID 0x020C)
            # The baseband query typically returns various baseband parameters, including session.
            frame: bytes = self.build_frame(mid=MID.QUERY_BASEBAND, payload=b'', rs485=False, notify=False)
            self.uart.send(frame)

            raw_response: bytes = self.receive(64) # Receive response
            if not raw_response:
                print("❌ No response received for session query.")
                return None

            # print(f"📥 Raw response for session query: {raw_response.hex().upper()}") # Verbose debug
            frames: List[bytes] = self.extract_valid_frames(raw_response)
            
            if not frames:
                print("❌ No valid frames extracted for session query.")
                return None

            frame_data: bytes = frames[0] # Assume the first valid frame contains the response
            parsed_response: Dict[str, Any] = self.parse_frame(frame_data)
            
            data_payload: bytes = parsed_response.get("data", b"")
            if len(data_payload) < 4:
                # Baseband query response (speed, q_value, session, inventory_flag) is usually 4 bytes.
                print("❌ Response too short for session information (expected at least 4 bytes).")
                return None

            # Session is typically the 3rd byte (index 2) in the baseband response data
            session_id: int = data_payload[2]
            if session_id in (0, 1, 2, 3):
                print(f"✅ Current session: {session_id}.")
                return session_id
            else:
                print(f"❌ Invalid session value received: {session_id}.")
                return None

        except ValueError as ve:
            print(f"❌ Data parsing error in get_session: {ve}")
            return None
        except Exception as e:
            print(f"❌ An unexpected exception occurred in get_session: {e}")
            return None

    def is_idle(self, retry: int = 3, delay: float = 0.3, settle_delay: float = 0.5) -> bool:
        """
        Checks if the RFID reader is currently in an idle state.
        It sends a STOP command and waits for a confirmation response.

        Args:
            retry (int): Number of times to retry the idle check if no immediate confirmation.
            delay (float): Delay in seconds between retries.
            settle_delay (float): Additional delay after confirmed idle to ensure hardware stability.

        Returns:
            bool: True if the reader successfully enters or is confirmed to be in the idle state, False otherwise.
        """
        for attempt in range(retry):
            try:
                self.uart.flush_input() # Clear any stale data
                
                # Build and send the STOP_INVENTORY command frame
                stop_frame: bytes = self.build_frame(mid=MID.STOP_INVENTORY, payload=b'', rs485=self.rs485, notify=False)
                self.uart.send(stop_frame)

                raw_response: bytes = self.uart.receive(64) # Read response
                if not raw_response:
                    print(f"❌ Attempt {attempt+1}/{retry}: No response received for Idle check.")
                    time.sleep(delay)
                    continue

                parsed_response: Dict[str, Any] = self.parse_frame(raw_response)
                mid_response: int = parsed_response.get("mid", -1)
                data_payload: bytes = parsed_response.get("data", b"")

                # Check for successful STOP_OPERATION (0xFF) or STOP_INVENTORY (0x02FF -> 0xFF) response with success code (0x00)
                if (mid_response == MID.STOP_OPERATION or mid_response == (MID.STOP_INVENTORY & 0xFF)) and \
                   len(data_payload) > 0 and data_payload[0] == 0x00:
                    print("✅ Reader responded with STOP success. Reader is idle.")
                    print(f"⏳ Waiting {settle_delay}s for hardware to fully settle...")
                    time.sleep(settle_delay) # Wait for hardware stability
                    return True
                else:
                    print(f"❌ Attempt {attempt+1}/{retry}: Reader not idle yet. Response MID: 0x{mid_response:02X}, Data: {data_payload.hex().upper()}. Retrying.")
                    time.sleep(delay)

            except ValueError as ve:
                print(f"❌ Attempt {attempt+1}/{retry}: Data parsing error during idle check: {ve}. Retrying.")
                time.sleep(delay)
            except Exception as e:
                print(f"❌ Attempt {attempt+1}/{retry}: An unexpected exception occurred in is_idle: {e}. Retrying.")
                time.sleep(delay)

        print(f"❌ Reader did not enter Idle state after {retry} retries.")
        return False

    def configure_baseband(self, speed: int, q_value: int, session: int, inventory_flag: int) -> bool:
        """
        Configures the EPC baseband parameters (e.g., Tari, Modulation, Q-value, Session, Inventory Flag)
        using a TLV (Type-Length-Value) encoded payload.

        Args:
            speed (int): Baseband speed setting (0, 1, 2, 3, 4, or 255 for auto).
            q_value (int): Q value for inventory (0-15).
            session (int): Session (S0, S1, S2, S3) for inventory (0-3).
            inventory_flag (int): Inventory flag (0, 1, or 2).

        Returns:
            bool: True if baseband configuration was successful, False otherwise.
        """
        # --- Step 1: Validate Input Parameters ---
        if speed not in (0, 1, 2, 3, 4, 255):
            print(f"❌ Invalid speed parameter: {speed}. Must be 0, 1, 2, 3, 4, or 255.")
            return False
        if not (0 <= q_value <= 15):
            print(f"❌ Invalid Q value: {q_value}. Must be between 0 and 15.")
            return False
        if session not in (0, 1, 2, 3):
            print(f"❌ Invalid session: {session}. Must be 0, 1, 2, or 3.")
            return False
        if inventory_flag not in (0, 1, 2):
            print(f"❌ Invalid inventory flag: {inventory_flag}. Must be 0, 1, or 2.")
            return False

        try:
            # --- Step 2: Ensure Reader is Idle ---
            # It's crucial that the reader is not performing other operations before configuration.
            if not self.stop_inventory():
                print("❌ Failed to stop previous inventory. Baseband configuration aborted.")
                return False
            if not self.is_idle():
                print("❌ Reader is not idle. Baseband configuration aborted.")
                return False
            time.sleep(0.1) # Small delay for stability
            self.uart.flush_input() # Clear any residual data

            # --- Step 3: Encode TLV Payload for Baseband Configuration ---
            # Each parameter (speed, q, session, flag) is sent as a Type (PID) and Value (1 byte).
            payload: bytes = bytes([
                0x01, speed,         # PID 0x01 for Speed
                0x02, q_value,       # PID 0x02 for Q Value
                0x03, session,       # PID 0x03 for Session
                0x04, inventory_flag # PID 0x04 for Inventory Flag
            ])

            # --- Step 4: Build Command Frame ---
            # Use MID.CONFIG_BASEBAND (0x020B) for baseband configuration.
            frame: bytes = self.build_frame(mid=MID.CONFIG_BASEBAND, payload=payload, rs485=False, notify=False)
            print(f"📤 Sending baseband configuration frame: {frame.hex().upper()}")

            # --- Step 5: Send Frame to Reader ---
            self.uart.send(frame)

            # --- Step 6: Wait for and Parse Response ---
            raw_response: bytes = self.uart.receive(64) # Receive response
            print(f"📥 Raw baseband config response: {raw_response.hex().upper()}")
            
            frames: List[bytes] = self.extract_valid_frames(raw_response)
            if not frames:
                print("❌ No valid response frames received for baseband configuration.")
                return False

            for response_frame in frames:
                parsed_response: Dict[str, Any] = self.parse_frame(response_frame)
                mid_response: int = parsed_response.get("mid", -1)
                category_response: int = parsed_response.get("category", -1)
                data_payload: bytes = parsed_response.get("data", b"")

                # Check for successful response to CONFIG_BASEBAND (MID 0x0B)
                # Category can be 0x01 or 0x02 based on specific reader types or protocol nuances.
                if mid_response == 0x0B and category_response in (0x01, 0x02):
                    result_code: int = data_payload[0] if data_payload else -1
                    if result_code == 0x00:
                        print("✅ Baseband configuration successful (CONFIG_BASEBAND OK).")
                        return True
                    else:
                        # Map specific error codes for baseband configuration
                        errors_map: Dict[int, str] = {
                            0x01: "Unsupported baseband parameter.",
                            0x02: "Q parameter error (value out of range or invalid for current mode).",
                            0x03: "Session parameter error.",
                            0x04: "Inventory Flag parameter error.",
                            0x05: "Other parameter error.",
                            0x06: "Save failed (error saving configuration to non-volatile memory)."
                        }
                        error_msg: str = errors_map.get(result_code, f"Unknown error code 0x{result_code:02X}.")
                        print(f"❌ Baseband configuration failed: {error_msg}.")
                        return False

                # Handle generic error responses (MID 0x00)
                elif mid_response == MID.ERROR_NOTIFICATION:
                    error_code_generic: int = data_payload[0] if data_payload else -1
                    generic_errors_map: Dict[int, str] = {
                        0x01: "Unsupported instruction.", 0x02: "CRC or mode error.",
                        0x03: "Parameter error.", 0x04: "Reader is busy.", 0x05: "Invalid state."
                    }
                    generic_error_msg: str = generic_errors_map.get(error_code_generic, f"Unknown generic error 0x{error_code_generic:02X}.")
                    print(f"❌ Generic error during baseband config: {generic_error_msg}.")
                    return False
            
            print("❌ No valid CONFIG_BASEBAND reply found among received frames.")
            return False

        except ValueError as ve:
            print(f"❌ Data validation/parsing error during baseband configuration: {ve}")
            return False
        except Exception as e:
            print(f"❌ An unexpected exception occurred during configure_baseband: {e}")
            return False

    def query_baseband_profile(self) -> Dict[str, Any]:
        """
        Queries the current EPC baseband parameters from the reader.

        Returns:
            dict: A dictionary containing the baseband settings:
                  'speed', 'q_value', 'session', and 'inventory_flag'.
                  Returns an empty dictionary on failure.
        """
        try:
            self.stop_inventory() # Ensure reader is idle before querying
            self.uart.flush_input() # Clear input buffer

            # Build and send the QUERY_BASEBAND command frame (MID 0x020C)
            frame: bytes = self.build_frame(mid=MID.QUERY_BASEBAND, payload=b'', rs485=False, notify=False)
            self.uart.send(frame)
            
            raw_response: bytes = self.uart.receive(64) # Receive response
            if not raw_response:
                print("❌ No response received for baseband profile query.")
                return {}

            frames: List[bytes] = self.extract_valid_frames(raw_response)
            
            if not frames:
                print("❌ No valid frames extracted for baseband profile query.")
                return {}

            # Assume the first valid frame is the baseband response
            response_frame_data: bytes = frames[0]
            parsed_response: Dict[str, Any] = self.parse_frame(response_frame_data)
            
            # The data payload contains the 4 baseband parameters
            data_payload: bytes = parsed_response.get('data', b"")
            
            if len(data_payload) < 4:
                print(f"❌ Invalid baseband profile response length. Expected 4 bytes, got {len(data_payload)}.")
                return {}

            return {
                "speed": data_payload[0],
                "q_value": data_payload[1],
                "session": data_payload[2],
                "inventory_flag": data_payload[3]
            }
            
        except ValueError as ve:
            print(f"❌ Data parsing error in query_baseband_profile: {ve}")
            return {}
        except Exception as e:
            print(f"❌ An unexpected exception occurred in query_baseband_profile: {e}")
            return {}