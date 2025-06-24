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

## Cài đặt

1. Cài đặt dependencies:
```bash
pip install -r requirements.txt
```

2. Chạy ứng dụng:
```bash
python app.py
```

3. Truy cập web interface tại: `http://localhost:5000`

## Cấu hình

Chỉnh sửa file `config.py` để thay đổi cấu hình mặc định:

```python
class Config:
    DEFAULT_PORT = 'COM3'  # Windows
    # DEFAULT_PORT = '/dev/ttyUSB0'  # Linux
    DEFAULT_BAUDRATE = 57600
    DEFAULT_ADDRESS = 0x00
    MAX_POWER = 30
    MIN_POWER = 0
    MAX_ANTENNAS = 4
    MAX_TAGS_DISPLAY = 100
```

## API Endpoints

### Kết nối
- `POST /api/connect` - Kết nối reader
- `POST /api/disconnect` - Ngắt kết nối reader

### Inventory
- `POST /api/start_inventory` - Bắt đầu inventory (Target A/B)
- `POST /api/stop_inventory` - Dừng inventory
- `POST /api/tags_inventory` - Bắt đầu tags inventory với cấu hình tùy chỉnh
- `POST /api/stop_tags_inventory` - Dừng tags inventory

### Cấu hình
- `GET /api/reader_info` - Lấy thông tin reader
- `POST /api/set_power` - Thiết lập RF power
- `POST /api/set_buzzer` - Bật/tắt buzzer
- `GET /api/get_profile` - Lấy profile hiện tại
- `POST /api/set_profile` - Thiết lập profile
- `POST /api/enable_antennas` - Bật antennas
- `POST /api/disable_antennas` - Tắt antennas
- `GET /api/get_antenna_power` - Lấy công suất antennas

### Dữ liệu
- `GET /api/get_tags` - Lấy danh sách tags đã phát hiện
- `GET /api/config` - Lấy cấu hình
- `GET /api/debug` - Thông tin debug

### Reset
- `POST /api/reset_reader` - Reset reader hoàn toàn

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

### Cách sử dụng khi gặp vấn đề

1. **Khi chuyển session**:
   - Dừng inventory hiện tại
   - Đợi 1-2 giây
   - Bắt đầu inventory với session mới

2. **Khi gặp CRC error hoặc không phản hồi**:
   - Gọi API `/api/reset_reader`
   - Đợi reset hoàn tất
   - Thử lại inventory

3. **Khi thread không dừng**:
   - Gọi API `/api/stop_inventory` hoặc `/api/stop_tags_inventory`
   - Đợi tối đa 3 giây
   - Nếu vẫn không dừng, gọi `/api/reset_reader`

### Log monitoring

Theo dõi log để phát hiện vấn đề:
- `Inventory thread không dừng trong thời gian chờ` - Thread timeout
- `❌ Invalid response or CRC error` - CRC error
- `❌ No response or incomplete response` - Reader không phản hồi

## Troubleshooting

### Reader không kết nối
- Kiểm tra port và baudrate
- Đảm bảo driver đã được cài đặt
- Thử port khác

### Inventory không hoạt động
- Kiểm tra kết nối
- Reset reader
- Kiểm tra antenna và power settings

### WebSocket không hoạt động
- Kiểm tra firewall
- Đảm bảo client hỗ trợ WebSocket
- Kiểm tra console browser

## Cấu trúc project

```
zk-web-app/
├── app.py              # Flask application
├── zk.py               # RFID reader SDK
├── config.py           # Configuration
├── requirements.txt    # Dependencies
├── templates/
│   └── index.html     # Web interface
└── README.md          # Documentation
```

## License

MIT License 