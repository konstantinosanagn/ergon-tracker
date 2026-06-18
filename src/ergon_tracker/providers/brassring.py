"""BrassRing (IBM / Infinite Kenexa "Infinite BrassRing") career-site provider.

BrassRing's new UI ("TGnewUI", an AngularJS SPA on ASP.NET MVC) serves job RECORDS as JSON
from a public, no-auth AJAX endpoint — but it is CSRF-protected and session-heavy, so a
two-step, no-browser handshake is required:

**Step A — bootstrap (plain GET, no auth)**::

    GET https://{host}/TGnewUI/Search/Home/Home?partnerid={pid}&siteid={sid}

sets the session cookies (``tg_session``/``tg_rft``…, kept by the shared httpx client) and, in
the HTML, exposes two values we need plus the tenant field map:

* ``<input name="__RequestVerificationToken" value="…">`` — the anti-forgery token, echoed
  back as the **``RFT``** request header on the POST (without it the POST 500s / returns 0).
* ``<input id="CookieValue" value="^…">`` — the encrypted session value, echoed in the body as
  ``encryptedSessionValue``.
* ``JobFieldsToDisplay`` (per-tenant Solr field map) + ``PartnerName`` (company).

**Step B — list jobs (POST JSON, paginated)**::

    POST https://{host}/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs
    RFT: {token}                       # header
    {... "SortType":"LastUpdated", "pageNumber":{N}, "encryptedSessionValue":"^…" ...}

Returns ``200 application/json``: ``{"Jobs":{"Job":[…]}, "JobsCount":{total}}``. **50 jobs per
page** (fixed); page off ``JobsCount`` with 1-indexed ``pageNumber``. This one endpoint serves
page 1 too (the SPA uses ``MatchedJobs`` for page 1, but ``ProcessSortAndShowMoreJobs`` returns
the identical shape for every page with a consistent ``LastUpdated`` sort).

Each job's fields live in a flat ``Questions[]`` array of ``{QuestionName, Value}`` pairs whose
names vary per tenant (Solr field codes). We resolve title/description/location field names from
``JobFieldsToDisplay`` (deterministic source of truth) with universal fallbacks: ``reqid`` is
the job id everywhere; ``Link`` is the apply URL; ``lastupdated`` (``%d-%b-%Y``) is an *update*
date → ``updated_at`` (``posted_at`` stays ``None`` — not invented). No salary/employment-type
fields are exposed → ``None`` / ``UNKNOWN``.

Token shape: ``"{host}|{partnerid}|{siteid}"`` (e.g.
``"sjobs.brassring.com|25416|5429"``). A 2-part ``"{partnerid}|{siteid}"`` defaults the host to
``sjobs.brassring.com``. Live-verified: ADM (25416/5429, 286 jobs), Fairfax County Public
Schools (25103/5019, 603 jobs).
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from html import unescape
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from selectolax.parser import HTMLParser

from ..models import JobPosting, Location, RawJob, RemoteType, SearchQuery
from .base import BaseProvider, register

if TYPE_CHECKING:
    from ..http import AsyncFetcher

__all__ = ["BrassRingProvider"]

_DEFAULT_HOST = "sjobs.brassring.com"
_HOME = "https://{host}/TGnewUI/Search/Home/Home?partnerid={pid}&siteid={sid}"
_LIST = "https://{host}/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs"

# A BrassRing host (sjobs / krb-sjobs / {company}.brassring.com).
_BRASSRING_HOST_RE = re.compile(r"(^|\.)brassring\.com$", re.IGNORECASE)
# Tenant field map + company name in the bootstrap HTML (HTML-entity-encoded JSON).
_FIELDMAP_RE = re.compile(r'"JobFieldsToDisplay":(\{.*?\})')
_PARTNER_RE = re.compile(r'"PartnerName":"([^"]*)"')
# Location-ish question names (in addition to the tenant's Position3 fields).
_LOC_NAMES = ("location", "city", "state", "region", "country", "formtext8", "formtext10")
# Field names that are NOT location even when listed in Position3.
_NOT_LOCATION = {"department", "reqid", "autoreq", "jobtitle"}


def _parse_date(value: Any) -> datetime | None:
    """Parse BrassRing's ``18-Jun-2026`` date to a tz-aware datetime, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip()[:11], "%d-%b-%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _clean(value: Any) -> str | None:
    """Return a stripped non-empty string, else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


@register("brassring")
class BrassRingProvider(BaseProvider):
    name = "brassring"

    PER_PAGE = 50  # server-fixed page size for ProcessSortAndShowMoreJobs
    MAX_PAGES = 200  # bound full pulls (=10k jobs)

    @classmethod
    def matches(cls, url_or_host: str) -> str | None:
        """Recognise a BrassRing URL -> ``"{host}|{partnerid}|{siteid}"``, else None.

        Requires a ``*.brassring.com`` host and both ``partnerid`` + ``siteid`` query params
        (a bare host can't identify a tenant).
        """
        candidate = url_or_host if "//" in url_or_host else "//" + url_or_host
        parts = urlsplit(candidate)
        host = parts.netloc.split("@")[-1].split(":")[0].lower()
        if not host or not _BRASSRING_HOST_RE.search(host):
            return None
        qs = parse_qs(parts.query)
        pid = (qs.get("partnerid") or qs.get("partnerId") or [""])[0].strip()
        sid = (qs.get("siteid") or qs.get("siteId") or [""])[0].strip()
        if not pid or not sid:
            return None
        return f"{host}|{pid}|{sid}"

    async def fetch(self, token: str, query: SearchQuery, fetcher: AsyncFetcher) -> list[RawJob]:
        host, pid, sid = self._split(token)
        if not (host and pid and sid):
            return []

        # Step A — bootstrap: cookies + anti-forgery token + tenant field map.
        try:
            html = await fetcher.get_text(_HOME.format(host=host, pid=pid, sid=sid))
        except Exception:
            return []
        rft, cookie_value = self._bootstrap_tokens(html)
        if not rft:
            return []  # no CSRF token -> the list POST can't succeed
        fields = self._field_map(html)
        company = self._company(html, pid)

        # Step B — page the JSON list endpoint.
        list_url = _LIST.format(host=host)
        headers = {"RFT": rft, "X-Requested-With": "XMLHttpRequest"}
        limit = query.limit
        seen: set[str] = set()
        raws: list[RawJob] = []
        total_pages = self.MAX_PAGES

        for page in range(1, self.MAX_PAGES + 1):
            if page > total_pages:
                break
            body = self._list_body(pid, sid, cookie_value, page)
            try:
                data = await fetcher.post_json(list_url, json=body, headers=headers)
            except Exception:
                break
            if not isinstance(data, dict):
                break

            if page == 1:
                count = data.get("JobsCount")
                if isinstance(count, int) and count >= 0:
                    total_pages = min(self.MAX_PAGES, max(1, math.ceil(count / self.PER_PAGE)))

            jobs = self._jobs(data)
            if not jobs:
                break
            new = 0
            for job in jobs:
                flat = self._flatten(job)
                jid = _clean(flat.get("reqid")) or _clean(flat.get("autoreq"))
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                new += 1
                raws.append(self._to_raw(job, flat, fields, company, host))
                if limit is not None and len(raws) >= limit:
                    return raws[:limit]
            if new == 0:
                break  # no fresh records -> past the end
        return raws

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _split(token: str) -> tuple[str, str, str]:
        """Split ``"{host}|{pid}|{sid}"`` or ``"{pid}|{sid}"`` (host defaults sjobs)."""
        parts = [p.strip() for p in token.split("|")]
        if len(parts) == 3:
            host, pid, sid = parts
            return (host.lower() or _DEFAULT_HOST), pid, sid
        if len(parts) == 2:
            pid, sid = parts
            return _DEFAULT_HOST, pid, sid
        return "", "", ""

    @staticmethod
    def _bootstrap_tokens(html: str) -> tuple[str | None, str]:
        """Extract the anti-forgery token and the ``#CookieValue`` session value."""
        tree = HTMLParser(html)
        rft = None
        token_node = tree.css_first('input[name="__RequestVerificationToken"]')
        if token_node is not None:
            rft = _clean(token_node.attributes.get("value"))
        cookie_value = ""
        cv_node = tree.css_first("input#CookieValue")
        if cv_node is not None:
            cookie_value = cv_node.attributes.get("value") or ""
        return rft, cookie_value

    @staticmethod
    def _field_map(html: str) -> dict[str, Any]:
        """Parse the tenant ``JobFieldsToDisplay`` map (title/summary/location field codes)."""
        m = _FIELDMAP_RE.search(unescape(html))
        if not m:
            return {}
        try:
            parsed = json.loads(m.group(1))
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _company(html: str, pid: str) -> str:
        """Company label from ``PartnerName`` in the bootstrap HTML, else the partnerid."""
        m = _PARTNER_RE.search(unescape(html))
        name = _clean(m.group(1)) if m else None
        return name or f"partner-{pid}"

    def _list_body(self, pid: str, sid: str, cookie_value: str, page: int) -> dict[str, Any]:
        # No server-side keyword: BrassRing returns the whole board and the orchestrator's
        # client-side query.matches() applies the keyword filter (see SearchQuery docstring).
        return {
            "partnerId": pid,
            "siteId": sid,
            "keyword": "",
            "location": "",
            "keywordCustomSolrFields": "",
            "locationCustomSolrFields": "",
            "linkId": "",
            "Latitude": 0,
            "Longitude": 0,
            "facetfilterfields": {"Facet": []},
            "powersearchoptions": {"PowerSearchOption": []},
            "SortType": "LastUpdated",
            "pageNumber": page,
            "encryptedSessionValue": cookie_value,
        }

    @staticmethod
    def _jobs(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the ``Jobs.Job`` list, tolerant of null/shape variants."""
        container = data.get("Jobs")
        jobs = container.get("Job") if isinstance(container, dict) else container
        if isinstance(jobs, list):
            return [j for j in jobs if isinstance(j, dict)]
        return []

    @staticmethod
    def _flatten(job: dict[str, Any]) -> dict[str, str]:
        """Flatten a job's ``Questions[]`` ``{QuestionName, Value}`` pairs into a dict."""
        out: dict[str, str] = {}
        for q in job.get("Questions") or []:
            if not isinstance(q, dict):
                continue
            name = q.get("QuestionName")
            value = q.get("Value")
            if isinstance(name, str) and name and isinstance(value, str):
                out.setdefault(name.lower(), value)
        return out

    def _to_raw(
        self,
        job: dict[str, Any],
        flat: dict[str, str],
        fields: dict[str, Any],
        company: str,
        host: str,
    ) -> RawJob:
        jid = _clean(flat.get("reqid")) or _clean(flat.get("autoreq")) or ""
        payload = {**flat, "_fields": fields, "_link": job.get("Link")}
        return RawJob(
            source=self.name,
            source_job_id=jid,
            company=company,
            token=host,
            url=_clean(job.get("Link")),
            payload=payload,
        )

    def normalize(self, raw: RawJob) -> JobPosting:
        flat = raw.payload
        fields = flat.get("_fields") or {}

        title_field = str(fields.get("JobTitle") or "jobtitle").lower()
        title = _clean(flat.get(title_field)) or _clean(flat.get("jobtitle")) or ""

        summary_field = str(fields.get("Summary") or "").lower()
        description = (
            _clean(flat.get(summary_field))
            or _clean(flat.get("jobdescription"))
            or _clean(flat.get("formtext3"))
        )

        locations = self._locations(flat, fields, title_field)
        remote = (
            RemoteType.REMOTE if any(loc.is_remote for loc in locations) else RemoteType.UNKNOWN
        )

        return JobPosting.create(
            source=self.name,
            source_job_id=raw.source_job_id,
            company=raw.company,
            title=title,
            fetched_at=raw.fetched_at,
            apply_url=raw.url,
            locations=locations,
            remote=remote,
            department=_clean(flat.get("department")),
            salary=None,
            posted_at=None,  # BrassRing exposes only "lastupdated" -> updated_at
            updated_at=_parse_date(flat.get("lastupdated")),
            description_html=description,
            description_text=None,
            raw=raw.payload,
        )

    @staticmethod
    def _locations(
        flat: dict[str, str], fields: dict[str, Any], title_field: str
    ) -> list[Location]:
        """Build a location from the tenant's ``Position3`` fields + literal location names."""
        names: list[str] = []
        pos3 = fields.get("Position3")
        if isinstance(pos3, list):
            names.extend(str(n).lower() for n in pos3 if isinstance(n, str))
        names.extend(_LOC_NAMES)

        skip = _NOT_LOCATION | {title_field}
        values: list[str] = []
        for name in names:
            if name in skip:
                continue
            value = _clean(flat.get(name))
            if value and value not in values:
                values.append(value)
        if not values:
            return []
        label = ", ".join(values)
        return [Location(raw=label, is_remote="remote" in label.lower())]
