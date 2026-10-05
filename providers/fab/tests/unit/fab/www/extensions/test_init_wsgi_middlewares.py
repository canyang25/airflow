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

import pytest
from flask import Flask, url_for
from werkzeug.test import Client

from airflow.providers.fab.www.extensions.init_wsgi_middlewares import init_wsgi_middleware

from tests_common.test_utils.config import conf_vars

# Starlette's ``/auth`` mount plus FastAPI ``root_path`` (from ``[api] base_url``)
# arrives as SCRIPT_NAME. ``X-Forwarded-Prefix`` is the external subpath only.
MOUNTED_SCRIPT_NAME = "/auth"
SUBPATH_WITH_MOUNT = "/myns/myrelease/auth"
SUBPATH_PREFIX = "/myns/myrelease"


def build_client() -> Client:
    app = Flask(__name__)

    @app.route("/roles/list/")
    def roles_list():
        return url_for("roles_add")

    @app.route("/roles/add")
    def roles_add():
        return "add"

    init_wsgi_middleware(app)
    return Client(app)


@conf_vars({("fab", "enable_proxy_fix"): "True"})
@pytest.mark.parametrize(
    ("script_name", "headers", "expected_url"),
    [
        pytest.param(MOUNTED_SCRIPT_NAME, {}, "/auth/roles/add", id="mounted-without-forwarded-prefix"),
        pytest.param(
            SUBPATH_WITH_MOUNT,
            {"X-Forwarded-Prefix": SUBPATH_PREFIX},
            "/myns/myrelease/auth/roles/add",
            id="root-path-already-includes-forwarded-prefix",
        ),
        pytest.param(
            SUBPATH_WITH_MOUNT,
            {"X-Forwarded-Prefix": f"{SUBPATH_PREFIX}/"},
            "/myns/myrelease/auth/roles/add",
            id="forwarded-prefix-with-trailing-slash",
        ),
        pytest.param(
            SUBPATH_WITH_MOUNT,
            {"X-Forwarded-Prefix": "/other"},
            "/other/auth/roles/add",
            id="unrelated-forwarded-prefix-keeps-auth-mount",
        ),
        pytest.param(
            "/auth/auth",
            {"X-Forwarded-Prefix": "/auth"},
            "/auth/auth/roles/add",
            id="auth-base-path-with-forwarded-auth-prefix",
        ),
        pytest.param(
            MOUNTED_SCRIPT_NAME,
            {"X-Forwarded-Prefix": SUBPATH_WITH_MOUNT},
            "/myns/myrelease/auth/roles/add",
            id="forwarded-prefix-already-includes-auth-mount",
        ),
        pytest.param(
            MOUNTED_SCRIPT_NAME,
            {"X-Forwarded-Prefix": SUBPATH_PREFIX},
            "/myns/myrelease/auth/roles/add",
            id="forwarded-prefix-with-mount-only-script-name",
        ),
        pytest.param(
            "",
            {"X-Forwarded-Prefix": SUBPATH_PREFIX},
            "/myns/myrelease/roles/add",
            id="unmounted-behind-subpath-proxy",
        ),
        pytest.param(
            MOUNTED_SCRIPT_NAME,
            {"X-Forwarded-Prefix": "/auth"},
            "/auth/roles/add",
            id="forwarded-prefix-equals-mount-path",
        ),
    ],
)
def test_generated_urls_keep_auth_mount_behind_proxy(script_name, headers, expected_url):
    response = build_client().get(
        "/roles/list/",
        environ_overrides={"SCRIPT_NAME": script_name},
        headers=headers,
    )

    assert response.text == expected_url


@conf_vars({("fab", "enable_proxy_fix"): "False"})
def test_forwarded_prefix_ignored_when_proxy_fix_disabled():
    response = build_client().get(
        "/roles/list/",
        environ_overrides={"SCRIPT_NAME": SUBPATH_WITH_MOUNT},
        headers={"X-Forwarded-Prefix": SUBPATH_PREFIX},
    )

    assert response.text == "/myns/myrelease/auth/roles/add"
