"""Client for the Gardena BFF (Backend-for-Frontend) private API.

The BFF API is the backend used by the official Gardena mobile / web app.
It exposes pump-specific telemetry (pressure, flow, temperature, settings)
that is not available through the public Gardena Smart System API v2.

Endpoint base: https://bff-api.sg.dss.husqvarnagroup.net/v1/
Authentication: Same Husqvarna OAuth2 Bearer token as the public API.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import ClientTimeout

from .auth import GardenaAuthenticationManager

_LOGGER = logging.getLogger(__name__)

BFF_HOST = "https://bff-api.sg.dss.husqvarnagroup.net"
_TIMEOUT = 30


class GardenaBFFError(Exception):
    """Raised when the BFF API returns an error or is unreachable."""


class GardenaBFFClient:
    """Thin async client for the Gardena BFF API."""

    def __init__(self, auth_manager: GardenaAuthenticationManager) -> None:
        self.auth_manager = auth_manager
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=ClientTimeout(total=_TIMEOUT))
        return self._session

    def _headers(self) -> dict:
        headers: dict = {
            "Authorization-Provider": "husqvarna",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.auth_manager._access_token:
            headers["Authorization"] = f"Bearer {self.auth_manager._access_token}"
            headers["X-Api-Key"] = self.auth_manager.client_id
        return headers

    async def get_device(self, device_id: str, location_id: str) -> Dict[str, Any]:
        """Return full device data including pump telemetry."""
        try:
            await self.auth_manager.authenticate()
            session = await self._get_session()
            url = f"{BFF_HOST}/v1/devices/{device_id}?locationId={location_id}"
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status == 200:
                    return await resp.json()
                text = await resp.text()
                raise GardenaBFFError(f"GET device {resp.status}: {text[:200]}")
        except aiohttp.ClientError as exc:
            raise GardenaBFFError(f"Network error: {exc}") from exc

    async def start_pump(
        self,
        device_id: str,
        location_id: str,
        duration_seconds: int = 300,
    ) -> None:
        """Start the pump for the given duration (in seconds)."""
        await self._put_watering_timer(
            device_id,
            location_id,
            {"state": "manual", "duration": duration_seconds, "valve_id": 1},
        )

    async def stop_pump(self, device_id: str, location_id: str) -> None:
        """Stop the pump immediately."""
        await self._put_watering_timer(
            device_id,
            location_id,
            {"state": "idle", "duration": 0, "valve_id": 1},
        )

    async def _put_watering_timer(
        self, device_id: str, location_id: str, value: dict
    ) -> None:
        try:
            await self.auth_manager.authenticate()
            session = await self._get_session()
            url = (
                f"{BFF_HOST}/v1/devices/{device_id}/abilities/watering/properties/"
                f"watering_timer_1?locationId={location_id}"
            )
            body = {"properties": {"name": "watering_timer_1", "value": value}}
            async with session.put(url, json=body, headers=self._headers()) as resp:
                if resp.status not in (200, 204):
                    text = await resp.text()
                    raise GardenaBFFError(f"PUT watering_timer_1 {resp.status}: {text[:200]}")
        except aiohttp.ClientError as exc:
            raise GardenaBFFError(f"Network error: {exc}") from exc

    async def set_turn_on_pressure(
        self,
        device_id: str,
        location_id: str,
        setting_id: str,
        value: float,
    ) -> None:
        """Write a new switch-on pressure (Bar) to the device settings."""
        try:
            await self.auth_manager.authenticate()
            session = await self._get_session()
            url = f"{BFF_HOST}/v1/devices/{device_id}/settings/{setting_id}?locationId={location_id}"
            body = {"settings": {"name": "turn_on_pressure", "value": value, "device": device_id}}
            async with session.put(url, json=body, headers=self._headers()) as resp:
                if resp.status not in (200, 204):
                    text = await resp.text()
                    raise GardenaBFFError(f"PUT setting {resp.status}: {text[:200]}")
        except aiohttp.ClientError as exc:
            raise GardenaBFFError(f"Network error: {exc}") from exc

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
