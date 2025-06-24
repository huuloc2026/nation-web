import serial
import time
import logging
from typing import Union, Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RFIDTag:
    """Represents an RFID tag with its properties."""
    epc: str
    tid: Optional[str] = None
    rssi: Optional[int] = None
    phase: Optional[int] = None
    frequency: Optional[int] = None
    antenna: Optional[int] = None
    
    def __str__(self):
        result = f"EPC: {self.epc}"
        if self.tid:
            result += f", TID: {self.tid}"
        if self.rssi is not None:
            result += f", RSSI: {self.rssi} dBm"
        if self.antenna is not None:
            result += f", Antenna: {self.antenna}"
        return result

@dataclass
class InventoryResult:
    """Represents the result of an inventory operation."""
    status: int
    status_description: str
    tags: List[RFIDTag]
    antenna: Optional[int] = None
    read_rate: Optional[int] = None
    total_count: Optional[int] = None
    is_complete: bool = False
    
    def __str__(self):
        result = f"Status: {self.status_description} (0x{self.status:02X})\n"
        result += f"Tags found: {len(self.tags)}\n"
        if self.antenna is not None:
            result += f"Antenna: {self.antenna}\n"
        if self.read_rate is not None:
            result += f"Read Rate: {self.read_rate} tags/sec\n"
        if self.total_count is not None:
            result += f"Total Count: {self.total_count}\n"
        
        for i, tag in enumerate(self.tags, 1):
            result += f"Tag {i}: {tag}\n"
        
        return result


