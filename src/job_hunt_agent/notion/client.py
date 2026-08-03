from typing import Any
import time


class NotionClient:
    def __init__(self, token: str, notion_version: str = "2026-03-11") -> None:
        self.token = token
        self.notion_version = notion_version
        self.base_url = "https://api.notion.com/v1"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def create_database(self, parent_page_id: str, title: str, properties: dict[str, Any]) -> dict:
        return self._request(
            "POST",
            "/databases",
            json={
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "title": [{"type": "text", "text": {"content": title}}],
                "initial_data_source": {
                    "title": [{"type": "text", "text": {"content": title}}],
                    "properties": properties,
                },
            },
        )

    def create_page(self, parent_data_source_id: str, properties: dict[str, Any]) -> dict:
        return self._request(
            "POST",
            "/pages",
            json={
                "parent": {
                    "type": "data_source_id",
                    "data_source_id": parent_data_source_id,
                },
                "properties": properties,
            },
        )

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    def retrieve_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}")

    def retrieve_data_source(self, data_source_id: str) -> dict:
        return self._request("GET", f"/data_sources/{data_source_id}")

    def retrieve_database(self, database_id: str) -> dict:
        return self._request("GET", f"/databases/{database_id}")

    def update_data_source_title(self, data_source_id: str, title: str) -> dict:
        return self._request(
            "PATCH",
            f"/data_sources/{data_source_id}",
            json={"title": title_payload(title)},
        )

    def update_database_title(self, database_id: str, title: str) -> dict:
        return self._request(
            "PATCH",
            f"/databases/{database_id}",
            json={"title": title_payload(title)},
        )

    def find_database_by_title(self, title: str, parent_page_id: str | None = None) -> dict | None:
        response = self._request(
            "POST",
            "/search",
            json={"query": title, "filter": {"value": "data_source", "property": "object"}},
        )
        for item in response.get("results", []):
            title_items = item.get("title", [])
            plain_title = "".join(part.get("plain_text", "") for part in title_items)
            if plain_title == title and self._matches_parent_page(item, parent_page_id):
                return item
        return None

    def _matches_parent_page(self, data_source: dict, parent_page_id: str | None) -> bool:
        if parent_page_id is None:
            return True
        parent = data_source.get("parent", {})
        if parent.get("type") != "database_id":
            return False
        database_id = parent.get("database_id")
        if not database_id:
            return False
        database = self.retrieve_database(database_id)
        database_parent = database.get("parent", {})
        return database_parent.get("type") == "page_id" and notion_id_equal(
            database_parent.get("page_id", ""),
            parent_page_id,
        )

    def query_database(self, database_id: str, filter_payload: dict | None = None) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {}
            if filter_payload is not None:
                body["filter"] = filter_payload
            if cursor is not None:
                body["start_cursor"] = cursor
            response = self._request("POST", f"/data_sources/{database_id}/query", json=body)
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                return results
            cursor = response.get("next_cursor")

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        import httpx

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(trust_env=False, timeout=60) as client:
                    response = client.request(
                        method,
                        f"{self.base_url}{path}",
                        headers=self.headers,
                        json=json,
                    )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(
                        f"Notion API request failed with {response.status_code}: {response.text}"
                    ) from exc
                return response.json()
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
        raise RuntimeError("Notion request failed") from last_error


def notion_id_equal(left: str, right: str) -> bool:
    return left.replace("-", "") == right.replace("-", "")


def title_payload(title: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": title}}]
