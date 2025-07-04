# from nation import NationReader
# import time
# import json
# import threading
# import subprocess

# # def beep():
# #     try:
# #         subprocess.Popen(
# #             ["ffplay", "-nodisp", "-autoexit", "beep.mp3"],
# #             stdout=subprocess.DEVNULL,
# #             stderr=subprocess.DEVNULL
# #         )
# #     except Exception as e:
# #         print(f"⚠️ Beep error: {e}")
        
    

# # def on_tag_callback(tag: dict):
# #     nonlocal tag_count, unique_epcs
# #     epc = tag.get("epc")
# #     tag_count += 1
# #     if epc:
# #         unique_epcs.add(epc.upper())
# #     payload = {
# #         "epc": tag.get("epc"),
# #         "rssi": tag.get("rssi"),
# #         "antenna_id": tag.get("antenna_id"),
# #         "status": "tag_detected",
# #         "total_detected": tag_count,
# #         "unique_tags": len(unique_epcs)
        
# #     }
    
# #     # if reader.set_beeper(2):
# #         # threading.Thread(target=beep, daemon=True).start()
# #     print(json.dumps(payload))
# #     return json.dumps(payload)

# def on_end_callback(reason):
#     reasons = {
#         0: "Kết thúc do đọc 1 lần",
#         1: "Dừng bởi lệnh STOP",
#         2: "Lỗi phần cứng"
#     }
#     print(f"📴 Inventory kết thúc. Lý do: {reasons.get(reason, 'Không rõ')}")
    

# def write_epc_list(reader, epc_list, antenna_id=1, access_password=None, timeout=1):
#     for epc in epc_list:
#         result = reader.write_epc_tag_auto(
#             new_epc_hex=epc,
#             match_epc_hex=None,
#             antenna_id=antenna_id,
#             access_password=access_password,
#             timeout=timeout
#         )
#         print("📝 Auto Write EPC Result:")
#         for k, v in result.items():
#             print(f"  {k}: {v}")
#         time.sleep(2)

# def main():
#     global reader
#     port = "/dev/ttyUSB0"
#     baud = 115200
#     reader = NationReader(port, baud)
#     tag_count = 0
#     unique_epcs = set()

#     reader.open()
#     print("🔧 Connecting and initializing reader...")
#     if not reader.Connect_Reader_And_Initialize():
#         print("❌ Initialization failed.")
#         return
#     def on_tag_callback(tag: dict):
#         nonlocal tag_count, unique_epcs
#         epc = tag.get("epc")
#         tag_count += 1
#         if epc:
#             unique_epcs.add(epc.upper())
#         payload = {
#             "epc": tag.get("epc"),
#             "rssi": tag.get("rssi"),
#             "antenna_id": tag.get("antenna_id"),
#             "status": "tag_detected",
#             "total_detected": tag_count,
#             "unique_tags": len(unique_epcs)
            
#         }
        
#         # if reader.set_beeper(2):
#             # threading.Thread(target=beep, daemon=True).start()
#         print(json.dumps(payload))
#         return json.dumps(payload)
#     # reader.configure_baseband(speed=0, q_value=1, session=0, inventory_flag=0) 
    
     
#     # # # infor= reader.query_baseband_profile()
#     # # # print("📡 Baseband profile queried successfully.",infor)
    
    

#     # # # session = reader.get_session()

    
    
#     # # Send config for Main Antenna 1 only


#     # #02/07/2025
#     # # Auto write EPC (auto PC bits, word length)
#     # # Example usage:
#     # # target_tag = "ABCD55551100"      # The EPC you want to find and overwrite
#     # # new_epc = "ABCD0284"             # The new EPC to write (hex string)
#     # # reader.write_epc_to_target_auto(target_tag, new_epc)

    
#     # # # Query and print config
#     # # config = reader.query_ext_ant_config()
#     # # print("Queried antenna config:", config)

#     # # enabled_ports = reader.get_enabled_ants()
#     # # print("Enabled global antenna ports:", enabled_ports)


    
#     # # # print("✅ Danh sách anten đang bật:", reader.get_enabled_ants())
    
#     # # info = reader.Query_Reader_Information()
#     # # print("📡 Reader Info:")
#     # # for k, v in info.items():
#     # #     print(f"  {k}: {v}")
#     # # config = reader.query_ext_ant_config()
#     # # print("Queried extended antenna config:", config)
#     # # return
#     # # config = reader.query_ext_ant_config()
#     # # print("Queried antenna config:", config)
    

    
#     # # print("Parsed antenna power response:", reader.antenna_power_list)
    


#     # #PRINT HEX mask
  
#     # # reader.query_enabled_ant_mask()


    
    
#     # # enable = reader.enable_ant(ant_id=1, save=True)
#     # # if enable:
#     # #     print("✅ Antenna 1 enabled successfully")  

