from __future__ import annotations

from typing import Any

import httpx

from app.modules.integrations.ports.real_estate_platform import (
    PlatformContactData,
    PlatformCredentials,
    PlatformLeadData,
    PlatformPage,
    RealEstatePlatformPort,
)
from app.shared.errors.exceptions import ExternalServiceError


class TecimobAdapter(RealEstatePlatformPort):
    def __init__(self, http_client: httpx.Client, *, retry_attempts: int = 3) -> None:
        self._http = http_client
        self._retry_attempts = retry_attempts

    def list_properties(
        self,
        credentials: PlatformCredentials,
        *,
        page: int = 1,
        per_page: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> PlatformPage:
        payload = self._request(
            credentials,
            "GET",
            "/api/properties",
            params=self._pagination_params(page, per_page, filters),
        )
        return self._page(payload, page, per_page)

    def get_property(self, credentials: PlatformCredentials, property_id: str) -> dict[str, Any]:
        payload = self._request(credentials, "GET", f"/api/properties/{property_id}")
        return self._data(payload)

    def list_contacts(
        self,
        credentials: PlatformCredentials,
        *,
        page: int = 1,
        per_page: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> PlatformPage:
        payload = self._request(
            credentials,
            "GET",
            "/api/people",
            params=self._pagination_params(page, per_page, filters),
        )
        return self._page(payload, page, per_page)

    def create_contact(
        self, credentials: PlatformCredentials, data: PlatformContactData
    ) -> dict[str, Any]:
        payload = self._request(
            credentials,
            "POST",
            "/api/people",
            json={
                "name": data.name,
                "email": data.email,
                "user_id": data.owner_user_id,
                "phones": self._phones(data.phone),
                "groups_id": data.group_ids,
            },
        )
        return self._data(payload)

    def create_lead(
        self, credentials: PlatformCredentials, data: PlatformLeadData
    ) -> dict[str, Any]:
        payload = self._request(
            credentials,
            "POST",
            "/api/leads/store-person",
            json={
                "name": data.name,
                "email": data.email,
                "phone_number": data.phone,
                "properties_id": data.property_ids,
                "user_id": data.owner_user_id,
                "note": data.note,
            },
        )
        return self._data(payload)

    def list_users(
        self, credentials: PlatformCredentials, *, page: int = 1, per_page: int = 20
    ) -> PlatformPage:
        payload = self._request(
            credentials,
            "GET",
            "/api/users",
            params={"page": page, "per_page": per_page},
        )
        return self._page(payload, page, per_page)

    def list_contact_groups(self, credentials: PlatformCredentials) -> list[dict[str, Any]]:
        payload = self._request(credentials, "GET", "/api/people/groups")
        data = payload.get("data")
        return data if isinstance(data, list) else []

    def add_note(
        self,
        credentials: PlatformCredentials,
        *,
        user_id: str,
        note: str,
        contact_id: str | None = None,
        property_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._request(
            credentials,
            "POST",
            "/api/notes",
            json={
                "user_id": user_id,
                "people_id": contact_id,
                "property_id": property_id,
                "note": note,
            },
        )
        return self._data(payload)

    def _request(
        self,
        credentials: PlatformCredentials,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{credentials.base_url.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for _ in range(self._retry_attempts):
            try:
                response = self._http.request(
                    method, url, headers=headers, params=params, json=self._clean(json)
                )
                if response.status_code >= 500:
                    last_error = ExternalServiceError("Tecimob temporary error")
                    continue
                if response.status_code >= 400:
                    raise ExternalServiceError("Tecimob request failed")
                if not response.content:
                    return {}
                payload = response.json()
                return payload if isinstance(payload, dict) else {"data": payload}
            except httpx.HTTPError as exc:
                last_error = exc
        raise ExternalServiceError("Tecimob request failed") from last_error

    @staticmethod
    def _pagination_params(
        page: int, per_page: int, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if filters:
            params.update(filters)
        return params

    @staticmethod
    def _page(payload: dict[str, Any], page: int, per_page: int) -> PlatformPage:
        items = payload.get("data")
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        return PlatformPage(
            items=items if isinstance(items, list) else [],
            page=int(meta.get("current_page") or page),
            per_page=int(meta.get("per_page") or per_page),
            total=int(meta["total"]) if isinstance(meta.get("total"), int) else None,
        )

    @staticmethod
    def _data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _phones(phone: str | None) -> list[dict[str, Any]]:
        if not phone:
            return []
        digits = "".join(character for character in phone if character.isdigit())
        if digits.startswith("55") and len(digits) > 11:
            digits = digits[2:]
        return [{"ddi": 55, "number": digits}]

    @staticmethod
    def _clean(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if payload is None:
            return None
        return {key: value for key, value in payload.items() if value not in (None, [], {})}
