#!/usr/bin/env python3
"""
Script để chạy RFID Reader Web Control Panel
"""

import os
import sys
import argparse
from app import app, socketio, config

def main():
    parser = argparse.ArgumentParser(description='RFID Reader Web Control Panel')
    parser.add_argument('--host', default=config.HOST, help='Host address (default: %(default)s)')
    parser.add_argument('--port', type=int, default=config.PORT, help='Port number (default: %(default)s)')
    parser.add_argument('--debug', action='store_true', default=config.DEBUG, help='Enable debug mode')
    parser.add_argument('--config', choices=['development', 'production', 'testing'], 
                       default='development', help='Configuration environment')
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ['FLASK_ENV'] = args.config
    
    print("🚀 RFID Reader Web Control Panel")
    print("=" * 40)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Debug: {args.debug}")
    print(f"Environment: {args.config}")
    print("=" * 40)
    print(f"🌐 Open your browser and go to: http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop the server")
    print("=" * 40)
    
    try:
        socketio.run(app, debug=args.debug, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 