#     # # Output: [(1, 12)]


#     # setPower = {
#     #     1:10, 
#     #     2:0,
#     #     3:1,
#     #     4:1
#     # }
#     # reader.configure_reader_power(setPower, persistence=True)
#     # powers = reader.query_reader_power()
#     # for ant in range(1, 5):
#     #     val = powers.get(ant)
#     #     if val is not None:
#     #         print(f"  🔧 Antenna {ant}: {val} dBm")
#     #     else:
#     #         print(f"  ⚠️ Antenna {ant}: N/A")
    
#     # # profilemock = reader.select_profile(0)
#     # # print("📊 Chọn profile:", profilemock)

#     # #KhUONG
#     result = reader.write_epc_tag_auto(
#         new_epc_hex="ABCD1111",       # Auto-detect PC, word length, etc.
#         match_epc_hex=None,           # Optional: set to EPC of target tag if needed
#         antenna_id=1,                 # Or 2, 3, 4...
#         access_password=None,         # Optional: default None
#         timeout=1
#     )
#     print("📝 Auto Write EPC Result:")
#     for k, v in result.items():
#         print(f"  {k}: {v}")
#     time.sleep(2)

#     # Example usage: batch write EPCs
#     epc_batch = ["ABCD1111", "ABCD2222", "ABCD3333"]  # Replace with your EPC list
#     write_epc_list(reader, epc_batch, antenna_id=1, access_password=None, timeout=1)

    
#     try:
       


#         # result = reader.query_rf_band()
#         # if result:
#         #     print(f"➡️ Reader is using band: {result['band_name']} (Code={result['band_code']})")

#         # # ✅ Step 4: Try setting new band
#         # # print("\n⚙️ Setting RF Band to FCC 902–928 MHz (Code 3)...")
#         # reader.set_rf_band(band_code=3, persist=True)
#         # result = reader.query_rf_band()
#         # if result:
#         #     print(f"Reader WITH NEW Band: {result['band_name']} (Code={result['band_code']})")    
        
        
        
#         reader.start_inventory_with_mode(antenna_mask=[1],callback=on_tag_callback)
       
#         time.sleep(10)
#         # infor= reader.query_baseband_profile()
#         # print("📡 Baseband profile queried successfully.",infor)
  
        
#     except KeyboardInterrupt:
#         reader.stop_inventory()
        
        
#     finally:
#         success = reader.stop_inventory()
        
#         if success:
#             print("✅ Inventory đã dừng thành công")
#         else:
#             print("❌ Không thể dừng reader")
#         reader.close()
#         print("🔌 Đóng kết nối UART")


# if __name__ == "__main__":
#     main()




# -*- coding: 2 reader -*-


from nation import NationReader
import time, json, threading

# ---------- Worker function for each UART port ----------
def run_reader(port: str, baud: int = 115200):
    tag_count = 0
    unique_epcs = set()

    reader = NationReader(port, baud)
    reader.open()
    print(f"🔧[{port}] Connecting & initializing...")
    if not reader.Connect_Reader_And_Initialize():
        print(f"❌[{port}] Init failed")
        return

    # --- Tag callback scoped to this reader ---
    def on_tag_callback(tag: dict):
        nonlocal tag_count, unique_epcs
        epc = tag.get("epc")
        tag_count += 1
        if epc:
            unique_epcs.add(epc.upper())
        payload = {
            "epc": epc,
            "rssi": tag.get("rssi"),
            "antenna_id": tag.get("antenna_id"),
            "port": port,
            "total_detected": tag_count,
            "unique_tags": len(unique_epcs),
            "status": "tag_detected",
        }
        print(json.dumps(payload))
        return json.dumps(payload)

    # Example configuration (tuỳ chỉnh lại nếu cần)
    reader.configure_baseband(speed=0, q_value=1, session=0, inventory_flag=0)
    reader.configure_reader_power({1: 10, 2: 0, 3: 0, 4: 0}, persistence=True)

    try:
        reader.start_inventory_with_mode(antenna_mask=[1,2,3,4], callback=on_tag_callback)
        while True:                
            time.sleep(1)
    except Exception as e:
        print(f"⚠️[{port}] Error: {e}")
    finally:
        reader.stop_inventory()
        reader.close()
        print(f"🔌[{port}] UART closed")

# ---------- Entry point ----------
if __name__ == "__main__":
    ports = ["/dev/ttyUSB0"] 
    threads = []

    for p in ports:
        t = threading.Thread(target=run_reader, args=(p,), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:  # Giữ chương trình chính sống để threads chạy
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⛔️  Stopping all readers ...")
        # Threads are daemons → sẽ tự kết thúc khi chương trình chính thoát
