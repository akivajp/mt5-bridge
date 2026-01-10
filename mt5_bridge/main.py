#!/usr/bin/env python3

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import asyncio
import argparse
import os
import sys
import json
from importlib.metadata import version, PackageNotFoundError

# Try relative imports (package mode), fallback to path manipulation (script mode)
try:
    from .mt5_handler import MT5Handler
    from .client import BridgeClient
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mt5_bridge.mt5_handler import MT5Handler
    from mt5_bridge.client import BridgeClient

app = FastAPI(title="MT5 Bridge API")
mt5_handler = MT5Handler()

class Rate(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int

class Tick(BaseModel):
    time: int
    bid: float
    ask: float
    last: float
    volume: int

class Position(BaseModel):
    ticket: int
    symbol: str
    type: str
    volume: float
    price_open: float
    comment: str
    magic: int
    sl: float
    tp: float
    price_current: float
    profit: float
    time: int

async def monitor_connection():
    """Periodically check MT5 connection and reconnect if needed."""
    while True:
        try:
            if not mt5_handler.check_connection():
                print("WARNING: MT5 connection lost. Reconnecting...")
            await asyncio.sleep(5)  # Check every 5 seconds
        except Exception as e:
            print(f"Error in connection monitor: {e}")
            await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    """Initialize MT5 connection on startup."""
    # Only try to initialize if we are on Windows (checked in main types, but safe here too)
    if sys.platform == "win32":
        if not mt5_handler.initialize():
            print("WARNING: Failed to initialize MT5 on startup. Will retry in background.")
        
        # Start connection monitor
        asyncio.create_task(monitor_connection())
    else:
        print("Non-Windows platform detected: MT5 connection disabled.")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown MT5 connection."""
    mt5_handler.shutdown()

@app.get("/health")
def health_check():
    return {"status": "ok", "mt5_connected": mt5_handler.connected}

@app.get("/rates/{symbol}", response_model=List[Rate])
def get_rates(
    symbol: str, 
    timeframe: str = Query(..., description="Timeframe (e.g., M1, H1)"), 
    count: int = Query(1000, description="Number of bars")
):
    rates = mt5_handler.get_rates(symbol, timeframe, count)
    if rates is None:
        raise HTTPException(status_code=500, detail=f"Failed to get rates for {symbol}")
    return rates

@app.get("/tick/{symbol}", response_model=Tick)
def get_tick(symbol: str):
    tick = mt5_handler.get_tick(symbol)
    if tick is None:
        raise HTTPException(status_code=500, detail=f"Failed to get tick for {symbol}")
    return tick

@app.get("/positions", response_model=List[Position])
def get_positions():
    positions = mt5_handler.get_positions()
    if positions is None:
        raise HTTPException(status_code=500, detail="Failed to get positions")
    return positions

class OrderRequest(BaseModel):
    symbol: str
    type: str # "BUY" or "SELL"
    volume: float
    sl: float = 0.0
    tp: float = 0.0
    comment: str = ""
    magic: int = 123456

class CloseRequest(BaseModel):
    ticket: int

class ModifyRequest(BaseModel):
    ticket: int
    sl: Optional[float] = None
    tp: Optional[float] = None
    update_sl: bool = False
    update_tp: bool = False

@app.post("/order")
def send_order(order: OrderRequest):
    ticket, error = mt5_handler.send_order(
        order.symbol, 
        order.type, 
        order.volume, 
        order.sl, 
        order.tp, 
        order.comment,
        magic=order.magic
    )
    if ticket is None:
        detail = error or "Failed to send order"
        raise HTTPException(status_code=500, detail=detail)
    return {"status": "ok", "ticket": ticket}

@app.post("/close")
def close_position(req: CloseRequest):
    success, message = mt5_handler.close_position(req.ticket)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to close position: {message}")
    return {"status": "ok"}

@app.post("/modify")
def modify_position(req: ModifyRequest):
    success, message = mt5_handler.modify_position(
        req.ticket,
        req.sl,
        req.tp,
        req.update_sl,
        req.update_tp,
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to modify position: {message}")
    return {"status": "ok"}

def main():
    parser = argparse.ArgumentParser(description="MT5 Bridge CLI")
    
    try:
        app_version = version("mt5-bridge")
    except PackageNotFoundError:
        app_version = "unknown"

    parser.add_argument(
        "--version",
        action="version",
        version=f"mt5-bridge version: {app_version}\nPython version: {sys.version}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Serve command
    server_parser = subparsers.add_parser("server", help="Run MT5 Bridge Server (Windows Only)")
    server_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind (default: 0.0.0.0)",
    )
    server_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    server_parser.add_argument("--mt5-path", default=None, help="Path to MT5 executable")
    server_parser.add_argument("--mt5-login", type=int, default=None, help="MT5 Login ID")
    server_parser.add_argument("--mt5-password", default=None, help="MT5 Password")
    server_parser.add_argument("--mt5-server", default=None, help="MT5 Server Name")
    server_parser.add_argument("--no-utc", action="store_true", help="Disable UTC conversion")

    # Client command
    client_parser = subparsers.add_parser("client", help="Run MT5 Bridge Client")
    client_parser.add_argument("--url", default="http://localhost:8000", help="Server URL")
    
    client_subs = client_parser.add_subparsers(dest="client_command", help="Client command", required=True)
    
    # Client Subcommands
    client_subs.add_parser("health", help="Check server health")
    
    rates_p = client_subs.add_parser("rates", help="Get historical rates")
    rates_p.add_argument("symbol", type=str)
    rates_p.add_argument("--timeframe", default="M1")
    rates_p.add_argument("--count", type=int, default=1000)
    
    tick_p = client_subs.add_parser("tick", help="Get latest tick")
    tick_p.add_argument("symbol", type=str)
    
    client_subs.add_parser("positions", help="Get open positions")

    args = parser.parse_args()

    if args.command == "server":
        if sys.platform != "win32":
            print("Error: Server functionality is only supported on Windows.")
            sys.exit(1)

        # Configure MT5 handler with CLI args
        if args.mt5_path:
            mt5_handler.program_path = args.mt5_path
        if args.mt5_login:
            mt5_handler.login = args.mt5_login
        if args.mt5_password:
            mt5_handler.password = args.mt5_password
        if args.mt5_server:
            mt5_handler.server = args.mt5_server
        
        # Configure UTC conversion
        mt5_handler.use_utc = not args.no_utc
        if mt5_handler.use_utc:
            print("UTC conversion enabled (Server Time -> UTC)")
        else:
            print("UTC conversion disabled (Raw Server Time)")

        # Run Server
        uvicorn.run(app, host=args.host, port=args.port)

    elif args.command == "client":
        client = BridgeClient(base_url=args.url)
        if args.client_command == "health":
            print(json.dumps(client.check_health(), indent=2))
        elif args.client_command == "rates":
            print(json.dumps(client.get_rates(args.symbol, args.timeframe, args.count), indent=2))
        elif args.client_command == "tick":
            print(json.dumps(client.get_tick(args.symbol), indent=2))
        elif args.client_command == "positions":
            print(json.dumps(client.get_positions(), indent=2))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
