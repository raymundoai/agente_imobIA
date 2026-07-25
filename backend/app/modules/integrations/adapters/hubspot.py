from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.modules.integrations.ports.crm import (
    CreateDealData,
    CreateNoteData,
    CreateOrUpdateContactData,
    CreateTaskData,
    CrmContact,
    CrmCredentials,
    CrmDeal,
    CrmPort,
)
from app.shared.errors.exceptions import ExternalServiceError


class HubSpotCrmAdapter(CrmPort):
    def __init__(
        self,
        http_client: httpx.Client,
        *,
        api_version: str = "2026-03",
        retry_attempts: int = 3,
    ) -> None:
        self._http = http_client
        self._api_version = api_version
        self._retry_attempts = retry_attempts

    def search_contact_by_phone(self, credentials: CrmCredentials, phone: str) -> CrmContact | None:
        response = self._request(
            credentials,
            "POST",
            self._object_path("contacts/search"),
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "phone",
                                "operator": "EQ",
                                "value": phone,
                            }
                        ]
                    }
                ],
                "properties": ["firstname", "lastname", "phone", "mobilephone", "email"],
                "limit": 1,
            },
        )
        results = response.get("results", [])
        if not results:
            return None
        item = results[0]
        return CrmContact(id=str(item["id"]), properties=item.get("properties", {}))

    def create_contact(
        self, credentials: CrmCredentials, data: CreateOrUpdateContactData
    ) -> CrmContact:
        response = self._request(
            credentials,
            "POST",
            self._object_path("contacts"),
            json={"properties": self._contact_properties(data)},
        )
        return CrmContact(id=str(response["id"]), properties=response.get("properties", {}))

    def update_contact(
        self, credentials: CrmCredentials, contact_id: str, data: CreateOrUpdateContactData
    ) -> CrmContact:
        response = self._request(
            credentials,
            "PATCH",
            self._object_path(f"contacts/{contact_id}"),
            json={"properties": self._contact_properties(data)},
        )
        return CrmContact(id=str(response["id"]), properties=response.get("properties", {}))

    def create_deal(self, credentials: CrmCredentials, data: CreateDealData) -> CrmDeal:
        properties = {
            "dealname": data.name,
            "dealstage": data.stage,
            **({"pipeline": data.pipeline} if data.pipeline else {}),
            **({"amount": data.amount} if data.amount else {}),
            **{key: value for key, value in data.properties.items() if value is not None},
        }
        response = self._request(
            credentials,
            "POST",
            self._object_path("deals"),
            json={"properties": properties},
        )
        return CrmDeal(id=str(response["id"]), properties=response.get("properties", {}))

    def associate(
        self,
        credentials: CrmCredentials,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
    ) -> None:
        self._request(
            credentials,
            "PUT",
            (
                f"/crm/v4/objects/{self._object_type(from_object_type)}/{from_object_id}"
                f"/associations/default/{self._object_type(to_object_type)}/{to_object_id}"
            ),
            json=None,
        )

    def add_note(
        self,
        credentials: CrmCredentials,
        data: CreateNoteData,
        associations: list[tuple[str, str]],
    ) -> str:
        response = self._request(
            credentials,
            "POST",
            self._object_path("notes"),
            json={
                "properties": {
                    "hs_timestamp": self._timestamp(data.timestamp),
                    "hs_note_body": data.body[:65536],
                    **({"hubspot_owner_id": data.owner_id} if data.owner_id else {}),
                }
            },
        )
        note_id = str(response["id"])
        for object_type, object_id in associations:
            self.associate(credentials, "note", note_id, object_type, object_id)
        return note_id

    def create_task(
        self,
        credentials: CrmCredentials,
        data: CreateTaskData,
        associations: list[tuple[str, str]],
    ) -> str:
        response = self._request(
            credentials,
            "POST",
            self._object_path("tasks"),
            json={
                "properties": {
                    "hs_timestamp": self._timestamp(data.timestamp),
                    "hs_task_body": data.body,
                    "hs_task_subject": data.subject,
                    "hs_task_status": "NOT_STARTED",
                    "hs_task_priority": data.priority,
                    "hs_task_type": "TODO",
                    **({"hubspot_owner_id": data.owner_id} if data.owner_id else {}),
                }
            },
        )
        task_id = str(response["id"])
        for object_type, object_id in associations:
            self.associate(credentials, "task", task_id, object_type, object_id)
        return task_id

    def _request(
        self,
        credentials: CrmCredentials,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        url = f"{credentials.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for _ in range(self._retry_attempts):
            try:
                response = self._http.request(method, url, headers=headers, json=json)
                if response.status_code >= 500:
                    last_error = ExternalServiceError("HubSpot temporary error")
                    continue
                if response.status_code >= 400:
                    raise ExternalServiceError("HubSpot request failed")
                if not response.content:
                    return {}
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
        raise ExternalServiceError("HubSpot request failed") from last_error

    def _object_path(self, suffix: str) -> str:
        return f"/crm/objects/{self._api_version}/{suffix}"

    @staticmethod
    def _object_type(value: str) -> str:
        return {
            "contact": "contacts",
            "deal": "deals",
            "note": "notes",
            "task": "tasks",
        }.get(value, value)

    @staticmethod
    def _contact_properties(data: CreateOrUpdateContactData) -> dict[str, str]:
        parts = data.name.split(maxsplit=1)
        properties = {
            "firstname": parts[0] if parts else data.name,
            "phone": data.phone,
        }
        if len(parts) > 1:
            properties["lastname"] = parts[1]
        if data.email:
            properties["email"] = data.email
        return properties

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")
