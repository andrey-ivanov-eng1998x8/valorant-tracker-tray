import base64
import os
from pathlib import Path
import httpx

# Shard mapping since game region from local config doesn't always match the API endpoints
SHARD_MAP = {
    "na": "na",
    "pbe": "na",
    "br": "na",
    "latam": "na",
    "eu": "eu",
    "ap": "ap",
    "kr": "kr",
}

class ClientNotRunningError(Exception):
    pass

class ValorantLocalClient:
    """
    Manages connection to the local Riot Client process via lockfile,
    extracts authorization tokens, and queries the remote pd shard APIs.
    """
    def __init__(self):
        # lockfile lives in AppData/Local on Windows
        self.lockfile_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Riot Games" / "Riot Client" / "Config" / "lockfile"

    def _read_lockfile(self):
        if not self.lockfile_path.exists():
            raise ClientNotRunningError("Riot Client lockfile not found. Make sure Valorant is running.")
        
        try:
            with open(self.lockfile_path, "r") as f:
                data = f.read()
        except PermissionError:
            # Sometimes file access is restricted during early startup handshake
            raise ClientNotRunningError("Lockfile is busy. Try again in a moment.")

        # FIXME: lockfile might be temporarily empty if we catch it mid-write during game launch
        if not data or ":" not in data:
            raise ClientNotRunningError("Lockfile is empty or initializing.")

        parts = data.split(":")
        # Format: name:pid:port:password:protocol
        return {
            "port": parts[2],
            "password": parts[3]
        }

    def fetch_client_version(self) -> str:
        # Riot requires the current client version header for matchmaking/MMR endpoints.
        # Best way is to hit the public valorant-api, otherwise we fall back to a hardcoded safe version.
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get("https://valorant-api.com/v1/version")
                if resp.status_code == 200:
                    return resp.json()["data"]["riotClientVersion"]
        except Exception:
            pass
        return "release-08.05-shipping-12-2432857" # solid fallback if offline or API changes

    def fetch_credentials(self):
        lock_info = self._read_lockfile()
        port = lock_info["port"]
        password = lock_info["password"]
        
        # print(f"Found client on port: {port}")

        auth = base64.b64encode(f"riot:{password}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}

        # Disable SSL warnings as local Riot Client uses self-signed certificates
        # We explicitly ignore warnings to prevent console pollution
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        with httpx.Client(verify=False, limits=limits, timeout=10.0) as client:
            try:
                token_res = client.get(f"https://127.0.0.1:{port}/entitlements/v1/token", headers=headers)
                token_res.raise_for_status()
                token_data = token_res.json()

                session_res = client.get(f"https://127.0.0.1:{port}/chat/v1/session", headers=headers)
                session_res.raise_for_status()
                session_data = session_res.json()

                region_res = client.get(f"https://127.0.0.1:{port}/riotclient/region-locale", headers=headers)
                region_res.raise_for_status()
                region_data = region_res.json()
            except httpx.HTTPError as e:
                raise ClientNotRunningError(f"Failed to communicate with local Riot Client: {e}")

        raw_region = region_data.get("region", "na").lower()
        shard = SHARD_MAP.get(raw_region, "na")

        return {
            "puuid": session_data["puuid"],
            "accessToken": token_data["accessToken"],
            "entitlementsToken": token_data["token"],
            "shard": shard,
            "region": raw_region
        }

    def get_competitive_updates(self, creds: dict, limit: int = 15) -> dict:
        shard = creds["shard"]
        puuid = creds["puuid"]
        url = f"https://pd.{shard}.a.pvp.net/mmr/v1/players/{puuid}/competitiveupdates"
        
        client_version = self.fetch_client_version()
        headers = {
            "Authorization": f"Bearer {creds['accessToken']}",
            "X-Riot-Entitlements-JWT": creds["entitlementsToken"],
            "X-Riot-ClientPlatform": "ew0KCSJjbGllbnRQbGF0Zm9ybSI6ICJXaW5kb3dzIiwNCgkiY2xpZW50VmVyc2lvbiI6ICJSREUtX0xJVkVfU0hSQU1CT0tfQ0xfNDMxOTM3MCIsDQoJImNsaWVudEJ1aWxkIiogNDMxOTM3MCwNCgkiY2xpZW50Vk9SRSI6ICJMSVZFIg0KfQ==",
            "X-Riot-ClientVersion": client_version
        }

        params = {"queue": "competitive", "startIndex": 0, "endIndex": limit}
        
        with httpx.Client(timeout=10.0) as client:
            res = client.get(url, headers=headers, params=params)
            res.raise_for_status()
            return res.json()

    def get_match_history(self, creds: dict, limit: int = 10) -> dict:
        shard = creds["shard"]
        puuid = creds["puuid"]
        url = f"https://pd.{shard}.a.pvp.net/match-history/v1/history/{puuid}"

        headers = {
            "Authorization": f"Bearer {creds['accessToken']}",
            "X-Riot-Entitlements-JWT": creds["entitlementsToken"],
        }
        params = {"startIndex": 0, "endIndex": limit}

        with httpx.Client(timeout=10.0) as client:
            res = client.get(url, headers=headers, params=params)
            res.raise_for_status()
            return res.json()
