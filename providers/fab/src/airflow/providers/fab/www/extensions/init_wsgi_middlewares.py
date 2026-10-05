# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

from typing import TYPE_CHECKING

from werkzeug.middleware.proxy_fix import ProxyFix

from airflow.providers.common.compat.sdk import conf

if TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse, WSGIApplication, WSGIEnvironment
    from flask import Flask


def _keep_mounted_script_name(original: str, forwarded: str) -> str:
    """
    Keep the WSGI mount path when ProxyFix replaces ``SCRIPT_NAME``.

    ``ProxyFix`` assigns ``X-Forwarded-Prefix`` to ``SCRIPT_NAME`` outright.
    The FAB app is mounted at ``/auth``, and FastAPI's ``root_path`` (the
    ``[api] base_url`` path) is already part of that script name, so the
    replacement drops ``/auth`` and ``url_for`` omits it. When the forwarded
    prefix is a different base path, only the ``/auth`` mount is kept, so
    the internal base path is not repeated.
    """
    original = original.rstrip("/")
    forwarded = forwarded.rstrip("/")
    if not forwarded or forwarded == original:
        return original
    # ``root_path`` already included this prefix; the remainder is the mount.
    if original.startswith(f"{forwarded}/"):
        return original
    # Keep the FAB mount. Joining the whole script name would repeat an internal base path.
    if original.endswith("/auth"):
        if forwarded.endswith("/auth"):
            return forwarded
        return f"{forwarded}/auth"
    if original and not forwarded.endswith(original):
        suffix = original if original.startswith("/") else f"/{original}"
        return f"{forwarded}{suffix}"
    return forwarded


class _KeepMountedScriptName:
    """Reapply the mount path after :class:`~werkzeug.middleware.proxy_fix.ProxyFix`."""

    def __init__(self, app: WSGIApplication) -> None:
        self.app = app

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse):
        orig = environ.get("werkzeug.proxy_fix.orig") or {}
        original = orig.get("SCRIPT_NAME") or ""
        forwarded = environ.get("SCRIPT_NAME") or ""
        environ["SCRIPT_NAME"] = _keep_mounted_script_name(original, forwarded)
        return self.app(environ, start_response)


def init_wsgi_middleware(flask_app: Flask) -> None:
    """Handle X-Forwarded-* headers and base_url support."""
    # Apply ProxyFix middleware
    if conf.getboolean("fab", "ENABLE_PROXY_FIX"):
        flask_app.wsgi_app = ProxyFix(  # type: ignore
            _KeepMountedScriptName(flask_app.wsgi_app),
            x_for=conf.getint("fab", "PROXY_FIX_X_FOR", fallback=1),
            x_proto=conf.getint("fab", "PROXY_FIX_X_PROTO", fallback=1),
            x_host=conf.getint("fab", "PROXY_FIX_X_HOST", fallback=1),
            x_port=conf.getint("fab", "PROXY_FIX_X_PORT", fallback=1),
            x_prefix=conf.getint("fab", "PROXY_FIX_X_PREFIX", fallback=1),
        )
