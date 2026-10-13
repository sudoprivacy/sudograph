"""GitLab's authenticated revision, review and CI interfaces."""

from __future__ import annotations

import base64
import json
from typing import override
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class GitLabError(ValueError):
    def __init__(self, message, *, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    @override
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GitLabError("GitLab redirected an authenticated request; register its canonical URL")


class Client:
    def __init__(self, url, token, *, allow_http=False, job_token=False):
        parsed = urlparse(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and not allow_http)
        ):
            raise GitLabError(
                "register an HTTPS GitLab URL; HTTP requires an explicit isolated profile"
            )
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
            raise GitLabError("provide a GitLab credential through the trusted transport")
        self.url, self.token = url.rstrip("/"), token
        self.header = "JOB-TOKEN" if job_token else "PRIVATE-TOKEN"
        self.opener = build_opener(NoRedirect())

    def request(self, path, *, method="GET", data=None, params=None):
        if not path.startswith("/") or path.startswith("//"):
            raise GitLabError("use a registered GitLab API path")
        url = self.url + "/api/v4" + path
        if params:
            url += "?" + urlencode(
                {k: str(v).lower() if type(v) is bool else v for k, v in params.items()}
            )
        payload = None if data is None else json.dumps(data).encode()
        request = Request(
            url,
            payload,
            {self.header: self.token, "Content-Type": "application/json"},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read(16 * 1024 * 1024 + 1)
                if len(body) > 16 * 1024 * 1024:
                    raise GitLabError("GitLab response exceeds the registered model limit")
                return json.loads(body) if body else None
        except HTTPError as exc:
            # GitLab error bodies and request URLs can contain private content.
            raise GitLabError(
                f"GitLab {method} request refused (HTTP {exc.code})", status=exc.code
            ) from None
        except (URLError, TimeoutError, ValueError) as exc:
            if isinstance(exc, GitLabError):
                raise
            raise GitLabError(
                "GitLab unavailable or returned an invalid response; no authority inferred"
            ) from None

    def pages(self, path, **params):
        result = []
        for page in range(1, 1001):
            batch = self.request(path, params={**params, "per_page": 100, "page": page})
            if not isinstance(batch, list):
                raise GitLabError("GitLab list response was not an array")
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise GitLabError("GitLab listing exceeded the deployment limit")

    def file(self, project, path, ref):
        result = self.request(
            f"/projects/{project}/repository/files/{quote(path, safe='')}", params={"ref": ref}
        )
        try:
            if result["encoding"] != "base64":
                raise ValueError
            return base64.b64decode(result["content"], validate=True).decode("utf8")
        except (ValueError, KeyError, UnicodeError):
            raise GitLabError("registered model must be a UTF-8 GitLab file") from None

    def actor(self):
        result = self.request("/user")
        if type(result.get("id")) is not int or result.get("state") != "active":
            raise GitLabError("GitLab identity is not active")
        return result

    def mr(self, project, iid):
        if type(iid) is not int or iid < 1:
            raise GitLabError("use a positive proposal number")
        return self.request(f"/projects/{project}/merge_requests/{iid}")
