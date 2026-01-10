import httpx
from typing import List, Dict, Optional, Any

class BridgeClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    def get_rates(self, symbol: str, timeframe: str = "M1", count: int = 1000) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/rates/{symbol}"
        params = {"timeframe": timeframe, "count": count}
        try:
            resp = httpx.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            print(f"Error fetching rates: {e}")
            return []

    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/tick/{symbol}"
        try:
            resp = httpx.get(url, timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            print(f"Error fetching tick: {e}")
            return None
    
    def get_positions(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/positions"
        try:
            resp = httpx.get(url, timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            print(f"Error fetching positions: {e}")
            return []
    
    def check_health(self) -> Dict[str, Any]:
        url = f"{self.base_url}/health"
        try:
            resp = httpx.get(url, timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            return {"status": "error", "detail": str(e)}
