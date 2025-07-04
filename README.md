# RFID Web Control Panel

A web application to control Ex10 series RFID readers with a web interface and real-time WebSocket support.

## Features

- **RFID Reader Connection**: Supports connection via serial port
- **Inventory Operations**: 
  - Start/Stop inventory with Target A/B
  - Tags inventory with customizable configuration (Q-value, Session, Antenna, Scan time)
  - Real-time tag detection via WebSocket
- **Reader Configuration**:
  - Set RF power
  - Enable/disable buzzer
  - Manage profiles
  - Configure antennas
- **Real-time Monitoring**: WebSocket for real-time tag and stats display
- **Batch EPC Write**: Write multiple EPCs to tags via UI or upload file (xlsx/csv)
- **Beep on Write Success**: When writing EPC is successful, the browser will play a beep sound (`public/beep.mp3`)

## Installation

1. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the backend Flask app:
   ```bash
   python app.py
   ```

3. Install frontend dependencies:
   ```bash
   cd front-end
   npm install
   ```

4. Run the frontend (Vite):
   ```bash
   npm run dev
   ```
   Access the web UI at: [http://localhost:5173](http://localhost:5173)

## API Endpoints

### Connection
- `POST /api/connect` - Connect to reader
- `POST /api/disconnect` - Disconnect reader

### Inventory
- `POST /api/start_inventory` - Start inventory (Target A/B)
- `POST /api/stop_inventory` - Stop inventory

### Configuration
- `GET /api/reader_info` - Get reader info
- `POST /api/set_power` - Set RF power
- `POST /api/enable_antennas` - Enable antennas
- `POST /api/disable_antennas` - Disable antennas
- `GET /api/get_antenna_power` - Get antenna power

### EPC Write
- `POST /api/write_epc_tag_auto` - Write EPC to tag (auto PC bits, word length)
- `POST /api/check_write_epc` - Check EPC write capability

## WebSocket Events

### Client → Server
- `connect` - Connect WebSocket
- `disconnect` - Disconnect WebSocket

### Server → Client
- `tag_detected` - New tag detected
- `stats_update` - Stats update
- `status` - Connection status

## Handling Session Switching Issues

### Common Issues
When switching between sessions (e.g., from session 2 to session 0), you may encounter:
- Reader not responding
- CRC error
- Delay when calling read commands
- Thread not stopping within timeout

### Improved Solutions

1. **Improved stop_inventory function**:
   - Send stop command multiple times to ensure reader receives it
   - Increase wait time for thread to stop (3 seconds)
   - Clear both input and output buffers
   - Force stop if thread does not stop

2. **Improved start_inventory function**:
   - Increase wait time between starts (1 second)
   - Clear buffer before starting
   - Add delay for reader stabilization

3. **Improved start_tags_inventory function**:
   - Add timeout to avoid hanging
   - Clear both input and output buffers
   - Increase wait time for reader stabilization
   - Add delay after sending command

4. **API Reset Reader**:
   - Fully reset reader when needed
   - Clear all buffers
   - Send stop command multiple times
   - Wait for reader to stabilize

## Project Structure

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

- When writing EPC is successful (via UI or file upload), the browser will play a beep sound (`public/beep.mp3`).
- Make sure the `beep.mp3` file exists in the `front-end/public/` directory.

## License

MIT License