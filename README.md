# RFID Web Control Panel

Ứng dụng web để điều khiển RFID reader Ex10 series với giao diện web và WebSocket real-time.

## Tính năng

- **Kết nối RFID Reader**: Hỗ trợ kết nối qua serial port
- **Inventory Operations**: 
  - Start/Stop inventory với Target A/B
  - Tags inventory với cấu hình tùy chỉnh (Q-value, Session, Antenna, Scan time)
  - Real-time tag detection qua WebSocket
- **Reader Configuration**:
  - Thiết lập RF power
  - Bật/tắt buzzer
  - Quản lý profile
  - Cấu hình antenna
- **Real-time Monitoring**: WebSocket để hiển thị tags và stats real-time
- **Batch EPC Write**: Ghi nhiều EPC vào tag qua giao diện hoặc upload file (xlsx/csv)
- **Beep on Write Success**: Khi ghi EPC thành công, trình duyệt sẽ phát âm thanh beep (`public/beep.mp3`)

## Cài đặt

1. Cài đặt dependencies backend:
   ```bash
   pip install -r requirements.txt
   ```

2. Chạy backend Flask app:
   ```bash
   python app.py
   ```

3. Cài đặt dependencies frontend:
   ```bash
   cd front-end
   npm install
   ```

4. Chạy frontend (Vite):
   ```bash
   npm run dev
   ```
   Truy cập web UI tại: [http://localhost:5173](http://localhost:5173)

## API Endpoints

### Kết nối
- `POST /api/connect` - Kết nối reader
- `POST /api/disconnect` - Ngắt kết nối reader

### Inventory
- `POST /api/start_inventory` - Bắt đầu inventory (Target A/B)
- `POST /api/stop_inventory` - Dừng inventory

### Cấu hình
- `GET /api/reader_info` - Lấy thông tin reader
- `POST /api/set_power` - Thiết lập RF power
- `POST /api/enable_antennas` - Bật antennas
- `POST /api/disable_antennas` - Tắt antennas
- `GET /api/get_antenna_power` - Lấy công suất antennas

### EPC Write
- `POST /api/write_epc_tag_auto` - Ghi EPC vào tag (auto PC bits, word length)
- `POST /api/check_write_epc` - Kiểm tra khả năng ghi EPC

## WebSocket Events

### Client → Server
- `connect` - Kết nối WebSocket
- `disconnect` - Ngắt kết nối WebSocket

### Server → Client
- `tag_detected` - Tag mới được phát hiện
- `stats_update` - Cập nhật thống kê
- `status` - Trạng thái kết nối

## Xử lý vấn đề Session Switching

### Vấn đề thường gặp
Khi chuyển đổi giữa các session (ví dụ: từ session 2 về session 0), có thể gặp các vấn đề:
- Reader không phản hồi
- CRC error
- Delay khi gọi lệnh đọc
- Thread không dừng trong thời gian chờ

### Giải pháp đã được cải thiện

1. **Cải thiện hàm stop_inventory**:
   - Gửi lệnh stop nhiều lần để đảm bảo reader nhận được
   - Tăng thời gian chờ thread dừng (3 giây)
   - Clear cả input và output buffer
   - Force stop nếu thread không dừng

2. **Cải thiện hàm start_inventory**:
   - Tăng thời gian chờ giữa các lần start (1 giây)
   - Clear buffer trước khi start
   - Thêm delay để reader ổn định

3. **Cải thiện hàm start_tags_inventory**:
   - Thêm timeout để tránh bị treo
   - Clear cả input và output buffer
   - Tăng thời gian chờ để reader ổn định
   - Thêm delay sau khi gửi lệnh

4. **API Reset Reader**:
   - Reset hoàn toàn reader khi cần thiết
   - Clear tất cả buffers
   - Gửi lệnh stop nhiều lần
   - Đợi reader ổn định

## Cấu trúc project

```
nation-web/
├── app.py              # Flask application
├── nation.py           # RFID reader SDK
├── config.py           # Configuration
├── requirements.txt    # Dependencies
├── front-end/
│   ├── src/
│   │   ├── App.tsx         # Web interface (React)
│   │   └── ...             # Other frontend files
│   └── public/
│       └── beep.mp3        # Beep sound for write success
└── README.md           # Documentation
```

## Beep on EPC Write Success

- Khi ghi EPC thành công (qua giao diện hoặc upload file), trình duyệt sẽ phát âm thanh beep (`public/beep.mp3`).
- Đảm bảo file `beep.mp3` tồn tại trong thư mục `front-end/public/`.

## License

MIT License