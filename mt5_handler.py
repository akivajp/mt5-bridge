import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone
import logging
from typing import Optional, Dict, List, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MT5Handler:
    def __init__(
        self,
        program_path: Optional[str] = None,
        login: Optional[int] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        use_utc: bool = True
    ):
        self.connected = False
        self.program_path = program_path
        self.login = login
        self.password = password
        self.server = server
        self.use_utc = use_utc
        self._server_offset_sec: Optional[int] = None

    def initialize(self) -> bool:
        """
        Initialize connection to MetaTrader 5 terminal.
        """
        # If path is specified, use it
        init_args = {}
        if self.program_path:
            init_args["path"] = self.program_path
            
        if not mt5.initialize(**init_args):
            logger.error("initialize() failed, error code = %s", mt5.last_error())
            self.connected = False
            return False
            
        # If login credentials are provided, try to login
        if self.login and self.password and self.server:
            authorized = mt5.login(
                login=self.login,
                password=self.password,
                server=self.server
            )
            if not authorized:
                logger.error("failed to connect at account #%d, error code: %s", self.login, mt5.last_error())
                self.connected = False
                return False
            logger.info("MT5 login successful")

        logger.info("MT5 initialized successfully")
        self.connected = True
        return True

    def check_connection(self) -> bool:
        """
        Check if connection is still alive using terminal_info.
        Attempt to reconnect if lost.
        """
        if not mt5.terminal_info():
            self.connected = False
            logger.warning("Connection lost. Attempting to reconnect...")
            return self.initialize()
        
        self.connected = True
        return True

    def shutdown(self):
        """
        Shutdown connection to MetaTrader 5.
        """
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection shutdown")

    def _update_server_offset(self, symbol: str):
        """
        Estimate server timezone offset relative to UTC using the given symbol's tick time.
        Offset = ServerTime - UTC.
        """
        if self._server_offset_sec is not None:
            return

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return

        server_ts = tick.time
        # Use simple utc timestamp
        utc_ts = datetime.now(timezone.utc).timestamp()
        
        diff = server_ts - utc_ts
        # Round to nearest 15 minutes (900s) to handle latency
        rounded_diff = round(diff / 900) * 900
        self._server_offset_sec = int(rounded_diff)
        logger.info(f"Server timezone offset estimated: {self._server_offset_sec}s (using {symbol})")

    def _apply_time_correction(self, ts: int) -> int:
        """Convert server timestamp to UTC if use_utc is True."""
        if not self.use_utc:
            return ts
        # If offset not yet calculated, we can't correct yet (or assume 0)
        # We rely on _update_server_offset being called before or during.
        return int(ts - (self._server_offset_sec or 0))

    def get_rates(self, symbol: str, timeframe_str: str, num_bars: int) -> Optional[List[Dict]]:
        """
        Get historical rates for a symbol.
        
        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            timeframe_str: Timeframe string (e.g., "M1", "H1")
            num_bars: Number of bars to fetch
            
        Returns:
            List of dictionaries containing rate data, or None if failed.
        """
        if not self.connected:
            if not self.initialize():
                return None

        # Map timeframe string to MT5 constant
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": getattr(mt5, "TIMEFRAME_W1", None),
            "MN1": getattr(mt5, "TIMEFRAME_MN1", None),
        }
        
        mt5_tf = tf_map.get(timeframe_str)
        if mt5_tf is None:
            logger.error(f"Invalid timeframe: {timeframe_str}")
            return None

        # Copy rates from current time backwards
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, num_bars)
        
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)
        
        if rates is None:
            logger.error(f"Failed to get rates for {symbol}")
            return None
            
        # Convert to list of dicts (handling numpy types)
        # rates is a numpy record array
        result = []
        for rate in rates:
            result.append({
                "time": self._apply_time_correction(int(rate['time'])),
                "open": float(rate['open']),
                "high": float(rate['high']),
                "low": float(rate['low']),
                "close": float(rate['close']),
                "tick_volume": int(rate['tick_volume']),
                "spread": int(rate['spread']),
                "real_volume": int(rate['real_volume'])
            })
            
        return result

    def get_tick(self, symbol: str) -> Optional[Dict]:
        """
        Get latest tick data.
        """
        if not self.connected:
            if not self.initialize():
                return None
                
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Failed to get tick for {symbol}")
            return None
            
        if self.use_utc and self._server_offset_sec is None:
            self._update_server_offset(symbol)

        return {
            "time": self._apply_time_correction(int(tick.time)),
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last),
            "volume": int(tick.volume)
        }

    def get_positions(self) -> Optional[List[Dict]]:
        """
        Get current open positions.
        """
        if not self.connected:
            if not self.initialize():
                return None
                
        positions = mt5.positions_get()
        if positions is None:
            return []
            
        result = []
        for pos in positions:
            result.append({
                "ticket": int(pos.ticket),
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": float(pos.volume),
                "price_open": float(pos.price_open),
                # deep-trader 側で「自分のポジだけ」を安全に識別するために必要
                "comment": str(getattr(pos, "comment", "")),
                "magic": int(getattr(pos, "magic", 0)),
                "sl": float(pos.sl),
                "tp": float(pos.tp),
                "price_current": float(pos.price_current),
                "profit": float(pos.profit),
                "time": self._apply_time_correction(int(pos.time))
            })
            
        return result

    def send_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        comment: str = "",
        magic: int = 123456,
    ) -> tuple[Optional[int], Optional[str]]:
        """
        Send a market order.
        
        Args:
            symbol: Symbol to trade.
            order_type: "BUY" or "SELL".
            volume: Lot size.
            sl: Stop Loss price.
            tp: Take Profit price.
            comment: Order comment.
            
        Returns:
            Order ticket if successful, None otherwise.
        """
        if not self.connected:
            if not self.initialize():
                message = "MT5 に接続できませんでした"
                return None, message
                
        # Get current price for filling request
        tick = self.get_tick(symbol)
        if tick is None:
            message = f"{symbol} のティック情報を取得できません"
            logger.error(message)
            return None, message
            
        action = mt5.TRADE_ACTION_DEAL
        mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick['ask'] if order_type == "BUY" else tick['bid']
        
        base_request = {
            "action": action,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,  # Slippage tolerance
            "magic": magic,   # Magic number
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # filling の切り替えは「filling 起因の失敗」のときだけ行う。
        # 例: Invalid stops(10016) は filling を変えても解決しないので、総当たりしない。
        invalid_fill_retcode = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)

        # まずはデフォルト（type_filling未指定）を試し、
        # 「Unsupported filling mode / Invalid filling」等の場合のみ filling を変えて再試行する。
        fillings = [
            None,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN,
        ]
        last_error: Optional[str] = None
        for filling in fillings:
            request = dict(base_request)
            if filling is not None:
                request["type_filling"] = filling
            filling_label = "default" if filling is None else str(filling)
            result = mt5.order_send(request)
            if result is None:
                # result=None は通信/端末側の問題の可能性が高く、filling を変えても改善しないことが多い
                error_code = mt5.last_error()
                last_error = f"order_send returned None with filling={filling_label} (error={error_code}). Request: {request}"
                logger.error(last_error)
                break
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order sent successfully: {result.order} (filling={filling_label})")
                return result.order, None
            last_error = f"filling={filling_label} {result.retcode} で失敗: {result.comment}"
            logger.warning("Order send failed: %s", last_error)

            # filling 起因の失敗（Unsupported/Invalid filling）のときだけ次の filling を試す。
            # それ以外（例: Invalid stops）は即座に中断して返す。
            if int(result.retcode) == int(invalid_fill_retcode) or "filling" in str(result.comment).lower():
                continue
            break
        message = last_error or "すべての filling モードで発注に失敗しました"
        return None, message

    def close_position(self, ticket: int) -> tuple[bool, str]:
        """
        Close an existing position.
        Returns: (success, message)
        """
        if not self.connected:
            if not self.initialize():
                return False, "Failed to connect to MT5"
                
        # Get position details to know volume and symbol
        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.error(f"Position {ticket} not found")
            return False, f"Position {ticket} not found"
            
        pos = positions[0]
        symbol = pos.symbol
        volume = pos.volume
        
        # Determine opposite type
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        
        # Get current price
        tick = self.get_tick(symbol)
        if tick is None:
            return False, f"Failed to get tick for {symbol}"
            
        price = tick['bid'] if order_type == mt5.ORDER_TYPE_SELL else tick['ask']
        
        base_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "Close position",
            "type_time": mt5.ORDER_TIME_GTC,
        }

        # filling の切り替えは「filling 起因の失敗」のときだけ行う。
        invalid_fill_retcode = getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)

        fillings = [
            None,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN,
        ]
        last_error: Optional[str] = None
        for filling in fillings:
            request = dict(base_request)
            if filling is not None:
                request["type_filling"] = filling
            filling_label = "default" if filling is None else str(filling)
            result = mt5.order_send(request)
            if result is None:
                error_code = mt5.last_error()
                last_error = f"order_send returned None with filling={filling_label} (error={error_code})"
                logger.error(last_error)
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info("Position %s closed successfully (filling=%s)", ticket, filling_label)
                return True, "Success"
            last_error = f"filling={filling_label} {result.retcode} で失敗: {result.comment}"
            logger.warning("Close position failed: %s", last_error)

            # filling 起因の失敗（Unsupported/Invalid filling）のときだけ次の filling を試す。
            # それ以外（例: Invalid stops）は即座に中断して返す。
            if int(result.retcode) == int(invalid_fill_retcode) or "filling" in str(result.comment).lower():
                continue
            break

        message = last_error or "Close position failed"
        return False, message

    def modify_position(self, ticket: int, sl: Optional[float], tp: Optional[float], update_sl: bool, update_tp: bool) -> tuple[bool, str]:
        """Adjust stop loss / take profit for an existing position."""

        if not update_sl and not update_tp:
            return False, "Nothing to update"

        if not self.connected:
            if not self.initialize():
                return False, "Failed to connect to MT5"

        positions = mt5.positions_get(ticket=ticket)
        if positions is None or len(positions) == 0:
            logger.error(f"Position {ticket} not found")
            return False, f"Position {ticket} not found"

        pos = positions[0]
        symbol = pos.symbol
        action = getattr(mt5, "TRADE_ACTION_SLTP", None)
        if action is None:
            logger.error("MT5 does not support TRADE_ACTION_SLTP")
            return False, "TRADE_ACTION_SLTP not available"

        sl_value = float(pos.sl or 0.0)
        tp_value = float(pos.tp or 0.0)

        if update_sl:
            sl_value = 0.0 if sl is None else float(sl)

        if update_tp:
            tp_value = 0.0 if tp is None else float(tp)

        request = {
            "action": action,
            "position": ticket,
            "symbol": symbol,
            "sl": sl_value,
            "tp": tp_value,
        }

        result = mt5.order_send(request)
        if result is None:
            logger.error("Modify position failed: result is None")
            return False, "order_send returned None"

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error_msg = f"{result.comment} ({result.retcode})"
            logger.error(f"Modify position failed: {error_msg}")
            return False, error_msg

        logger.info(f"Protection updated for ticket {ticket}")
        return True, "Success"
