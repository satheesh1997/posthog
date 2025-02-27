import base64
import datetime
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.timezone import now

from posthog.models import Plugin, PluginAttachment, PluginConfig
from posthog.plugins.test.mock import mocked_plugin_requests_get
from posthog.plugins.test.plugin_archives import HELLO_WORLD_PLUGIN_GITHUB_ATTACHMENT_ZIP, HELLO_WORLD_PLUGIN_GITHUB_ZIP
from posthog.redis import get_client

from .base import APIBaseTest


def mocked_plugin_reload(*args, **kwargs):
    pass


@mock.patch("posthog.api.plugin.reload_plugins_on_workers", side_effect=mocked_plugin_reload)
@mock.patch("requests.get", side_effect=mocked_plugin_requests_get)
class TestPluginAPI(APIBaseTest):
    def test_create_plugin_auth(self, mock_get, mock_reload):
        repo_url = "https://github.com/PostHog/helloworldplugin"
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 400)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 400)
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 201)
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 400)  # already installed, tested separately below

    def test_update_plugin_auth(self, mock_get, mock_reload):
        repo_url = "https://github.com/PostHog/helloworldplugin"
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 201)
        api_url = "/api/plugin/{}".format(response.data["id"])  # type: ignore
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.patch(api_url, {"url": repo_url})
            self.assertEqual(response.status_code, 200)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.patch(api_url, {"url": repo_url})
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.patch(api_url, {"url": repo_url})
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.patch(api_url, {"url": repo_url})
            self.assertEqual(response.status_code, 200)

    def test_delete_plugin_auth(self, mock_get, mock_reload):
        repo_url = "https://github.com/PostHog/helloworldplugin"
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 201)
        api_url = "/api/plugin/{}".format(response.data["id"])  # type: ignore

        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.delete(api_url)
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.delete(api_url)
            self.assertEqual(response.status_code, 404)

        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.delete(api_url)
            self.assertEqual(response.status_code, 204)

        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):  # create again
            response = self.client.post("/api/plugin/", {"url": repo_url})
            self.assertEqual(response.status_code, 201)
        api_url = "/api/plugin/{}".format(response.data["id"])  # type: ignore
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.delete(api_url)
            self.assertEqual(response.status_code, 204)

    def test_create_plugin_repo_url(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            self.assertEqual(mock_reload.call_count, 0)
            response = self.client.post("/api/plugin/", {"url": "https://github.com/PostHog/helloworldplugin"})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(
                response.data,
                {
                    "id": response.data["id"],  # type: ignore
                    "name": "helloworldplugin",
                    "description": "Greet the World and Foo a Bar, JS edition!",
                    "url": "https://github.com/PostHog/helloworldplugin",
                    "config_schema": {
                        "bar": {"name": "What's in the bar?", "type": "string", "default": "baz", "required": False,},
                    },
                    "tag": HELLO_WORLD_PLUGIN_GITHUB_ZIP[0],
                    "error": None,
                },
            )
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(mock_reload.call_count, 1)

            self.client.delete("/api/plugin/{}".format(response.data["id"]))  # type: ignore
            self.assertEqual(Plugin.objects.count(), 0)
            self.assertEqual(mock_reload.call_count, 2)

    def test_create_plugin_commit_url(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True):
            self.assertEqual(mock_reload.call_count, 0)
            response = self.client.post(
                "/api/plugin/",
                {
                    "url": "https://github.com/PostHog/helloworldplugin/commit/{}".format(
                        HELLO_WORLD_PLUGIN_GITHUB_ZIP[0]
                    )
                },
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(
                response.data,
                {
                    "id": response.data["id"],  # type: ignore
                    "name": "helloworldplugin",
                    "description": "Greet the World and Foo a Bar, JS edition!",
                    "url": "https://github.com/PostHog/helloworldplugin",
                    "config_schema": {
                        "bar": {"name": "What's in the bar?", "type": "string", "default": "baz", "required": False,},
                    },
                    "tag": HELLO_WORLD_PLUGIN_GITHUB_ZIP[0],
                    "error": None,
                },
            )
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(mock_reload.call_count, 1)

            response2 = self.client.patch(
                "/api/plugin/{}".format(response.data["id"]),  # type: ignore
                {
                    "url": "https://github.com/PostHog/helloworldplugin/commit/{}".format(
                        HELLO_WORLD_PLUGIN_GITHUB_ATTACHMENT_ZIP[0]
                    )
                },
            )
            self.assertEqual(response2.status_code, 200)
            self.assertEqual(
                response2.data,
                {
                    "id": response.data["id"],  # type: ignore
                    "name": "helloworldplugin",
                    "description": "Greet the World and Foo a Bar, JS edition, vol 2!",
                    "url": "https://github.com/PostHog/helloworldplugin",
                    "config_schema": {
                        "bar": {"name": "What's in the bar?", "type": "string", "default": "baz", "required": False,},
                        "foodb": {"name": "Upload your database", "type": "attachment", "required": False,},
                    },
                    "tag": HELLO_WORLD_PLUGIN_GITHUB_ATTACHMENT_ZIP[0],
                    "error": None,
                },
            )
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(mock_reload.call_count, 2)

    def test_plugin_repository(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.get("/api/plugin/repository/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.data,
                [
                    {
                        "name": "posthog-currency-normalization-plugin",
                        "url": "https://github.com/posthog/posthog-currency-normalization-plugin",
                        "description": "Normalise monerary values into a base currency",
                        "verified": False,
                        "maintainer": "official",
                    },
                    {
                        "name": "helloworldplugin",
                        "url": "https://github.com/posthog/helloworldplugin",
                        "description": "Greet the World and Foo a Bar",
                        "verified": True,
                        "maintainer": "community",
                    },
                ],
            )
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.get("/api/plugin/repository/")
            self.assertEqual(response.status_code, 400)

    def test_plugin_status(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.get("/api/plugin/status/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {"status": "offline"})

            get_client().set("@posthog-plugin-server/ping", now().isoformat())
            response = self.client.get("/api/plugin/status/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, {"status": "online"})

        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.get("/api/plugin/status/")
            self.assertEqual(response.status_code, 400)

    def test_create_plugin_config(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            self.assertEqual(mock_reload.call_count, 0)
            response = self.client.post("/api/plugin/", {"url": "https://github.com/PostHog/helloworldplugin"})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(PluginConfig.objects.count(), 0)
            plugin_id = response.data["id"]  # type: ignore
            response = self.client.post(
                "/api/plugin_config/",
                {"plugin": plugin_id, "enabled": True, "order": 0, "config": json.dumps({"bar": "moop"})},
            )
            plugin_config_id = response.data["id"]  # type: ignore
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(PluginConfig.objects.count(), 1)
            self.assertEqual(
                response.data,
                {
                    "id": plugin_config_id,
                    "plugin": plugin_id,
                    "enabled": True,
                    "order": 0,
                    "config": {"bar": "moop"},
                    "error": None,
                },
            )
            response = self.client.patch(
                "/api/plugin_config/{}".format(plugin_config_id),
                {"enabled": False, "order": 1, "config": json.dumps({"bar": "soup"})},
            )
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(PluginConfig.objects.count(), 1)
            self.assertEqual(
                response.data,
                {
                    "id": plugin_config_id,
                    "plugin": plugin_id,
                    "enabled": False,
                    "order": 1,
                    "config": {"bar": "soup"},
                    "error": None,
                },
            )
            self.client.delete("/api/plugin_config/{}".format(plugin_config_id))
            self.assertEqual(Plugin.objects.count(), 1)
            self.assertEqual(PluginConfig.objects.count(), 1)

    def test_create_plugin_config_auth(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": "https://github.com/PostHog/helloworldplugin"})
            plugin_id = response.data["id"]  # type: ignore
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.post(
                "/api/plugin_config/",
                {"plugin": plugin_id, "enabled": True, "order": 0, "config": json.dumps({"bar": "moop"})},
            )
            self.assertEqual(response.status_code, 400)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.post(
                "/api/plugin_config/",
                {"plugin": plugin_id, "enabled": True, "order": 0, "config": json.dumps({"bar": "moop"})},
            )
            self.assertEqual(response.status_code, 400)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post(
                "/api/plugin_config/",
                {"plugin": plugin_id, "enabled": True, "order": 0, "config": json.dumps({"bar": "moop"})},
            )
            self.assertEqual(response.status_code, 201)

    def test_update_plugin_config_auth(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": "https://github.com/PostHog/helloworldplugin"})
            plugin_id = response.data["id"]  # type: ignore
            response = self.client.post(
                "/api/plugin_config/",
                {"plugin": plugin_id, "enabled": True, "order": 0, "config": json.dumps({"bar": "moop"})},
            )
            plugin_config_id = response.data["id"]  # type: ignore
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.patch(
                "/api/plugin_config/{}".format(plugin_config_id),
                {"enabled": False, "order": 1, "config": json.dumps({"bar": "soup"})},
            )
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.patch(
                "/api/plugin_config/{}".format(plugin_config_id),
                {"enabled": False, "order": 1, "config": json.dumps({"bar": "soup"})},
            )
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.patch(
                "/api/plugin_config/{}".format(plugin_config_id),
                {"enabled": False, "order": 1, "config": json.dumps({"bar": "soup"})},
            )
            self.assertEqual(response.status_code, 200)

    def test_delete_plugin_config_auth(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.post("/api/plugin/", {"url": "https://github.com/PostHog/helloworldplugin"})
            plugin_id = response.data["id"]  # type: ignore
            response = self.client.post(
                "/api/plugin_config/",
                {"plugin": plugin_id, "enabled": True, "order": 0, "config": json.dumps({"bar": "moop"})},
            )
            plugin_config_id = response.data["id"]  # type: ignore
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.delete("/api/plugin_config/{}".format(plugin_config_id))
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=False):
            response = self.client.delete("/api/plugin_config/{}".format(plugin_config_id))
            self.assertEqual(response.status_code, 404)
        with self.settings(PLUGINS_INSTALL_VIA_API=False, PLUGINS_CONFIGURE_VIA_API=True):
            response = self.client.delete("/api/plugin_config/{}".format(plugin_config_id))
            self.assertEqual(response.status_code, 204)

    def test_plugin_config_attachment(self, mock_get, mock_reload):
        with self.settings(PLUGINS_INSTALL_VIA_API=True, PLUGINS_CONFIGURE_VIA_API=True):
            tmp_file_1 = SimpleUploadedFile(
                "foo-database-1.db",
                base64.b64decode(HELLO_WORLD_PLUGIN_GITHUB_ZIP[1]),
                content_type="application/octet-stream",
            )
            tmp_file_2 = SimpleUploadedFile(
                "foo-database-2.db",
                base64.b64decode(HELLO_WORLD_PLUGIN_GITHUB_ATTACHMENT_ZIP[1]),
                content_type="application/zip",
            )

            self.assertEqual(PluginAttachment.objects.count(), 0)
            response = self.client.post(
                "/api/plugin/",
                {
                    "url": "https://github.com/PostHog/helloworldplugin/commit/{}".format(
                        HELLO_WORLD_PLUGIN_GITHUB_ATTACHMENT_ZIP[0]
                    )
                },
                format="multipart",
            )
            plugin_id = response.data["id"]  # type: ignore
            response = self.client.post(
                "/api/plugin_config/",
                {
                    "plugin": plugin_id,
                    "enabled": True,
                    "order": 0,
                    "config": json.dumps({"bar": "moop"}),
                    "add_attachment[foodb]": tmp_file_1,
                },
            )
            plugin_config_id = response.data["id"]  # type: ignore
            plugin_attachment_id = response.data["config"]["foodb"]["uid"]  # type: ignore

            response = self.client.get("/api/plugin_config/{}".format(plugin_config_id))
            self.assertEqual(
                response.data["config"],  # type: ignore
                {
                    "bar": "moop",
                    "foodb": {
                        "uid": plugin_attachment_id,
                        "saved": True,
                        "size": 1964,
                        "name": "foo-database-1.db",
                        "type": "application/octet-stream",
                    },
                },
            )

            response = self.client.patch(
                "/api/plugin_config/{}".format(plugin_config_id),
                {"add_attachment[foodb]": tmp_file_2},
                format="multipart",
            )
            self.assertEqual(PluginAttachment.objects.count(), 1)

            self.assertEqual(
                response.data["config"],  # type: ignore
                {
                    "bar": "moop",
                    "foodb": {
                        "uid": plugin_attachment_id,
                        "saved": True,
                        "size": 2279,
                        "name": "foo-database-2.db",
                        "type": "application/zip",
                    },
                },
            )

            response = self.client.patch(
                "/api/plugin_config/{}".format(plugin_config_id), {"remove_attachment[foodb]": True}, format="multipart"
            )
            self.assertEqual(response.data["config"], {"bar": "moop"})  # type: ignore
            self.assertEqual(PluginAttachment.objects.count(), 0)
