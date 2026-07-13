"""קליינט ל-API של morning (חשבונית ירוקה).

מבוסס על התיעוד הרשמי: https://developers.morning.co/
- אימות: POST /account/token עם id, secret, grant_type=client_credentials → JWT
- הפקת מסמך: POST /documents
- קישורי הורדה: GET /documents/{id}/download/links
"""
import time

import requests


class GreenInvoiceError(Exception):
    pass


class GreenInvoiceClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self._token = None
        self._token_expires = 0

    # ---------- auth ----------
    def _fetch_token(self) -> None:
        url = f"{self.base_url}/account/token"
        payload = {
            "id": self.api_key,
            "secret": self.api_secret,
            "grant_type": "client_credentials",
        }
        resp = requests.post(url, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise GreenInvoiceError(
                f"קבלת טוקן נכשלה ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        self._token = data.get("token")
        # expires מוחזר כ-timestamp; אם לא — נחדש בעוד 50 דקות
        self._token_expires = data.get("expires", time.time() + 50 * 60)
        if not self._token:
            raise GreenInvoiceError(f"לא התקבל טוקן בתשובה: {data}")

    def _headers(self) -> dict:
        # מרווח ביטחון של דקה לפני פקיעה
        if not self._token or time.time() > self._token_expires - 60:
            self._fetch_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, json=json_body, headers=self._headers(), timeout=self.timeout
        )
        if resp.status_code == 401:
            # טוקן פג — ננסה פעם אחת מחדש
            self._token = None
            resp = requests.request(
                method, url, json=json_body, headers=self._headers(), timeout=self.timeout
            )
        if resp.status_code >= 400:
            raise GreenInvoiceError(
                f"{method} {path} נכשל ({resp.status_code}): {resp.text[:500]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {}

    # ---------- API ----------
    def test_connection(self) -> bool:
        self._fetch_token()
        return True

    def create_document(self, payload: dict) -> dict:
        """מפיק מסמך חדש. מחזיר את תשובת השרת (כולל id ומספר מסמך)."""
        return self._request("POST", "/documents", payload)

    def get_download_links(self, document_id: str) -> dict:
        return self._request("GET", f"/documents/{document_id}/download/links")

    def search_documents(self, filters: dict) -> dict:
        return self._request("POST", "/documents/search", filters)
