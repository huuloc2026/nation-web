from nation import NationReader
import time
import json
import threading
import subprocess

# def beep():
#     try:
#         subprocess.Popen(
#             ["ffplay", "-nodisp", "-autoexit", "beep.mp3"],
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL
#         )
#     except Exception as e:
#         print(f"⚠️ Beep error: {e}")
        
def on_tag_callback(tag: dict):
    
    payload = {
        "epc": tag.get("epc"),
        "rssi": tag.get("rssi"),
        "antenna_id": tag.get("antenna_id"),
        "status": "tag_detected"
    }
    # if reader.set_beeper(2):
        # threading.Thread(target=beep, daemon=True).start()
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
    port = "/dev/ttyUSB1"
    baud = 115200
    reader = NationReader(port, baud)
    

    reader.open()
    print("🔧 Connecting and initializing reader...")
    if not reader.Connect_Reader_And_Initialize():
        print("❌ Initialization failed.")
        return

    # reader.configure_baseband(speed=0, q_value=1, session=2, inventory_flag=0) 
    
    
    # # infor= reader.query_baseband_profile()
    # # print("📡 Baseband profile queried successfully.",infor)
    
    

    # # session = reader.get_session()

    
    

    
    # Send config for Main Antenna 1 only
    # reader.send_all_ant_config()

    # # Query and print config
    # config = reader.query_ext_ant_config()
    # print("Queried antenna config:", config)

    # enabled_ports = reader.get_enabled_ants()
    # print("Enabled global antenna ports:", enabled_ports)


    
    # # print("✅ Danh sách anten đang bật:", reader.get_enabled_ants())
    
    # info = reader.Query_Reader_Information()
    # print("📡 Reader Info:")
    # for k, v in info.items():
    #     print(f"  {k}: {v}")
    # config = reader.query_ext_ant_config()
    # print("Queried extended antenna config:", config)
    # return
    # config = reader.query_ext_ant_config()
    # print("Queried antenna config:", config)
    # enabled_ports = reader.get_enabled_ants()
    # reader.disable_ant(2)
    # reader.disable_ant(3)

    # reader.disable_ant(4)
    # enabled_ports = reader.get_enabled_ants()
    # print("Enabled global antenna ports:", enabled_ports)

    # setPower = {
    #     1:22, 
    #     2:5,
    #     3:1,
    #     4:1
    # }
    # reader.configure_reader_power(setPower, persistence=True)
    # powers = reader.query_reader_power()
    # for ant in range(1, 5):
    #     val = powers.get(ant)
    #     if val is not None:
    #         print(f"  🔧 Antenna {ant}: {val} dBm")
    #     else:
    #         print(f"  ⚠️ Antenna {ant}: N/A")
    
    # # profilemock = reader.select_profile(0)
    # # print("📊 Chọn profile:", profilemock)


    # result = reader.write_epc_tag_auto(
    #     new_epc_hex="ABCD0284",       # Auto-detect PC, word length, etc.
    #     match_epc_hex=None,           # Optional: set to EPC of target tag if needed
    #     antenna_id=1,                 # Or 2, 3, 4...
    #     access_password=None,         # Optional: default None
    #     timeout=2.0
    # )
    # print("📝 Auto Write EPC Result:")
    # for k, v in result.items():
    #     print(f"  {k}: {v}")



    # # # # --- Test write_epc_tag here ---
    # epc_to_write = "ABCD0284"  # Example EPC value (hex string)
    # match_epc = None   # Or e.g. "ABCD0059" to match a specific tag
    # access_pwd = None          # Or e.g. 0x12345678 if your tag requires a password

    # print("📝 Writing EPC tag...")
    # result = reader.write_epc_tag(
    #     epc_hex=epc_to_write,
    #     antenna_id=1,
    #     match_epc_hex=match_epc,
    #     access_password=access_pwd,
    #     start_word=2,          # Default for EPC area
    #     timeout=2.0
    # )
    # print("Write EPC result:", result)
    
    
    
    # # Example usage:
    # target_tag = "ABCD55551100"      # The EPC you want to find and overwrite
    # new_epc = "ABCD0284"          # The new EPC to write (hex string)
    # reader.write_to_target_tag(target_tag, new_epc)  
    
    try:
       

        
        
        # print("▶️ Bắt đầu đọc tag (ấn Ctrl+C để dừng)...")
    
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
