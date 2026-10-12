"""Bounded official provider pages and opaque resumable cursors."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode, urlsplit

from app.integrations.accounts import ProviderHTTP
from app.integrations.extraction_cache import cache
from app.integrations.normalization import calendar_facts, mail_facts, timestamp
from app.integrations.provider import ProviderError


@dataclass
class Page:
    events: list[tuple[str, dict]]
    checkpoint: dict
    complete: bool
    full: bool = False


class AccountAdapter:
    def __init__(
        self, provider: str, kind: str, http: ProviderHTTP, retention: int = 30
    ):
        self.provider, self.kind, self.http, self.retention = (
            provider,
            kind,
            http,
            retention,
        )
        self.cache_scope: tuple[str, ...] | None = None

    def normalize(self, event, operation):
        return cache.extract(
            self.cache_scope,
            str(event.get("id", "")),
            self.provider + "_" + operation,
            event,
            lambda payload: (
                mail_facts(payload, self.provider)
                if operation == "email"
                else calendar_facts(payload, self.provider)
            ),
        )

    def get(self, url: str, token: str, **kwargs) -> dict:
        return self.http.request(
            "GET",
            url,
            headers={
                "Authorization": "Bearer " + token,
                "Prefer": 'outlook.body-content-type="text", outlook.timezone="UTC", IdType="ImmutableId", odata.maxpagesize=25',
            },
            **kwargs,
        )

    def calendars(self, token: str) -> list[dict]:
        url = (
            "https://www.googleapis.com/calendar/v3/users/me/calendarList"
            if self.provider == "google"
            else "https://graph.microsoft.com/v1.0/me/calendars"
        )
        result = []
        for _ in range(10):
            response = self.get(url, token)
            for item in response.get(
                "items" if self.provider == "google" else "value", []
            ):
                if self.provider == "google" and item.get("accessRole") not in (
                    "reader",
                    "writer",
                    "owner",
                ):
                    continue
                result.append(
                    {
                        "id": str(item["id"])[:255],
                        "name": str(
                            item.get("summary") or item.get("name") or "Calendar"
                        )[:150],
                    }
                )
            next_page = (
                response.get("nextPageToken")
                if self.provider == "google"
                else response.get("@odata.nextLink")
            )
            if not next_page:
                return result
            url = (
                "https://www.googleapis.com/calendar/v3/users/me/calendarList?"
                + urlencode({"pageToken": next_page})
                if self.provider == "google"
                else self.graph_link(next_page, "/v1.0/me/calendars")
            )
        raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)

    @staticmethod
    def graph_link(value, path: str) -> str:
        if not isinstance(value, str) or len(value) > 16000:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or parsed.path != path
            or parsed.fragment
        ):
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        return value

    def page(self, token: str, stream: str, checkpoint: dict, now: datetime) -> Page:
        if self.provider == "google" and self.kind == "email":
            return self.gmail(token, checkpoint, now)
        if self.provider == "google":
            return self.google_calendar(token, stream, checkpoint, now)
        return self.graph(token, stream, checkpoint, now)

    def gmail(self, token: str, checkpoint: dict, now: datetime) -> Page:
        base = "https://gmail.googleapis.com/gmail/v1/users/me/"
        cp = dict(checkpoint)
        full = not cp.get("history")
        deleted: list[str]
        if cp.get("pending_ids"):
            ids = cp.pop("pending_ids")
            deleted = []
            response = cp.pop("pending_response")
        elif full:
            if not cp.get("anchor"):
                cp["anchor"] = str(self.get(base + "profile", token)["historyId"])
            cp.setdefault(
                "window_start", int((now - timedelta(days=self.retention)).timestamp())
            )
            args = {
                "maxResults": 25,
                "q": f"after:{cp['window_start']} -in:sent -in:drafts -in:spam -in:trash",
            }
            if cp.get("page"):
                args["pageToken"] = cp["page"]
            response = self.get(base + "messages", token, params=args)
            ids = [str(m["id"]) for m in response.get("messages", [])]
            deleted = []
        else:
            args = {"maxResults": 25, "startHistoryId": cp["history"]}
            if cp.get("page"):
                args["pageToken"] = cp["page"]
            response = self.get(base + "history", token, params=args)
            ids, deleted = [], []
            for item in response.get("history", []):
                ids.extend(
                    str(m["message"]["id"]) for m in item.get("messagesAdded", [])
                )
                ids.extend(str(m["id"]) for m in item.get("messages", []))
                deleted.extend(
                    str(m["message"]["id"]) for m in item.get("messagesDeleted", [])
                )
        ids = [id for id in dict.fromkeys(ids) if id not in deleted]
        if len(ids) > 2000:
            raise ProviderError("INCOMPLETE_SYNC", retryable=False)
        if len(ids) > 25:
            cp["pending_ids"] = ids[25:]
            cp["pending_response"] = {
                key: response[key]
                for key in ("nextPageToken", "historyId")
                if key in response
            }
            ids = ids[:25]
        events = [
            (external_id, {"kind": "email", "unavailable": True})
            for external_id in set(deleted)
        ]
        for external_id in dict.fromkeys(ids):
            if external_id in deleted:
                continue
            try:
                message = self.get(
                    base + "messages/" + quote(external_id, safe=""),
                    token,
                    params={"format": "full"},
                )
            except ProviderError as error:
                if error.code != "SOURCE_NOT_FOUND":
                    raise
                events.append((external_id, {"kind": "email", "unavailable": True}))
                continue
            if set(message.get("labelIds", [])) & {"SENT", "DRAFT", "SPAM", "TRASH"}:
                events.append((external_id, {"kind": "email", "unavailable": True}))
                continue
            facts = self.normalize(message, "email")
            if datetime.fromisoformat(facts["source_timestamp"]) >= now - timedelta(
                days=self.retention
            ):
                events.append((external_id, facts))
        if cp.get("pending_ids"):
            return Page(events, cp, False, full)
        more = response.get("nextPageToken")
        if more:
            cp["page"] = more
        else:
            cp = {"history": cp["anchor"] if full else str(response["historyId"])}
        return Page(events, cp, not bool(more), full)

    def google_calendar(self, token, stream, checkpoint, now) -> Page:
        cp = dict(checkpoint)
        if cp.get("end") and datetime.fromisoformat(cp["end"]) < now + timedelta(
            days=30
        ):
            cp = {}
        full = not cp.get("sync")
        url = (
            "https://www.googleapis.com/calendar/v3/calendars/"
            + quote(stream, safe="")
            + "/events"
        )
        args = {"maxResults": 100, "singleEvents": "true", "showDeleted": "true"}
        if full:
            cp.setdefault("start", (now - timedelta(days=self.retention)).isoformat())
            cp.setdefault("end", (now + timedelta(days=180)).isoformat())
            args.update(timeMin=cp["start"], timeMax=cp["end"])
        else:
            args["syncToken"] = cp["sync"]
        if cp.get("page"):
            args["pageToken"] = cp["page"]
        response = self.get(url, token, params=args)
        events = [
            (str(e["id"]), self.normalize(e, "calendar"))
            for e in response.get("items", [])
        ]
        more = response.get("nextPageToken")
        if more:
            cp["page"] = more
        else:
            cp.pop("page", None)
            cp["sync"] = response["nextSyncToken"]
        return Page(events, cp, not bool(more), full)

    def graph(self, token, stream, checkpoint, now) -> Page:
        cp = dict(checkpoint)
        delta = True
        if self.kind == "email":
            path = "/v1.0/me/mailFolders/inbox/messages/delta"
        else:
            # v1.0 documents default-calendar delta. Selected non-default calendars
            # use supported paginated calendarView reconciliation, never beta APIs.
            default_id = self.get(
                "https://graph.microsoft.com/v1.0/me/calendar?$select=id", token
            ).get("id")
            if not isinstance(default_id, str) or not default_id:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
            delta = stream == default_id
            if (
                cp.get("default_calendar") is not None
                and cp["default_calendar"] != delta
            ):
                cp = {}
            if cp.get("end") and datetime.fromisoformat(cp["end"]) < now + timedelta(
                days=30
            ):
                cp = {}
            cp["default_calendar"] = delta
            path = (
                "/v1.0/me/calendarView/delta"
                if delta
                else "/v1.0/me/calendars/" + quote(stream, safe="") + "/calendarView"
            )
            if not delta:
                cp.pop("delta", None)
                if not cp.get("page"):
                    cp["start"] = (now - timedelta(days=self.retention)).isoformat()
                    cp["end"] = (now + timedelta(days=180)).isoformat()
        full = not cp.get("delta") or not delta
        if cp.get("page") or cp.get("delta"):
            url = self.graph_link(cp.get("page") or cp["delta"], path)
        else:
            args: dict[str, str | int] = {}
            if self.kind == "email":
                args["$select"] = (
                    "id,subject,from,toRecipients,receivedDateTime,lastModifiedDateTime,conversationId,body,hasAttachments"
                )
            else:
                cp.setdefault(
                    "start", (now - timedelta(days=self.retention)).isoformat()
                )
                cp.setdefault("end", (now + timedelta(days=180)).isoformat())
                args.update(startDateTime=cp["start"], endDateTime=cp["end"])
            url = "https://graph.microsoft.com" + path + "?" + urlencode(args)
        response = self.get(url, token)
        events = []
        for event in response.get("value", []):
            if event.get("@removed"):
                facts = {"kind": self.kind, "unavailable": True}
            elif self.kind == "calendar":
                facts = self.normalize(event, "calendar")
            else:
                if not all(
                    key in event
                    for key in ("body", "receivedDateTime", "from", "conversationId")
                ):
                    try:
                        event = self.get(
                            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/"
                            + quote(event["id"], safe=""),
                            token,
                        )
                    except ProviderError as error:
                        if error.code != "SOURCE_NOT_FOUND":
                            raise
                        events.append(
                            (str(event["id"]), {"kind": "email", "unavailable": True})
                        )
                        continue
                facts = self.normalize(event, "email")
                if datetime.fromisoformat(
                    timestamp(event["receivedDateTime"])
                ) < now - timedelta(days=self.retention):
                    continue
                if event.get("hasAttachments"):
                    files = self.get(
                        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/"
                        + quote(event["id"], safe="")
                        + "/attachments?$select=name,contentType,size,isInline",
                        token,
                    )
                    facts["attachments"] = [
                        {
                            "name": str(f.get("name", ""))[:150],
                            "type": str(f.get("contentType", ""))[:100],
                            "size": f.get("size", 0),
                        }
                        for f in files.get("value", [])[:30]
                    ]
            events.append((str(event["id"]), facts))
        more = response.get("@odata.nextLink")
        if more:
            cp["page"] = self.graph_link(more, path)
        else:
            cp.pop("page", None)
            if delta:
                cp["delta"] = self.graph_link(response["@odata.deltaLink"], path)
        return Page(events, cp, not bool(more), full)
