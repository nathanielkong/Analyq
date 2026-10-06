"""Exercise fresh containers without provider keys or the developer's database."""

import argparse
import http.cookiejar
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-tests", action="store_true")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    project = "analyq-smoke-" + uuid4().hex[:10]
    password = secrets.token_hex(32)
    origin = f"http://127.0.0.1:{args.port}"
    with tempfile.TemporaryDirectory(prefix="analyq-smoke-") as temporary:
        env_file = Path(temporary) / "container.env"
        env_file.write_text(
            f"POSTGRES_PASSWORD={password}\n"
            f"AUTH_SESSION_SECRET={secrets.token_hex(32)}\n"
            "APP_ENV=production\nREQUIRE_AUTH=true\nAUTH_COOKIE_SECURE=false\n"
            f"BACKEND_CORS_ORIGINS={origin}\nWEB_PORT={args.port}\n"
            "WEB_BIND=127.0.0.1\n"
        )
        env_file.chmod(0o600)
        environment = {**os.environ, "DEPLOY_ENV_FILE": str(env_file)}
        for key in (
            "POSTGRES_PASSWORD",
            "REQUIRE_AUTH",
            "WEB_BIND",
            "WEB_PORT",
            "COMPOSE_PROFILES",
        ):
            environment.pop(key, None)
        # A developer's deployment image overrides must not affect synthetic tests.
        environment["API_IMAGE"] = "analyq-api:local"
        environment["WEB_IMAGE"] = "analyq-web:local"
        compose = [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "compose.deploy.yml"),
            "-p",
            project,
        ]

        def run(*command, capture=False):
            return subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=True,
                text=True,
                capture_output=capture,
            )

        cookies = http.cookiejar.CookieJar()
        browser = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies)
        )

        def request(path, body=None, method=None):
            payload = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(
                origin + path,
                data=payload,
                method=method,
                headers={"Content-Type": "application/json", "Origin": origin},
            )
            with browser.open(req, timeout=15) as response:
                return response.status, response.read(), response.headers

        try:
            run(*compose, "up", "--build", "-d", "--wait", "--wait-timeout", "180")
            status, html, _ = request("/")
            assert status == 200 and b'id="root"' in html
            assert json.loads(request("/api/health")[1])["status"] == "ok"
            run(
                *compose,
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "import os; from pathlib import Path; assert os.getuid() != 0; assert not Path('/app/.env').exists()",
            )
            # Sensitive files must never become served static assets.
            assert request("/.env")[1] == html
            try:
                request("/api/chat/sessions")
                raise AssertionError("Guest access was not blocked")
            except urllib.error.HTTPError as error:
                assert error.code == 401
            _, _, headers = request(
                "/api/auth/register",
                {
                    "username": "container_test",
                    "password": secrets.token_hex(24),
                },
            )
            assert "HttpOnly" in headers["Set-Cookie"]
            assert "SameSite=lax" in headers["Set-Cookie"]
            session = json.loads(
                request("/api/chat/sessions", {"title": "Container persistence test"})[
                    1
                ]
            )
            assert any(
                row["id"] == session["id"]
                for row in json.loads(request("/api/chat/sessions")[1])
            )
            run(*compose, "up", "-d", "--no-deps", "--force-recreate", "--wait", "db")
            run(*compose, "up", "-d", "--no-deps", "--force-recreate", "--wait", "api")
            for attempt in range(30):
                try:
                    rows = json.loads(request("/api/chat/sessions")[1])
                    assert any(row["id"] == session["id"] for row in rows)
                    break
                except (urllib.error.URLError, AssertionError):
                    if attempt == 29:
                        raise
                    time.sleep(1)
            if args.backend_tests:
                run(
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    f"{project}_default",
                    "-e",
                    f"DATABASE_URL=postgresql+psycopg://analyq:{password}@db:5432/analyq",
                    "-e",
                    "ANALYQ_POSTGRES_TEST=1",
                    "analyq-api:test",
                )
            request("/api/auth/session", method="DELETE")
            assert not list(cookies)
            print(
                "PASS: containers, migrations, same-origin API, authentication, persistence and logout"
            )
        except Exception:
            subprocess.run(
                [*compose, "logs", "--tail=80", "api", "migrate", "web"],
                cwd=ROOT,
                env=environment,
                check=False,
            )
            raise
        finally:
            # Only the unique synthetic stack and its test volume are removed.
            run(*compose, "down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