def calculate_crc16(data: bytes) -> int:
    """Calculate CRC16 checksum for RFID commands.

    Parameters:
        data (bytes): Data bytes to calculate CRC for.

    Returns:
        int: 16-bit CRC value.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc

def parse_frames(data: bytes) -> Tuple[List[bytes], bytes]:
    """Parse complete frames from raw data buffer.

    Parameters:
        data (bytes): Raw data buffer containing one or more frames.

    Returns:
        Tuple[List[bytes], bytes]: A tuple containing:
            - List of complete frames
            - Remaining unparsed data
    """
    frames = []
    offset = 0
    
    while offset < len(data):
        if offset >= len(data):
            break
            
        # First byte is the frame length (excluding itself)
        len_byte = data[offset]
        
        # Sanity check - frame length should be reasonable 
        # Minimum: 4 bytes (Adr + reCmd + Status + CRC-16)
        # Maximum: reasonable limit
        if len_byte < 4 or len_byte > 100:
            logger.error(f"Warning: Invalid Len byte {len_byte} at offset {offset}")
            offset += 1  # Skip this byte and try next
            continue
            
        # Total frame size = Len + 1 (include the Len byte itself)
        total_frame_size = len_byte + 1
        
        # Check if we have enough data for the complete frame
        if offset + total_frame_size > len(data):
            # Not enough data for complete frame, break and wait for more data
            break
            
        # Extract the complete frame (including Len byte)
        frame = data[offset:offset + total_frame_size]
        frames.append(frame)
        
        # Move to next frame
        offset += total_frame_size
    
    return frames, data[offset:]  # Return frames and remaining unparsed data

def verify_crc16(frame: bytes) -> bool:
    """Verify CRC16 checksum for a complete frame.

    Parameters:
        frame (bytes): Complete frame including CRC bytes.

    Returns:
        bool: True if CRC is valid, False otherwise.
    """
    if len(frame) < 5:  # Minimum frame: Len + Adr + reCmd + Status + CRC(2)
        return False
    
    # CRC is calculated from Len byte to end of Data[] (excluding CRC itself)
    data_for_crc = frame[:-2]  # All bytes except last 2 (CRC bytes)
    received_crc_bytes = frame[-2:]  # Last 2 bytes are CRC
    received_crc = int.from_bytes(received_crc_bytes, 'little')
    
    # Calculate expected CRC
    calculated_crc = calculate_crc16(data_for_crc)
    
    return calculated_crc == received_crc

def decode_antenna_mask(ant_byte: int) -> List[int]:
    """Decode antenna mask byte to list of active antennas.

    Parameters:
        ant_byte (int): Antenna mask byte where each bit represents an antenna.

    Returns:
        List[int]: List of active antenna numbers (1-based).
    """
    # # For 16-port readers (direct antenna number)
    # if ant_byte <= 15:
    #     return [ant_byte + 1]  # Convert 0-15 to 1-16
        
    # For 4/8-port readers (bit mask)
    antennas = []
    # Check each bit (0-7) and add antenna number if bit is set
    # Note: bit 0 corresponds to Antenna 1, bit 1 to Antenna 2, etc.
    for i in range(8):
        if ant_byte & (1 << i):
            antennas.append(i + 1)  # Convert bit position to antenna number
    return sorted(antennas)  # Sort antennas for consistent output

epc_list = set()
def print_frame_details(frame: bytes) -> None:
    """Print detailed information about a frame.

    Parameters:
        frame (bytes): Complete frame to analyze and print.
    """
    if len(frame) < 5:
        logger.error(f"❌ Invalid frame (too short): {' '.join(f'{b:02X}' for b in frame)}")
        return
    
    len_byte = frame[0]        # Length excluding itself
    address = frame[1]         # Reader address
    re_command = frame[2]      # Response command
    status = frame[3]          # Status byte
    

    # Extract CRC (last 2 bytes)
    crc_bytes = frame[-2:]
    crc_value = int.from_bytes(crc_bytes, 'little')
    
    # Data section (everything between Status and CRC)
    data_section = frame[4:-2] if len(frame) > 6 else b''
    
    # Verify CRC
    crc_valid = verify_crc16(frame)
    crc_status = "✅ Valid" if crc_valid else "❌ Invalid"
    
    logger.info(f"📦 Frame: {' '.join(f'{b:02X}' for b in frame)}")
    logger.info(f"   Len: {len_byte} (frame content length excluding Len byte)")
    logger.info(f"   Total Frame Size: {len(frame)} bytes")
    logger.info(f"   Address: 0x{address:02X}")
    logger.info(f"   reCmd: 0x{re_command:02X}")
    logger.info(f"   Status: 0x{status:02X} {'✅ Success' if status == 0x00 else '❌ Error' if status != 0x28 else '💓 Heartbeat'}")
    logger.info(f"   CRC: {' '.join(f'{b:02X}' for b in crc_bytes)} (0x{crc_value:04X}) {crc_status}")
    
    # Parse based on response command type
    if re_command == 0x50:
        logger.info("   Type: 🚀 START INVENTORY Response")
        if status == 0x00:
            logger.info("   Result: ✅ Inventory started successfully")
        else:
            logger.error(f"   Result: ❌ Error starting inventory (status: 0x{status:02X})")
            
    elif re_command == 0x51:
        logger.info("   Type: 🛑 STOP INVENTORY Response") 
        if status == 0x00:
            logger.info("   Result: ✅ Inventory stopped successfully")
        else:
            logger.error(f"   Result: ❌ Error stopping inventory (status: 0x{status:02X})")
            
    elif re_command == 0xEE:
        if status == 0x00:
            logger.info("   Type: 🏷️  TAG DATA")
            if len(data_section) >= 3:
                # Parse tag data: Ant Len EPC/TID RSSI
                ant_byte = data_section[0]
                epc_length = data_section[1]
                
                logger.info(f"   Antenna Mask: 0x{ant_byte:02X} (binary: {ant_byte:08b})")
                active_antennas = decode_antenna_mask(ant_byte)
                if active_antennas:
                    logger.info(f"   Active Antennas: {', '.join(f'Ant{a}' for a in active_antennas)}")
                else:
                    logger.info("   Active Antennas: None detected")
                
                logger.info(f"   EPC/TID Length: {epc_length} bytes")
                
                if len(data_section) >= 2 + epc_length + 1:  # Ant + Len + EPC + RSSI
                    epc_data = data_section[2:2+epc_length]
                    rssi = data_section[2+epc_length]
                    
                    epc_hex = ' '.join(f'{b:02X}' for b in epc_data)
                    logger.info(f"   EPC/TID: {epc_hex}")
                    logger.info(f"   RSSI: 0x{rssi:02X} ({rssi} dBm)")
                    
                    # Convert EPC to string representation
                    epc_string = ''.join(f'{b:02X}' for b in epc_data)
                    logger.info(f"   EPC String: {epc_string}")

                    epc_list.add(epc_string)
                    
                else:
                    logger.error("   ⚠️  Incomplete tag data")
            else:
                logger.error("   ⚠️  Invalid tag data format")
                
        elif status == 0x28:
            logger.info("   Type: 💓 HEARTBEAT PACKET")
            if len(data_section) >= 2:
                read_rate = data_section[0] if len(data_section) > 0 else 0
                total_count = data_section[1] if len(data_section) > 1 else 0
                logger.info(f"   ReadRate: {read_rate}")
                logger.info(f"   TotalCount: {total_count}")
            else:
                logger.error("   ⚠️  Incomplete heartbeat data")
        else:
            logger.error(f"   Type: ❓ Unknown EE status (0x{status:02X})")
            
    else:
        logger.error(f"   Type: ❓ Unknown response command (0x{re_command:02X})")
        
    if data_section and len(data_section) > 0:
        logger.info(f"   Data Section ({len(data_section)} bytes): {' '.join(f'{b:02X}' for b in data_section)}")
    
    print()

def send_command(serial_port: serial.Serial, address: int, command: bytes, target: int = 0) -> bool:
    """Send a command to the Ex10 RFID reader.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int): Reader address (usually 0x00).
        command (bytes): Command bytes to send.
        target (int, optional): Target value (0 for target A, 1 for target B). Defaults to 0.

    Returns:
        bool: True if command was sent successfully, False otherwise.
    """
    try:
        # Build command frame: Len Adr Cmd Data[]
        if command == 0x50:  # START command needs target parameter
            cmd_data = bytes([0x05, address, command, target])  # Length=5, Adr, Cmd, Target
        else:  # STOP command
            cmd_data = bytes([0x04, address, command])  # Length=4, Adr, Cmd
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        command_name = "START INVENTORY" if command == 0x50 else "STOP INVENTORY"
        command_str = ' '.join(f'{b:02X}' for b in full_command)
        logger.info(f"📤 Sent {command_name}: {command_str}")
        
        if command == 0x50:
            target_name = "Target A" if target == 0 else "Target B"
            logger.info(f"   Target: {target_name} (0x{target:02X})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error sending command: {e}")
        return False

def get_reader_info(serial_port: serial.Serial, address: int = 0x00) -> Optional[Dict]:
    """Obtain reader information including firmware version, model, protocols, frequency band, etc.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        Optional[Dict]: Dictionary containing reader information or None if command fails.
            Dictionary includes:
            - firmware_version (str): Version in format "X.Y"
            - reader_type (str): Reader type in hex
            - supported_protocols (list): List of supported protocols
            - frequency_band (dict): Frequency configuration
            - rf_power (dict): RF power configuration
            - inventory_time (int): Inventory time in ms
            - antenna_config (int): Antenna configuration byte
            - antenna_check (str): "ON" or "OFF"
    """
    try:
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([0x04, address, 0x21])  # Len=4, Adr, Cmd=0x21
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Get Reader Info: {' '.join(f'{b:02X}' for b in full_command)}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 18:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return None
            
        # Read response
        response = serial_port.read(18)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 18 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return None
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        data = response[4:-2]  # Data section (excluding CRC)
        
        if status != 0x00:
            logger.error(f"❌ Command failed with status: 0x{status:02X}")
            return None
            
        # Parse data section
        version = int.from_bytes(data[0:2], 'little')
        reader_type = data[2]
        tr_type = data[3]
        dmaxfre = data[4]
        dminfre = data[5]
        power = data[6]
        scntm = data[7]
        ant_config = data[8]
        reserved1 = data[9]
        reserved2 = data[10]
        check_ant = data[11]
        
        # Parse frequency band configuration
        max_freq_band = (dmaxfre >> 6) & 0x03
        min_freq_band = (dminfre >> 6) & 0x03
        max_freq_point = dmaxfre & 0x3F
        min_freq_point = dminfre & 0x3F
        
        # Parse supported protocols
        protocols = []
        if tr_type & 0x01:
            protocols.append("ISO18000-6B")
        if tr_type & 0x02:
            protocols.append("ISO18000-6C")
            
        # Build result dictionary
        result = {
            'firmware_version': f"{version >> 8}.{version & 0xFF}",
            'reader_type': f"0x{reader_type:02X}",
            'supported_protocols': protocols,
            'frequency_band': {
                'max_band': max_freq_band,
                'min_band': min_freq_band,
                'max_freq_point': max_freq_point,
                'min_freq_point': min_freq_point
            },
            'rf_power': power,
            'inventory_time': scntm,
            'antenna_config': ant_config,
            'antenna_check': "ON" if check_ant == 1 else "OFF"
        }
        
        # Print information
        logger.info("\n📋 Reader Information:")
        logger.info(f"   Firmware Version: {result['firmware_version']}")
        logger.info(f"   Reader Type: {result['reader_type']}")
        logger.info("\n   Supported Protocols:")
        for protocol in ["ISO18000-6C", "ISO18000-6B"]:
            logger.info(f"      {protocol}: {'Yes' if protocol in result['supported_protocols'] else 'No'}")
            
        logger.info("\n   Frequency Configuration:")
        # Map frequency band numbers to names
        band_names = {
            0: "US band",
            1: "European band",
            2: "Chinese band",
            3: "Custom band"
        }
        band_name = band_names.get(max_freq_band, "Unknown band")
        logger.info(f"      Frequency Band: {band_name}")
        logger.info(f"      Max Frequency Point: {max_freq_point}")
        logger.info(f"      Min Frequency Point: {min_freq_point}")
        
        # Check if power is 0xFF (255) and get individual antenna powers if needed
        if power == 0xFF:
            logger.info("\n   RF Power: Different power levels per antenna")
            power_levels = get_power(serial_port, address)
            if power_levels:
                logger.info("\n   Antenna Power Levels:")
                for ant, pwr in power_levels.items():
                    logger.info(f"      Ant{ant}: {pwr} dBm")
        else:
            logger.info(f"\n   RF Power: {result['rf_power']} dBm")
            
        logger.info(f"   Inventory Time: {result['inventory_time']} ms")
        logger.info(f"   Antenna Configuration: 0x{ant_config:02X}")
        logger.info(f"   Antenna Check: {result['antenna_check']}")
        
        # Print raw data for debugging
        # print("\n   Raw Response Data:")
        # print(f"      Full Response: {' '.join(f'{b:02X}' for b in response)}")
        # print(f"      Data Section: {' '.join(f'{b:02X}' for b in data)}")
        # print(f"      Power Byte: 0x{power:02X}")
        # print(f"      Antenna Config Byte: 0x{ant_config:02X}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error getting reader info: {e}")
        return None

def connect_reader(port: str = '/dev/cu.usbserial-10', baudrate: int = 57600) -> Optional[serial.Serial]:
    """Connect to the RFID reader via serial port.

    Parameters:
        port (str, optional): Serial port name. Defaults to '/dev/cu.usbserial-10'.
        baudrate (int, optional): Baud rate. Defaults to 57600.

    Returns:
        Optional[serial.Serial]: Serial port object if connection successful, None otherwise.
    """
    try:
        serial_port = serial.Serial(port, baudrate, timeout=1)
        time.sleep(0.5)  # Allow connection to stabilize
        serial_port.reset_input_buffer()
        logger.info("✅ Connected to Ex10 RFID reader")
        return serial_port
    except Exception as e:
        logger.error(f"❌ Error connecting to reader: {e}")
        return None

def stop_inventory(serial_port: serial.Serial, address: int = 0x00) -> bool:
    """Stop the inventory process.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        bool: True if inventory stopped successfully, False otherwise.
    """
    try:
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([0x04, address, 0x51])  # Len=4, Adr, Cmd=0x51
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Stop Inventory: {' '.join(f'{b:02X}' for b in full_command)}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 6:  
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(6)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 6 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        
        if status != 0x00:
            logger.error(f"❌ Stop command failed with status: 0x{status:02X}")
            return False
            
        logger.info("✅ Inventory stopped successfully")
        serial_port.reset_input_buffer()
        return True
        
    except Exception as e:
        logger.error(f"❌ Error stopping inventory: {e}")
        return False

def start_inventory(serial_port: serial.Serial, address: int = 0x00, target: int = 0,
                   tag_callback: Optional[Callable[[RFIDTag], None]] = None,
                   stats_callback: Optional[Callable[[int, int], None]] = None,
                   stop_flag: Optional[Callable[[], bool]] = None) -> bool:
    """Start inventory operation and collect tag data.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int, optional): Reader address. Defaults to 0x00.
        target (int, optional): Target type (0=target A, 1=target B). Defaults to 0.
        tag_callback (Optional[Callable[[RFIDTag], None]], optional): Callback function for tag data.
        stats_callback (Optional[Callable[[int, int], None]], optional): Callback function for statistics.
        stop_flag (Optional[Callable[[], bool]], optional): Function to check if should stop.

    Returns:
        bool: True if operation completed successfully, False otherwise.
    """
    try:
        epc_list.clear()    

        # Clear any pending data
        serial_port.reset_input_buffer()
        logger.info("🧹 Input buffer cleared")
        
        # Send STOP command first (to ensure clean state)
        logger.info("\n--- Sending STOP command ---")
        stop_inventory(serial_port, address)  # Use the new stop function
        time.sleep(0.2)
        
        # Read STOP response
        if serial_port.in_waiting > 0:
            stop_response = serial_port.read(serial_port.in_waiting)
            logger.info(f"📨 STOP Response: {' '.join(f'{b:02X}' for b in stop_response)}")

        serial_port.reset_input_buffer()
        
        # Send START command
        logger.info("\n--- Sending START command ---")
        if not send_command(serial_port, address=address, command=0x50, target=target):
            return False
        
        # Initialize data buffer and counters
        buffer = b''
        frame_count = 0
        tag_count = 0
        start_time = time.time()
        
        logger.info("\n--- Listening for tag responses ---")
        logger.info("Press Ctrl+C to stop...")
        
        while True:
            # Check stop flag if provided
            if stop_flag and stop_flag():
                logger.info("🛑 Stop flag detected, stopping inventory")
                break
                
            # Check for available data
            if serial_port.in_waiting > 0:
                # Read available data and add to buffer
                new_data = serial_port.read(serial_port.in_waiting)
                buffer += new_data
                
                logger.info(f"📨 Raw data: {' '.join(f'{b:02X}' for b in new_data)}")
                
                # Parse frames from buffer
                frames, buffer = parse_frames(buffer)
                
                # Process each complete frame
                for frame in frames:
                    frame_count += 1
                    logger.info(f"\n--- Frame #{frame_count} ---")
                    print_frame_details(frame)
                    
                    # Count different frame types
                    if len(frame) >= 3:
                        re_cmd = frame[2]
                        status = frame[3] if len(frame) > 3 else None
                        
                        if re_cmd == 0xEE and status == 0x00:
                            tag_count += 1
                            logger.info(f"🎯 Total tags detected: {tag_count}")
                            
                            # Parse tag data and call callback if available
                            if len(frame) >= 6:  # Minimum frame size for tag data
                                try:
                                    # Extract tag data
                                    ant_byte = frame[4]
                                    epc_length = frame[5]
                                    
                                    if len(frame) >= 6 + epc_length + 1:  # Ant + Len + EPC + RSSI
                                        epc_data = frame[6:6+epc_length]
                                        rssi = frame[6+epc_length]
                                        
                                        # Create RFIDTag object
                                        tag = RFIDTag(
                                            epc=''.join(f'{b:02X}' for b in epc_data),
                                            rssi=rssi,
                                            antenna=ant_byte
                                        )
                                        
                                        # Call tag callback if available
                                        if tag_callback:
                                            tag_callback(tag)
                                except Exception as e:
                                    logger.warning(f"⚠️  Error parsing tag data: {e}")
                                    
                        elif re_cmd == 0xEE and status == 0x28:
                            logger.info("💓 Heartbeat received")
                            # Parse heartbeat data and call stats callback if available
                            if len(frame) >= 6 and stats_callback:
                                read_rate = frame[4]
                                total_count = frame[5]
                                stats_callback(read_rate, total_count)
                        elif re_cmd == 0xEE and status == 0x28:
                            logger.info("💓 Heartbeat received")
                            if len(frame) >= 6 and stats_callback:
                                read_rate = frame[4]
                                total_count = frame[5]
                                stats_callback(read_rate, total_count)
            else:
                # Small delay to prevent busy waiting
                time.sleep(0.1)
        
        # Clean up
        logger.info("🧹 Cleaning up inventory session")
        serial_port.reset_input_buffer()
        
        # Print summary
        duration = time.time() - start_time
        logger.info(f"\n📊 Session Summary:")
        logger.info(f"   Total frames processed: {frame_count}")
        logger.info(f"   Total tags detected: {tag_count}")
        logger.info(f"   Total different tags detected: {len(epc_list)}")
        logger.info(f"   Session duration: {duration:.1f} seconds")
        logger.info(f"   Unique tags: {epc_list}")
        return True
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        stop_inventory(serial_port, address)  # Use the new stop function
        
        # Print summary
        duration = time.time() - start_time
        logger.info(f"\n📊 Session Summary:")
        logger.info(f"   Total frames processed: {frame_count}")
        logger.info(f"   Total tags detected: {tag_count}")
        logger.info(f"   Total different tags detected: {len(epc_list)}")
        logger.info(f"   Session duration: {duration:.1f} seconds")
        logger.info(f"   Unique tags: {epc_list}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during inventory: {e}")
        return False

def set_power(serial_port: serial.Serial, power: Union[int, List[int]], address: int = 0x00, preserve_config: bool = True) -> bool:
    """Set RF power for reader antennas.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        power (Union[int, List[int]]): Either a single power value (0-30) for all antennas,
            or a list of power values for specific antennas.
        address (int, optional): Reader address. Defaults to 0x00.
        preserve_config (bool, optional): Whether to preserve configuration during power off. Defaults to True.

    Returns:
        bool: True if power was set successfully, False otherwise.
    """
    try:
        # Validate power values
        if isinstance(power, int):
            if not 0 <= power <= 30:
                logger.error("❌ Power value must be between 0 and 30")
                return False
            power_values = [power]
        else:
            if not all(0 <= p <= 30 for p in power):
                logger.error("❌ All power values must be between 0 and 30")
                return False
            power_values = power
        
        # Determine format based on number of antennas
        num_antennas = len(power_values)
        if num_antennas > 16:
            logger.error("❌ Maximum 16 antennas supported")
            return False
        
        # Create power bytes with preservation bit
        power_data = []
        for p in power_values:
            # Set bit7 based on preserve_config (0 = preserve, 1 = don't preserve)
            power_byte = p & 0x7F  # Clear bit7 first
            if not preserve_config:
                power_byte |= 0x80  # Set bit7 if not preserving config
            power_data.append(power_byte)
        
        # Pad power bytes to match format requirements
        if num_antennas <= 1:
            # Format 1: 1 byte
            cmd_len = 0x05
        elif num_antennas <= 4:
            # Format 2: 4 bytes
            power_data.extend([0] * (4 - num_antennas))
            cmd_len = 0x08
        elif num_antennas <= 8:
            # Format 3: 8 bytes
            power_data.extend([0] * (8 - num_antennas))
            cmd_len = 0x0C
        else:
            # Format 4: 16 bytes
            power_data.extend([0] * (16 - num_antennas))
            cmd_len = 0x14
        
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([cmd_len, address, 0x2F] + power_data)
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Set Power: {' '.join(f'{b:02X}' for b in full_command)}")
        logger.info(f"   Power values: {power_values}")
        logger.info(f"   Preserve config: {'Yes' if preserve_config else 'No'}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 6:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(6)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 6 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        
        if status != 0x00:
            logger.error(f"❌ Set power command failed with status: 0x{status:02X}")
            return False
            
        logger.info("✅ Power set successfully")
        if len(power_values) == 1:
            logger.info(f"   Power set to: {power_values[0]} dBm")
        else:
            logger.info(f"   Power values set: {power_values}")
        logger.info(f"   Config preservation: {'Enabled' if preserve_config else 'Disabled'}")
        logger.info(f"   Number of antennas: {num_antennas}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting power: {e}")
        return False

def set_buzzer(serial_port: serial.Serial, enable: bool = True, address: int = 0x00) -> bool:
    """Enable or disable the buzzer (shared with GPO1 pin).

    Parameters:
        serial_port (serial.Serial): Serial port object.
        enable (bool, optional): Whether to enable the buzzer. Defaults to True.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        bool: True if buzzer was set successfully, False otherwise.
    """
    try:
        # Build command frame: Len Adr Cmd Data[] CRC-16
        beep_en = 0x01 if enable else 0x00  # bit0: 1=enable, 0=disable
        cmd_data = bytes([0x05, address, 0x40, beep_en])
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Set Buzzer: {' '.join(f'{b:02X}' for b in full_command)}")
        logger.info(f"   Buzzer: {'Enabled' if enable else 'Disabled'}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 6:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(6)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 6 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        
        if status != 0x00:
            logger.error(f"❌ Set buzzer command failed with status: 0x{status:02X}")
            return False
            
        logger.info("✅ Buzzer set successfully")
        logger.info(f"   Status: {'Enabled' if enable else 'Disabled'}")
        logger.info("   Note: Buzzer will beep on every successful tag operation")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting buzzer: {e}")
        return False

def get_profile(serial_port: serial.Serial, address: int = 0x00) -> Optional[int]:
    """Get the current reader profile configuration.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        Optional[int]: Current profile number (0-3) or None if command fails.
    """
    try:
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([0x05, address, 0x7F, 0x00])  # Load profile (bit7=0)
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Get Profile: {' '.join(f'{b:02X}' for b in full_command)}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 7:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return None
            
        # Read response
        response = serial_port.read(7)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 7 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return None
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        profile = response[4]
        
        if status != 0x00:
            logger.error(f"❌ Get profile command failed with status: 0x{status:02X}")
            return None
            
        # Extract profile number (bit6~bit0)
        profile_num = profile & 0x3F
        
        # Print profile information
        logger.info("\n📋 Current Profile Configuration:")
        logger.info(f"   Profile Number: {profile_num}")
        
        # Map profile numbers to configurations
        profile_configs = {
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
        
        if profile_num in profile_configs:
            logger.info(f"   Configuration: {profile_configs[profile_num]}")
        else:
            logger.info("   Configuration: Unknown")
            
        return profile_num
        
    except Exception as e:
        logger.error(f"❌ Error getting profile: {e}")
        return None

def set_profile(serial_port: serial.Serial, profile_num: int, save_on_power_down: bool = True, address: int = 0x00) -> bool:
    """Set the reader profile configuration.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        profile_num (int): Profile number to set (0-3).
        save_on_power_down (bool, optional): Whether to save configuration. Defaults to True.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        bool: True if profile was set successfully, False otherwise.
    """
    try:
        # Validate profile number
        if not 0 <= profile_num <= 63:
            logger.error("❌ Profile number must be between 0 and 63")
            return False
            
        # Build profile byte
        # bit7: 1 (modify profile)
        # bit6: 0 (save on power down) or 1 (don't save)
        # bit5~bit0: profile number
        profile_byte = 0x80  # Set bit7 for modify
        if not save_on_power_down:
            profile_byte |= 0x40  # Set bit6 if not saving
        profile_byte |= (profile_num & 0x3F)  # Set profile number in bits 5-0
        
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([0x05, address, 0x7F, profile_byte])
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Set Profile: {' '.join(f'{b:02X}' for b in full_command)}")
        logger.info(f"   Profile Number: {profile_num}")
        logger.info(f"   Save on Power Down: {'Yes' if save_on_power_down else 'No'}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 7:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(7)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 7 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        current_profile = response[4]
        
        if status != 0x00:
            logger.error(f"❌ Set profile command failed with status: 0x{status:02X}")
            return False
            
        logger.info("✅ Profile set successfully")
        logger.info(f"   Current Profile: {current_profile & 0x3F}")
        
        # Map profile numbers to configurations
        profile_configs = {
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
        
        if profile_num in profile_configs:
            logger.info(f"   Configuration: {profile_configs[profile_num]}")
        else:
            logger.info("   Configuration: Custom")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting profile: {e}")
        return False

def set_antenna_config(serial_port: serial.Serial, antenna_states: Dict[int, bool], save_on_power_down: bool = True, address: int = 0x00) -> bool:
    """Configure reader antenna multiplexing.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        antenna_states (Dict[int, bool]): Dictionary mapping antenna numbers (1-4) to their states (True=enable, False=disable).
        save_on_power_down (bool, optional): Whether to save configuration. Defaults to True.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        bool: True if configuration was successful, False otherwise.
    """
    try:
        # Validate antenna numbers and states
        if not antenna_states:
            logger.error("❌ No antenna states provided")
            return False
            
        if not all(1 <= ant <= 4 for ant in antenna_states.keys()):
            logger.error("❌ Antenna numbers must be between 1 and 4")
            return False
            
        # Convert antenna states to bit configuration
        ant_byte = 0
        
        for ant, state in antenna_states.items():
            if state:  # Only set bit if antenna is enabled
                ant_byte |= (1 << (ant - 1))
                    
        # Check if at least one antenna is enabled
        if ant_byte == 0:
            logger.error("❌ At least one antenna must be enabled")
            return False
                
        # Format 1: 1-4 antennas
        cmd_len = 0x05
        # Set bit7 based on save_on_power_down (0=save, 1=don't save)
        if not save_on_power_down:
            ant_byte |= 0x80  # Set bit7 if not saving
            
        cmd_data = bytes([cmd_len, address, 0x3F, ant_byte])
            
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Antenna Config: {' '.join(f'{b:02X}' for b in full_command)}")
        
        # Print antenna states with bit mapping
        enabled = [ant for ant, state in antenna_states.items() if state]
        disabled = [ant for ant, state in antenna_states.items() if not state]
        logger.info(f"   Enabled Antennas: {enabled}")
        logger.info(f"   Disabled Antennas: {disabled}")
        logger.info(f"   Save on Power Down: {'Yes' if save_on_power_down else 'No'}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 6:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(6)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 6 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        
        if status != 0x00:
            logger.error(f"❌ Set antenna config command failed with status: 0x{status:02X}")
            return False
            
        logger.info("✅ Antenna configuration set successfully")
        logger.info(f"   Enabled Antennas: {enabled}")
        logger.info(f"   Disabled Antennas: {disabled}")
        logger.info(f"   Configuration will {'be' if save_on_power_down else 'not be'} saved on power down")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error setting antenna configuration: {e}")
        return False

def enable_antenna(serial_port: serial.Serial, antenna_numbers: List[int], save_on_power_down: bool = True, address: int = 0x00) -> bool:
    """Enable specific antennas while preserving the state of other antennas.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        antenna_numbers (List[int]): List of antenna numbers to enable (1-4).
        save_on_power_down (bool, optional): Whether to save configuration. Defaults to True.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        bool: True if configuration was successful, False otherwise.
    """
    # First get current antenna configuration
    try:
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([0x04, address, 0x21])  # Len=4, Adr, Cmd=0x21
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 18:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(18)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 18 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        status = response[3]
        if status != 0x00:
            logger.error(f"❌ Command failed with status: 0x{status:02X}")
            return False
            
        # Get current antenna configuration
        current_ant = response[12]  # Antenna configuration byte
        
        # Create antenna states dictionary with current configuration
        antenna_states = {}
        for i in range(4):  # For 4 antennas
            ant_num = i + 1
            # Set state based on current configuration
            antenna_states[ant_num] = bool(current_ant & (1 << i))
            
        # Now enable the specified antennas
        for ant in antenna_numbers:
            if 1 <= ant <= 4:  # Validate antenna number
                antenna_states[ant] = True
                
        # Apply the new configuration
        return set_antenna_config(serial_port, antenna_states, save_on_power_down, address)
        
    except Exception as e:
        logger.error(f"❌ Error getting current antenna configuration: {e}")
        return False

def disable_antenna(serial_port: serial.Serial, antenna_numbers: List[int], save_on_power_down: bool = True, address: int = 0x00) -> bool:
    """Disable specific antennas while preserving the state of other antennas.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        antenna_numbers (List[int]): List of antenna numbers to disable (1-4).
        save_on_power_down (bool, optional): Whether to save configuration. Defaults to True.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        bool: True if configuration was successful, False otherwise.
    """
    # First get current antenna configuration
    try:
        # Build command frame: Len Adr Cmd Data[] CRC-16
        cmd_data = bytes([0x04, address, 0x21])  # Len=4, Adr, Cmd=0x21
        
        # Calculate and append CRC
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 18:  # Minimum response length
            logger.error("❌ No response or incomplete response")
            return False
            
        # Read response
        response = serial_port.read(18)  # Fixed length response
        
        # Verify response length and CRC
        if len(response) != 18 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return False
            
        # Parse response
        status = response[3]
        if status != 0x00:
            logger.error(f"❌ Command failed with status: 0x{status:02X}")
            return False
            
        # Get current antenna configuration
        current_ant = response[12]  # Antenna configuration byte
        
        # Create antenna states dictionary with current configuration
        antenna_states = {}
        for i in range(4):  # For 4 antennas
            ant_num = i + 1
            # Set state based on current configuration
            antenna_states[ant_num] = bool(current_ant & (1 << i))
            
        # Now disable the specified antennas
        for ant in antenna_numbers:
            if 1 <= ant <= 4:  # Validate antenna number
                antenna_states[ant] = False
                
        # Check if at least one antenna is still enabled
        if not any(antenna_states.values()):
            logger.error("❌ Cannot disable all antennas - at least one must remain enabled")
            return False
            
        # Apply the new configuration
        return set_antenna_config(serial_port, antenna_states, save_on_power_down, address)
        
    except Exception as e:
        logger.error(f"❌ Error getting current antenna configuration: {e}")
        return False

def antenna_config_menu(serial_port: serial.Serial) -> None:
    """Display and handle antenna configuration menu.

    Parameters:
        serial_port (serial.Serial): Serial port object.
    """
    while True:
        print("\n📡 Antenna Configuration Menu")
        print("1. Enable Antennas")
        print("2. Disable Antennas")
        print("3. Return to Main Menu")
        
        choice = input("\nSelect an option (1-3): ").strip()
        
        if choice == '1':
            print("\nEnter antenna numbers to enable (1-4, comma-separated)")
            print("Example: 1,2")
            try:
                ant_input = input("Antennas: ")
                logger.info(f"Debug - Raw input: '{ant_input}'")
                antennas = [int(x.strip()) for x in ant_input.split(',')]
                logger.info(f"Debug - Parsed antennas: {antennas}")
                if not all(1 <= ant <= 4 for ant in antennas):
                    logger.error(f"❌ Antenna numbers must be between 1 and 4 (got: {antennas})")
                    continue
                    
                save = input("Save configuration when power is down? (y/n): ").lower() == 'y'
                if enable_antenna(serial_port, antennas, save):
                    logger.info("✅ Antennas enabled successfully")
            except ValueError as e:
                logger.error(f"❌ Invalid input. Please enter numbers separated by commas. Error: {e}")
                
        elif choice == '2':
            print("\nEnter antenna numbers to disable (1-4, comma-separated)")
            print("Example: 1,2")
            try:
                ant_input = input("Antennas: ")
                logger.info(f"Debug - Raw input: '{ant_input}'")
                antennas = [int(x.strip()) for x in ant_input.split(',')]
                logger.info(f"Debug - Parsed antennas: {antennas}")
                if not all(1 <= ant <= 4 for ant in antennas):
                    logger.error(f"❌ Antenna numbers must be between 1 and 4 (got: {antennas})")
                    continue
                    
                save = input("Save configuration when power is down? (y/n): ").lower() == 'y'
                if disable_antenna(serial_port, antennas, save):
                    logger.info("✅ Antennas disabled successfully")
            except ValueError as e:
                logger.error(f"❌ Invalid input. Please enter numbers separated by commas. Error: {e}")
                
        elif choice == '3':
            break
            
        else:
            logger.error("❌ Invalid option. Please select 1-3")

def get_power(serial_port: serial.Serial, address: int = 0x00) -> Optional[Dict[int, int]]:
    """Read the output power information of each antenna port.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int, optional): Reader address. Defaults to 0x00.

    Returns:
        Optional[Dict[int, int]]: Dictionary mapping antenna numbers to their power levels in dBm,
            or None if command fails.
    """
    try:
        # Build command frame
        cmd_data = bytes([0x04, address, 0x94])
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        serial_port.write(full_command)
        serial_port.flush()
        
        logger.info(f"📤 Sent Get Antenna Power: {' '.join(f'{b:02X}' for b in full_command)}")
        
        # Wait for response
        time.sleep(0.1)
        if serial_port.in_waiting < 7:  # Minimum response length (5 + 2 for CRC)
            logger.error("❌ No response or incomplete response")
            return None
            
        # Read response
        response = serial_port.read(serial_port.in_waiting)
        
        # Verify response length and CRC
        if len(response) < 7 or not verify_crc16(response):
            logger.error("❌ Invalid response or CRC error")
            return None
            
        # Parse response
        len_byte = response[0]
        resp_address = response[1]
        resp_cmd = response[2]
        status = response[3]
        
        if status != 0x00:
            logger.error(f"❌ Get antenna power command failed with status: 0x{status:02X}")
            return None
            
        # Get power data
        power_data = response[4:-2]  # Exclude CRC
        num_antennas = len(power_data)
        
        # Create dictionary mapping antenna numbers to power levels
        power_levels = {}
        for i in range(num_antennas):
            power = power_data[i]
            if power != 0xFF:  # 0xFF indicates antenna is disabled
                power_levels[i + 1] = power  # Antenna numbers start at 1
        
        # Print power levels
        # print("\n📊 Antenna Power Levels:")
        # for ant, power in power_levels.items():
        #     print(f"   Ant{ant}: {power} dBm")
            
        # Print raw data for debugging
        # print("\n   Raw Response Data:")
        # print(f"      Full Response: {' '.join(f'{b:02X}' for b in response)}")
        # print(f"      Power Data: {' '.join(f'{b:02X}' for b in power_data)}")
        
        return power_levels
        
    except Exception as e:
        logger.error(f"❌ Error getting antenna power: {e}")
        return None

########################
epc_tag_list = []

def parse_epc_id_block(data: bytes, offset: int = 0) -> Tuple[RFIDTag, int]:
    """Parse EPC ID block and return tag info and bytes consumed."""
    if offset >= len(data):
        raise ValueError("Insufficient data for EPC ID block")
    
    data_length_byte = data[offset]
    offset += 1
    
    # Parse data length byte
    has_tid = bool(data_length_byte & 0x80)
    has_phase_freq = bool(data_length_byte & 0x40)
    data_length = data_length_byte & 0x3F
    
    if offset + data_length > len(data):
        raise ValueError("Insufficient data for EPC content")
    
    # Extract EPC/TID data
    epc_tid_data = data[offset:offset + data_length]
    offset += data_length
    
    # Parse EPC and TID
    if has_tid:
        # FastID mode: EPC + 12 bytes TID
        if data_length >= 12:
            epc_data = epc_tid_data[:-12]
            tid_data = epc_tid_data[-12:]
            epc = epc_data.hex().upper()
            tid = tid_data.hex().upper()
        else:
            epc = epc_tid_data.hex().upper()
            tid = None
    else:
        epc = epc_tid_data.hex().upper()
        tid = None
    
    # Parse RSSI
    rssi = None
    if offset < len(data):
        rssi_raw = data[offset]
        rssi = rssi_raw - 256 if rssi_raw > 127 else rssi_raw  # Convert to signed
        offset += 1
    
    # Parse Phase (4 bytes) and Frequency (3 bytes) if enabled
    phase = None
    frequency = None
    if has_phase_freq:
        if offset + 4 <= len(data):
            phase = int.from_bytes(data[offset:offset + 4], 'big')
            offset += 4
        
        if offset + 3 <= len(data):
            frequency = int.from_bytes(data[offset:offset + 3], 'big')
            offset += 3
    
    tag = RFIDTag(
        epc=epc,
        tid=tid,
        rssi=rssi,
        phase=phase,
        frequency=frequency
    )
    
    return tag, offset

def parse_inventory_response(frame: bytes) -> InventoryResult:
    """Parse inventory response frame."""
    if len(frame) < 4:
        raise ValueError("Frame too short")
    
    frame_length = frame[0]
    address = frame[1]
    command = frame[2]
    status = frame[3]
    
    # Status descriptions
    STATUS_DESCRIPTIONS = {
        0x01: "Operation completed successfully",
        0x02: "Inventory timeout, operation aborted",
        0x03: "More data following in next frames", 
        0x04: "Memory full, partial inventory completed",
        0x26: "Statistics data packet",
        0xF8: "Antenna error detected"
    }
    
    # Verify CRC if frame is complete
    if len(frame) >= frame_length + 1:  # +1 for length byte
        if not verify_crc16(frame[:frame_length + 1]):  # Include length byte in CRC calculation
            logger.warning("⚠️  CRC verification failed")
    
    status_desc = STATUS_DESCRIPTIONS.get(
        status, f"Unknown status (0x{status:02X})"
    )
    
    tags = []
    antenna = None
    read_rate = None
    total_count = None
    
    if status == 0x26:  # Statistics packet
        if len(frame) >= 10:
            antenna = frame[4]
            read_rate = int.from_bytes(frame[5:7], 'little')
            total_count = int.from_bytes(frame[7:11], 'little')
    
    elif status in [0x01, 0x02, 0x03, 0x04]:  # Tag data packets
        if len(frame) >= 6:
            antenna = frame[4]
            num_tags = frame[5]
            
            # Parse EPC ID blocks
            offset = 6
            for _ in range(num_tags):
                try:
                    tag, bytes_consumed = parse_epc_id_block(frame, offset)
                    tag.antenna = antenna
                    tags.append(tag)
                    
                    # Add to global EPC list if not already present
                    if tag.epc not in epc_tag_list:
                        epc_tag_list.append(tag.epc)
                    
                    offset = bytes_consumed
                    if offset >= len(frame):
                        break
                except (ValueError, IndexError) as e:
                    logger.warning(f"⚠️  Error parsing tag data: {e}")
                    break
    
    is_complete = status in [0x01, 0x02, 0x04, 0x26]
    
    return InventoryResult(
        status=status,
        status_description=status_desc,
        tags=tags,
        antenna=antenna,
        read_rate=read_rate,
        total_count=total_count,
        is_complete=is_complete
    )

def print_tag_frame_details(frame: bytes):
    """Print detailed frame information (similar to original function)."""
    if len(frame) < 4:
        logger.info(f"❌ Invalid frame (too short): {' '.join(f'{b:02X}' for b in frame)}")
        return
    
    frame_length = frame[0]
    address = frame[1] 
    command = frame[2]
    status = frame[3]
    
    logger.info(f"📦 Frame: {' '.join(f'{b:02X}' for b in frame)}")
    logger.info(f"   Length: {frame_length}, Address: 0x{address:02X}, Command: 0x{command:02X}, Status: 0x{status:02X}")
    
    # Parse the frame
    try:
        result = parse_inventory_response(frame)
        logger.info(f"   {result.status_description}")
        
        if result.tags:
            for i, tag in enumerate(result.tags):
                logger.info(f"   🏷️  Tag {i+1}: {tag}")
        
        if result.read_rate is not None:
            logger.info(f"   📊 Read Rate: {result.read_rate} tags/sec, Total: {result.total_count}")
            
    except Exception as e:
        logger.warning(f"   ⚠️  Parse error: {e}")

def start_tags_inventory(serial_port: serial.Serial, address: int = 0x00, 
                   q_value: int = 4, session: int = 2, target: int = 0, antenna: int = 4, scan_time: int = 20,
                   tag_callback: Optional[Callable[[RFIDTag], None]] = None,
                   stats_callback: Optional[Callable[[int, int], None]] = None) -> bool:
    """Start inventory operation with enhanced parsing.

    Parameters:
        serial_port (serial.Serial): Serial port object.
        address (int, optional): Reader address. Defaults to 0x00.
        q_value (int, optional): Q-value for inventory. Defaults to 4.
        session (int, optional): Session (0-3). Defaults to 0.
        target (int, optional): Target (A-B). Defaults to A.
        antenna (int, optional): Antenna number (1-16). Defaults to 1.
        scan_time (int, optional): Scan time in 100ms units. Defaults to 20 (2s).
        tag_callback (Optional[Callable[[RFIDTag], None]], optional): Callback function for tag data.
        stats_callback (Optional[Callable[[int, int], None]], optional): Callback function for statistics (read_rate, total_count).

    Returns:
        bool: True if operation completed successfully, False otherwise.
    """
    try:
        epc_tag_list.clear()    

        # Clear any pending data and wait for reader to stabilize
        serial_port.reset_input_buffer()
        serial_port.reset_output_buffer()
        time.sleep(0.3)  # Tăng thời gian chờ để reader ổn định
        logger.info("🧹 Input/Output buffer cleared")
        
        # Build and send inventory command
        logger.info("\n--- Sending Inventory command ---")
        
        # Build command data
        q_byte = q_value & 0x0F  # Only use lower 4 bits
        session_byte = session & 0xFF
        
        if target == 0:
            target_byte = 0x00  # Target A
        else: 
            target_byte = 0x01 # Target B

        antenna_byte = 0x80 + (antenna - 1)  # Convert to antenna format
        scantime_byte = scan_time & 0xFF
        
        data = [q_byte, session_byte, target_byte, antenna_byte, scantime_byte]
        
        # Build full command
        cmd_data = bytes([0x09, address, 0x01]) + bytes(data)
        checksum = calculate_crc16(cmd_data)
        full_command = cmd_data + checksum.to_bytes(2, 'little')
        
        # Send command
        command_str = ' '.join(f'{b:02X}' for b in full_command)
        logger.info(f"📤 Sending: {command_str}")
        logger.info(f"   Q-Value: {q_value}, Session: S{session}, Antenna: {antenna}, Scan Time: {scan_time}00ms")
        
        serial_port.write(full_command)
        serial_port.flush()
        
        # Wait a bit for reader to process command
        time.sleep(0.1)
        
        # Initialize data buffer and counters
        buffer = b''
        frame_count = 0
        tag_count = 0
        unique_tag_count = 0
        start_time = time.time()
        last_data_time = time.time()
        
        logger.info("\n--- Listening for responses ---")
        logger.info("Press Ctrl+C to stop...")
        
        while True:
            # Check for available data
            if serial_port.in_waiting > 0:
                # Read available data and add to buffer
                new_data = serial_port.read(serial_port.in_waiting)
                buffer += new_data
                last_data_time = time.time()  # Update last data time
                
                logger.info(f"\n📨 Raw data: {' '.join(f'{b:02X}' for b in new_data)}")
                
                # Parse frames from buffer
                frames, buffer = parse_frames(buffer)
                
                # Process each complete frame
                for frame in frames:
                    frame_count += 1
                    logger.info(f"\n--- Frame #{frame_count} ---")
                    print_tag_frame_details(frame)
                    
                    # Parse and count tags
                    try:
                        result = parse_inventory_response(frame)
                        if result.tags:
                            tag_count += len(result.tags)
                            # Call tag callback for each tag
                            if tag_callback:
                                for tag in result.tags:
                                    tag_callback(tag)
                        
                        # Call stats callback if available
                        if stats_callback and result.read_rate is not None and result.total_count is not None:
                            stats_callback(result.read_rate, result.total_count)
                        
                        # Check if inventory is complete
                        if result.is_complete and result.status == 0x01:
                            logger.info("✅ Inventory completed successfully")
                            # Print summary before returning
                            duration = time.time() - start_time
                            logger.info(f"\n📊 Session Summary:")
                            logger.info(f"   Total frames processed: {frame_count}")
                            logger.info(f"   Total tags detected: {tag_count}")
                            logger.info(f"   Unique tags detected: {len(epc_tag_list)}")
                            logger.info(f"   Session duration: {duration:.1f} seconds")
                            if epc_tag_list:
                                logger.info(f"   EPCs found:")
                                for i, epc in enumerate(epc_tag_list, 1):
                                    logger.info(f"     {i}. {epc}")
                            return True  # Return True when inventory completes successfully
                            
                    except Exception as e:
                        logger.warning(f"⚠️  Error processing frame: {e}")
            else:
                # Check for timeout - if no data for more than scan_time + 1 second, consider it complete
                current_time = time.time()
                if current_time - last_data_time > (scan_time * 0.1) + 1.0:  # scan_time in 100ms units + 1 second buffer
                    logger.info(f"⏰ Timeout reached ({scan_time * 0.1 + 1.0:.1f}s without data), considering inventory complete")
                    duration = time.time() - start_time
                    logger.info(f"\n📊 Session Summary:")
                    logger.info(f"   Total frames processed: {frame_count}")
                    logger.info(f"   Total tags detected: {tag_count}")
                    logger.info(f"   Unique tags detected: {len(epc_tag_list)}")
                    logger.info(f"   Session duration: {duration:.1f} seconds")
                    if epc_tag_list:
                        logger.info(f"   EPCs found:")
                        for i, epc in enumerate(epc_tag_list, 1):
                            logger.info(f"     {i}. {epc}")
                    return True
                
                # Small delay to prevent busy waiting
                time.sleep(0.1)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        
        # Print summary
        duration = time.time() - start_time
        logger.info(f"\n📊 Session Summary:")
        logger.info(f"   Total frames processed: {frame_count}")
        logger.info(f"   Total tags detected: {tag_count}")
        logger.info(f"   Unique tags detected: {len(epc_tag_list)}")
        logger.info(f"   Session duration: {duration:.1f} seconds")
        if epc_tag_list:
            logger.info(f"   EPCs found:")
            for i, epc in enumerate(epc_tag_list, 1):
                logger.info(f"     {i}. {epc}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during inventory: {e}")
        return False

def main() -> None:
    """Main menu function to handle user interactions with the RFID reader."""
    print("🚀 Ex10 RFID Reader Control Program")
    print("==================================")
    
    # Connect to reader
    port = input("Enter serial port (default: /dev/cu.usbserial-10): ").strip() or '/dev/cu.usbserial-10'
    reader = connect_reader(port)
    
    if not reader:
        print("❌ Failed to connect to reader. Exiting...")
        return
        
    try:
        while True:
            print("\n📋 Available Commands:")
            print("1. Get Reader Information")
            print("2. Start Inventory (Target A)")
            print("3. Start Inventory (Target B)")
            print("4. Stop Inventory")
            print("5. Set RF Power")
            print("6. Set Buzzer")
            print("7. Profile Management")
            print("8. Antenna Configuration")
            print("9. Get Antenna Power")
            print("10. Tags inventory")
            print("11. Exit")
            
            choice = input("\nEnter your choice (1-10): ").strip()
            
            if choice == "1":
                get_reader_info(reader)
                
            elif choice == "2":
                # Define callback functions for Target A inventory
                def on_tag_detected(tag: RFIDTag):
                    print(f"\n🏷️  New Tag Detected (Target A):")
                    print(f"   EPC: {tag.epc}")
                    if tag.rssi is not None:
                        print(f"   RSSI: {tag.rssi} dBm")
                    if tag.antenna is not None:
                        print(f"   Antenna: {tag.antenna}")
                
                def on_stats_update(read_rate: int, total_count: int):
                    print(f"\n📊 Stats Update (Target A):")
                    print(f"   Read Rate: {read_rate} tags/sec")
                    print(f"   Total Count: {total_count}")
                
                start_inventory(
                    serial_port=reader,
                    address=0x00,
                    target=0,
                    tag_callback=on_tag_detected,
                    stats_callback=on_stats_update
                )
                
            elif choice == "3":
                # Define callback functions for Target B inventory
                def on_tag_detected(tag: RFIDTag):
                    print(f"\n🏷️  New Tag Detected (Target B):")
                    print(f"   EPC: {tag.epc}")
                    if tag.rssi is not None:
                        print(f"   RSSI: {tag.rssi} dBm")
                    if tag.antenna is not None:
                        print(f"   Antenna: {tag.antenna}")
                
                def on_stats_update(read_rate: int, total_count: int):
                    print(f"\n📊 Stats Update (Target B):")
                    print(f"   Read Rate: {read_rate} tags/sec")
                    print(f"   Total Count: {total_count}")
                
                start_inventory(
                    serial_port=reader,
                    address=0x00,
                    target=1,
                    tag_callback=on_tag_detected,
                    stats_callback=on_stats_update
                )
                
            elif choice == "4":
                stop_inventory(reader)
                
            elif choice == "5":
                print("\nSet RF Power Options:")
                print("1. Set single power value for all antennas")
                print("2. Set different power values for multiple antennas")
                power_choice = input("Enter choice (1-2): ").strip()
                
                preserve = input("Preserve configuration during power off? (y/n, default: y): ").strip().lower() != 'n'
                
                if power_choice == "1":
                    try:
                        power = int(input("Enter power value (0-30): "))
                        set_power(reader, power, preserve_config=preserve)
                    except ValueError:
                        print("❌ Invalid power value")
                elif power_choice == "2":
                    try:
                        power_str = input("Enter power values (comma-separated, 0-30): ")
                        powers = [int(p.strip()) for p in power_str.split(",")]
                        set_power(reader, powers, preserve_config=preserve)
                    except ValueError:
                        print("❌ Invalid power values")
                else:
                    print("❌ Invalid choice")
                    
            elif choice == "6":
                print("\nSet Buzzer Options:")
                print("1. Enable buzzer")
                print("2. Disable buzzer")
                buzzer_choice = input("Enter choice (1-2): ").strip()
                
                if buzzer_choice == "1":
                    set_buzzer(reader, enable=True)
                elif buzzer_choice == "2":
                    set_buzzer(reader, enable=False)
                else:
                    print("❌ Invalid choice")
                    
            elif choice == "7":
                print("\nProfile Management Options:")
                print("1. Get Current Profile")
                print("2. Set Profile")
                profile_choice = input("Enter choice (1-2): ").strip()
                
                if profile_choice == "1":
                    get_profile(reader)
                elif profile_choice == "2":
                    print("\nAvailable Profiles:")
                    print("11: 640kHz, FM0, Tari 7.5μs")
                    print("1:  640kHz, Miller2, Tari 7.5μs")
                    print("15: 640kHz, Miller4, Tari 7.5μs")
                    print("12: 320kHz, Miller2, Tari 15μs")
                    print("3:  320kHz, Miller2, Tari 20μs")
                    print("5:  320kHz, Miller4, Tari 20μs")
                    print("7:  250kHz, Miller4, Tari 20μs")
                    print("13: 160kHz, Miller8, Tari 20μs")
                    print("50: 640kHz, FM0, Tari 6.25μs")
                    print("51: 640kHz, Miller2, Tari 6.25μs")
                    print("52: 426kHz, FM0, Tari 15μs")
                    print("53: 640kHz, Miller4, Tari 7.5μs")
                    
                    try:
                        profile = int(input("\nEnter profile number: "))
                        save = input("Save configuration when power is down? (y/n, default: y): ").strip().lower() != 'n'
                        set_profile(reader, profile, save_on_power_down=save)
                    except ValueError:
                        print("❌ Invalid profile number")
                else:
                    print("❌ Invalid choice")
                    
            elif choice == "8":
                antenna_config_menu(reader)
                
            elif choice == "9":
                if reader is None:
                    print("❌ Please connect to a reader first")
                    continue
                    
                power_levels = get_power(reader)
                if power_levels:
                    logger.info("\n📊 Current Antenna Power Levels:")
                    for ant, power in power_levels.items():
                        logger.info(f"   Ant{ant}: {power} dBm")
                    
            elif choice == "10": 
                print("\n📋 Tags Inventory Options:")
                print("1. Use default settings")
                print("2. Customize settings")
                inventory_choice = input("Enter choice (1-2): ").strip()
                
                # Define callback functions
                def on_tag_detected(tag: RFIDTag):
                    print(f"\n🏷️  New Tag Detected:")
                    print(f"   EPC: {tag.epc}")
                    if tag.rssi is not None:
                        print(f"   RSSI: {tag.rssi} dBm")
                    if tag.antenna is not None:
                        print(f"   Antenna: {tag.antenna}")
                
                def on_stats_update(read_rate: int, total_count: int):
                    print(f"\n📊 Stats Update:")
                    print(f"   Read Rate: {read_rate} tags/sec")
                    print(f"   Total Count: {total_count}")
                
                # Set default parameters
                q_value = 4
                session = 0
                antenna = 1
                scan_time = 10
                
                if inventory_choice == "2":
                    try:
                        # Get custom values with defaults shown
                        q_value = int(input("Enter Q-value (0-15, default: 4): ") or "4")
                        session = int(input("Enter session (0-3, default: 0): ") or "0")
                        antenna = int(input("Enter antenna number (1-4, default: 1): ") or "1")
                        scan_time = int(input("Enter scan time in 100ms units (1-255, default: 10): ") or "10")
                        
                        # Validate inputs
                        if not (0 <= q_value <= 15):
                            print("❌ Invalid Q-value. Using default (4)")
                            q_value = 4
                        if not (0 <= session <= 3):
                            print("❌ Invalid session. Using default (0)")
                            session = 0
                        if not (1 <= antenna <= 4):
                            print("❌ Invalid antenna. Using default (1)")
                            antenna = 1
                        if not (1 <= scan_time <= 255):
                            print("❌ Invalid scan time. Using default (10)")
                            scan_time = 10
                    except ValueError:
                        print("❌ Invalid input. Using default values")
                
                print(f"\n🔄 Starting continuous inventory loop...")
                print(f"   Q-value: {q_value}, Session: S{session}, Antenna: {antenna}, Scan Time: {scan_time}00ms")
                print("   Press Ctrl+C to stop the loop and return to main menu")
                
                try:
                    while True:
                        print(f"\n--- Starting new inventory cycle at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                        start_tags_inventory(
                            serial_port=reader,
                            address=0x00,
                            q_value=q_value,
                            session=session,
                            antenna=antenna,
                            scan_time=scan_time,
                            tag_callback=on_tag_detected,
                            stats_callback=on_stats_update
                        )
                        print(f"\n--- Inventory cycle completed at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
                        print("🔄 Starting next cycle immediately...")
                        # Không có delay giữa các cycle để quét nhanh nhất có thể
                        
                except KeyboardInterrupt:
                    print("\n⚠️  Continuous inventory loop stopped by user")
                    print("Returning to main menu...")
                    
            elif choice == "11":
                print("\n👋 Goodbye!")
                break
                
            else:
                print("❌ Invalid choice. Please try again.")
                
    except KeyboardInterrupt:
        print("\n⚠️  Program interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if reader and reader.is_open:
            reader.close()
            print("🔌 Serial connection closed")

if __name__ == "__main__":
    # print("Ex10 Series RFID Reader Protocol Parser")
    # print("=======================================")
    # print()
    # print("Choose an option:")
    # print("1. Connect to real Ex10 RFID reader")
    # print("2. Test with sample data")
    
    try:
        main()
        # port = input("Enter serial port (default: /dev/cu.usbserial-10): ").strip() or '/dev/cu.usbserial-10'
        # reader = connect_reader(port)
        # tags_inventory(reader)
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")