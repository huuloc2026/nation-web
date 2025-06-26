from nation import NationReader
import time
import json
import threading
import subprocess

def beep():
    try:
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "beep.mp3"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"⚠️ Beep error: {e}")
        
def on_tag_callback(tag: dict):
    
    payload = {
        "epc": tag.get("epc"),
        "rssi": tag.get("rssi"),
        "antenna_id": tag.get("antenna_id"),
        "status": "tag_detected"
    }
    if reader.set_beeper(2):
        threading.Thread(target=beep, daemon=True).start()
    print(json.dumps(payload))
    return json.dumps(payload)

def on_end_callback(reason):
    reasons = {
        0: "Kết thúc do đọc 1 lần",
        1: "Dừng bởi lệnh STOP",
        2: "Lỗi phần cứng"
    }
    print(f"📴 Inventory kết thúc. Lý do: {reasons.get(reason, 'Không rõ')}")
    
    
def main():
    global reader
    port = "/dev/ttyUSB0"
    baud = 115200
    reader = NationReader(port, baud)
    

    reader.open()
    print("🔧 Connecting and initializing reader...")
    if not reader.Connect_Reader_And_Initialize():
        print("❌ Initialization failed.")
        return
    # reader.configure_baseband(speed=255, q_value=1, session=2, inventory_flag=0) 
    
    
    # # infor= reader.query_baseband_profile()
    # # print("📡 Baseband profile queried successfully.",infor)
    
    

    # # session = reader.get_session()

    
    

    
    # print("\n📤 Sending all antenna configuration to reader...")
    # reader.send_all_ant_config()

    
    # # print("✅ Danh sách anten đang bật:", reader.get_enabled_ants())
    
    # info = reader.Query_Reader_Information()
    # print("📡 Reader Info:")
    # for k, v in info.items():
    #     print(f"  {k}: {v}")


    setPower = {
        1:30, 
        2:1,
        3:1,
        4:1
    }
    reader.configure_reader_power(setPower, persistence=True)
    # powers = reader.query_reader_power()
    # for ant in range(1, 5):
    #     val = powers.get(ant)
    #     if val is not None:
    #         print(f"  🔧 Antenna {ant}: {val} dBm")
    #     else:
    #         print(f"  ⚠️ Antenna {ant}: N/A")
    
    # # profilemock = reader.select_profile(0)
    # # print("📊 Chọn profile:", profilemock)

        # === TEST: Write EPC Tag ===
    print("\n✍️ Testing write_epc_tag...")
    # Example EPC data (must be even length, word-aligned)
    new_epc = bytes.fromhex("3000112233445566")  # adjust as needed
    write_result = reader.write_epc_tag(
        antenna_mask=0x00000001,
        start_word_addr=2,
        epc_data=new_epc,
        access_password=0,
        match_area=None,
        match_addr=None,
        match_bitlen=None,
        match_data=None
    )
    print("Write EPC result:", write_result)
    try:
        print("▶️ Bắt đầu đọc tag (ấn Ctrl+C để dừng)...")
    
        # reader.start_inventory(on_tag=on_tag_callback, on_inventory_end=on_end_callback)
        

        reader.start_inventory_with_mode(mode=0,callback=on_tag_callback)
       
   
        time.sleep(10000)
        # infor= reader.query_baseband_profile()
        # print("📡 Baseband profile queried successfully.",infor)
        
    except KeyboardInterrupt:
        reader.stop_inventory()
        
        
    finally:
        success = reader.stop_inventory()
        
        if success:
            print("✅ Inventory đã dừng thành công")
        else:
            print("❌ Không thể dừng reader")
        reader.close()
        print("🔌 Đóng kết nối UART")


if __name__ == "__main__":
    main()
