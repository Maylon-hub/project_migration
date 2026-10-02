import io
import json
import logging
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import requests

from studybr.api.client import ReadOnlyClient
from studybr.api.errors import PloneError as InventoryError
from studybr.inventory.cli import main
from studybr.inventory.comparison import compare_models, compare_page
from studybr.inventory.runner import MODELS, ROOTS, InventoryRunner
from studybr.inventory.snapshots import SnapshotStore, snapshot
from studybr.reconciliation import legacy_expectations
from studybr.reconciliation import read_approved_overlay as approved_names
from studybr.security import Redactor
from studybr.settings import ConfigurationError, Settings

clean = Redactor().public_data

BASE = "https://portal.test/site/++api++"
FAKE_TOKEN = "synthetic-test-credential"
FIXTURE = Path(__file__).parent / "fixtures" / "inventory-page.json"


def response(data=None, status=200, content_type="application/json", body=None, headers=None):
    result = requests.Response()
    result.status_code = status
    result.headers.update({"Content-Type": content_type, **(headers or {})})
    result._content = (
        body if body is not None else json.dumps(data if data is not None else {}).encode()
    )
    result._content_consumed = True
    return result


def page(path, items=None, total=None):
    return {
        "@id": "https://portal.test/site" + path,
        "id": path.rstrip("/").rsplit("/", 1)[-1],
        "@type": "Document",
        "language": path.split("/")[1],
        "items": items or [],
        "items_total": len(items or []) if total is None else total,
    }


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ, {"PLONE_BASE_URL": BASE, "PLONE_TOKEN": FAKE_TOKEN}, clear=True
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = ReadOnlyClient(Settings.from_env(rest_path="", timeout=(15, 15)))

    def test_write_methods_and_unknown_verbs_blocked_before_transport(self):
        with patch.object(requests.Session, "send") as send:
            for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "get"):
                with self.subTest(method=method), self.assertRaises(InventoryError) as caught:
                    self.client.request(method, "/pt-br")
                self.assertEqual(caught.exception.kind, "method_blocked")
            send.assert_not_called()

    def test_only_env_token_no_legacy_fallback(self):
        for missing in ("PLONE_TOKEN", "PLONE_BASE_URL"):
            with (
                self.subTest(missing=missing),
                patch.dict(os.environ, {missing: ""}),
                self.assertRaises(ConfigurationError),
            ):
                Settings.from_env(rest_path="", timeout=(15, 15))

    def test_settings_repr_hides_secret(self):
        self.assertNotIn(FAKE_TOKEN, repr(Settings.from_env(rest_path="", timeout=(15, 15))))
        self.assertNotIn(FAKE_TOKEN, repr(self.client))

    def test_invalid_settings_rejected(self):
        invalid_bases = (
            "http://portal.test/site/++api++",
            "https://user:pass@portal.test/site/++api++",
            BASE + "?token=x",
            "https://portal.test/site/../++api++",
            BASE + "#x",
        )
        for base in invalid_bases:
            with (
                self.subTest(base=base),
                patch.dict(os.environ, {"PLONE_BASE_URL": base}),
                self.assertRaises(ConfigurationError),
            ):
                Settings.from_env(rest_path="", timeout=(15, 15))
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ConfigurationError):
                Settings.from_env(timeout=(timeout, timeout))

    def test_token_whitespace_rejected(self):
        with (
            patch.dict(os.environ, {"PLONE_TOKEN": "bad\r\nheader"}),
            self.assertRaises(ConfigurationError),
        ):
            Settings.from_env(rest_path="", timeout=(15, 15))

    def test_bearer_prefix_normalized_only_in_memory(self):
        with patch.dict(os.environ, {"PLONE_TOKEN": "Bearer " + FAKE_TOKEN}):
            self.assertEqual(Settings.from_env(rest_path="", timeout=(15, 15)).token, FAKE_TOKEN)

    def test_direct_settings_cannot_bypass_https_or_secret_requirements(self):
        for base, token in (
            ("http://portal.test/site/++api++", FAKE_TOKEN),
            (BASE, ""),
            (BASE, "bad\nheader"),
        ):
            with self.subTest(base=base), self.assertRaises(ConfigurationError):
                Settings(base, token)

    def test_external_urls_prefix_traversal_and_login_rejected(self):
        bad_urls = (
            "https://evil.test/site/en",
            "http://portal.test/site/en",
            "//evil.test/site/en",
            "https://portal.test/other/en",
            "https://portal.test/site-other/en",
            "https://user:pass@portal.test/site/en",
            "https://portal.test:444/site/en",
            "/pt-br/../outside",
            "/pt-br/%2e%2e/outside",
            "/pt-br/%252e%252e/outside",
            "/pt-br/%5c..%5coutside",
            "/@login",
            "/@login-renew",
            "/@logout",
            "/pt-br/@workflow/publish",
            "/pt-br?token=secret",
            "/pt-br#fragment",
        )
        with patch.object(requests.Session, "send") as send:
            for url in bad_urls:
                with self.subTest(url=url), self.assertRaises(InventoryError):
                    self.client.get(url)
            send.assert_not_called()

    def test_frontend_urls_preserved_without_renaming_slug(self):
        url = "https://portal.test/site/pt-br/instituicoes_brasileiras/cefet_mg/vida_na_ies"
        self.assertEqual(self.client.resolve(url), url)

    def test_prepared_get_no_cookies_timeout_tls_and_no_redirects(self):
        seen = []

        def send(session, request, **kwargs):
            seen.append((session, request, kwargs))
            return response({"ok": True}, headers={"Set-Cookie": "session=private"})

        with patch.object(requests.Session, "send", autospec=True, side_effect=send):
            self.client.get("/pt-br")
            self.client.get("/en")
        for session, request, options in seen:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.headers["Accept"], "application/json")
            self.assertEqual(request.headers["Authorization"], "Bearer " + FAKE_TOKEN)
            self.assertNotIn("Cookie", request.headers)
            self.assertFalse(session.trust_env)
            self.assertEqual(options["timeout"], (15, 15))
            self.assertFalse(options["allow_redirects"])
            self.assertTrue(options["verify"])
            self.assertEqual(options["proxies"], {})
        self.assertFalse(seen[0][0].cookies)
        self.assertFalse(seen[1][0].cookies)

    def test_401_latches_stop_and_does_not_read_body(self):
        with patch.object(
            requests.Session, "send", return_value=response(status=401, body=b"private error")
        ) as send:
            for path in ("/pt-br", "/en", "/es"):
                with self.assertRaises(InventoryError) as caught:
                    self.client.get(path)
                self.assertEqual(caught.exception.status, 401)
            self.assertEqual(send.call_count, 1)

    def test_redirect_is_never_followed_even_same_host(self):
        with patch.object(
            requests.Session,
            "send",
            return_value=response(status=302, headers={"Location": "https://evil.test"}),
        ) as send:
            with self.assertRaises(InventoryError) as caught:
                self.client.get("/pt-br")
            self.assertEqual(caught.exception.kind, "redirect_blocked")
            self.assertEqual(send.call_count, 1)

    def test_errors_sanitized_and_no_auth_logging(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        data = {
            "type": "Unauthorized " + FAKE_TOKEN,
            "message": "Failure Authorization: Bearer " + FAKE_TOKEN,
        }
        with patch.object(requests.Session, "send", return_value=response(data, status=403)):
            with self.assertRaises(InventoryError) as caught:
                self.client.get("/pt-br")
        serialized = json.dumps(caught.exception.as_dict()) + output.getvalue()
        self.assertNotIn(FAKE_TOKEN, serialized)
        self.assertNotIn("Authorization:", serialized)

    def test_transport_error_never_echoes_request_or_token(self):
        with patch.object(
            requests.Session,
            "send",
            side_effect=requests.ConnectionError("Authorization: " + FAKE_TOKEN),
        ):
            with self.assertRaises(InventoryError) as caught:
                self.client.get("/pt-br")
        self.assertNotIn(FAKE_TOKEN, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_html_invalid_json_and_scalars_rejected(self):
        cases = (
            (response(content_type="text/html", body=b"<html>private</html>"), "non_json"),
            (response(body=b"bad json"), "invalid_json"),
            (response(data=5), "invalid_shape"),
        )
        for result, kind in cases:
            with (
                self.subTest(kind=kind),
                patch.object(requests.Session, "send", return_value=result),
                self.assertRaises(InventoryError) as caught,
            ):
                self.client.get("/pt-br")
            self.assertEqual(caught.exception.kind, kind)

    def test_types_list_and_schema_media_type_supported(self):
        for data, content_type in (
            ([{"id": "Document"}], "application/json"),
            ({"type": "object"}, "application/json+schema"),
        ):
            with patch.object(
                requests.Session, "send", return_value=response(data, content_type=content_type)
            ):
                self.assertEqual(self.client.get("/@types"), data)

    def test_request_budget_blocks_extra_get(self):
        client = ReadOnlyClient(Settings.from_env(rest_path="", max_requests=1))
        with patch.object(requests.Session, "send", return_value=response()) as send:
            client.get("/pt-br")
            with self.assertRaises(InventoryError):
                client.get("/en")
            self.assertEqual(send.call_count, 1)

    def test_credentials_removed_from_success_body(self):
        with patch.object(
            requests.Session,
            "send",
            return_value=response(
                {
                    "token": FAKE_TOKEN,
                    "nested": {"Authorization": "Bearer x", "message": FAKE_TOKEN},
                    "ok": True,
                }
            ),
        ):
            result = self.client.get("/pt-br")
        self.assertNotIn(FAKE_TOKEN, json.dumps(result))
        self.assertNotIn("token", result)
        self.assertNotIn("Authorization", result["nested"])


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_snapshot_structure_and_long_text_removed(self):
        result = snapshot(self.data, self.data["@id"], model=True)
        self.assertEqual(result["id"], "model")
        self.assertEqual(result["block_types"], {"heading": "title", "body": "slate"})
        self.assertEqual(result["block_order"], ["title", "slate"])
        self.assertEqual(result["children"][0]["id"], "about")
        self.assertNotIn("Synthetic paragraph", json.dumps(result))
        self.assertNotIn("fictional@example.test", json.dumps(result))

    def test_snapshot_normalization_does_not_mutate_input(self):
        original = deepcopy(self.data)
        snapshot(self.data, self.data["@id"], model=True)
        self.assertEqual(self.data, original)

    def test_common_page_omits_block_bodies_but_preserves_layout(self):
        result = snapshot(self.data, self.data["@id"])
        self.assertNotIn("blocks_structure", result)
        self.assertEqual(result["blocks_layout"], self.data["blocks_layout"])

    def test_empty_missing_and_false_are_distinct(self):
        result = snapshot(
            {"id": "vida_na_ies", "description": "", "is_folderish": False}, BASE + "/vida_na_ies"
        )
        self.assertEqual(result["description"], "")
        self.assertIs(result["is_folderish"], False)
        self.assertNotIn("language", result)
        self.assertEqual(result["slug"], "vida_na_ies")

    def test_schema_snapshot_preserves_required_and_types(self):
        data = {
            "type": "object",
            "required": ["title", "language"],
            "properties": {"title": {"type": "string"}},
            "description": "Very long explanatory text",
        }
        result = snapshot(data, BASE + "/@types/Document", kind="schema")
        self.assertEqual(result["structure"]["required"], ["title", "language"])
        self.assertEqual(result["structure"]["properties"]["title"]["type"], "string")

    def test_invalid_page_and_blocks_are_sanitized_errors(self):
        for data in ([], {"blocks": [1]}, {"blocks_layout": {"items": 7}}, {"@id": None}):
            with self.subTest(data=data), self.assertRaises(InventoryError):
                snapshot(data, BASE + "/pt-br")

    def test_raw_and_sanitized_separated_without_secret_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotStore(directory, "run")
            data = {**self.data, "Authorization": "Bearer dummy", "token": "dummy"}
            store.save(BASE + "/en/model", data, model=True)
            raw = next(store.raw.glob("*.json")).read_text(encoding="utf-8")
            structured = next(store.sanitized.glob("*.json")).read_text(encoding="utf-8")
            self.assertNotIn("Authorization", raw + structured)
            self.assertNotIn('"token"', raw + structured)
            self.assertIn("Synthetic paragraph", raw)
            self.assertNotIn("Synthetic paragraph", structured)

    def test_redaction_jwt_nested_fields_and_bearer(self):
        data = {
            "password": "private",
            "nested": [{"Cookie": "x", "content": "Bearer example-secret"}],
            "jwt": ".".join(("eyJmb28", "eyJiYXI", "signature")),
        }
        self.assertNotIn("private", json.dumps(clean(data)))
        self.assertNotIn("example-secret", json.dumps(clean(data)))
        self.assertNotIn("eyJmb28", json.dumps(clean(data)))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.env = patch.dict(
            os.environ, {"PLONE_BASE_URL": BASE, "PLONE_TOKEN": FAKE_TOKEN}, clear=True
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = ReadOnlyClient(Settings.from_env(rest_path="", timeout=(15, 15)))
        self.store = SnapshotStore(self.directory.name, "run")
        self.runner = InventoryRunner(self.client, self.store)

    def test_first_batch_has_only_three_root_gets(self):
        with patch.object(
            requests.Session, "send", side_effect=[response(page(root)) for root in ROOTS]
        ) as send:
            report = self.runner.execute()
        self.assertTrue(report["complete"])
        self.assertFalse(report["ready_for_write"])
        self.assertEqual(send.call_count, 3)
        self.assertEqual(
            [call.args[0].url for call in send.call_args_list], [BASE + root for root in ROOTS]
        )

    def test_401_stops_runner_and_preserves_partial_summary(self):
        with patch.object(
            requests.Session, "send", side_effect=[response(page("/pt-br")), response(status=401)]
        ) as send:
            report = self.runner.execute("schemas")
        self.assertEqual(send.call_count, 2)
        self.assertFalse(report["complete"])
        self.assertEqual(report["error"]["http_status"], 401)
        self.assertTrue((self.store.sanitized / "summary.json").exists())

    def test_root_missing_stops_later_stages(self):
        with patch.object(
            requests.Session, "send", return_value=response({"type": "NotFound"}, status=404)
        ) as send:
            report = self.runner.execute("models")
        self.assertFalse(report["complete"])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(report["conflicts"][0]["category"], "missing page")

    def test_models_are_second_batch_after_protected_roots(self):
        responses = [response(page(root)) for root in ROOTS] + [
            response(page(model)) for model in MODELS
        ]
        with patch.object(requests.Session, "send", side_effect=responses) as send:
            self.runner.execute("models")
        self.assertEqual(
            [call.args[0].url for call in send.call_args_list],
            [BASE + path for path in (*ROOTS, *MODELS)],
        )

    def test_pagination_merges_all_items_and_keeps_raw_batches(self):
        first = page("/pt-br", [{"@id": "https://portal.test/site/pt-br/a", "id": "a"}], total=2)
        first["batching"] = {"next": "https://portal.test/site/pt-br?b_start=1"}
        second = page("/pt-br", [{"@id": "https://portal.test/site/pt-br/b", "id": "b"}], total=2)
        original = deepcopy(first)
        with patch.object(
            requests.Session, "send", side_effect=[response(first), response(second)]
        ):
            result = self.runner.collection("/pt-br")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(first, original)
        self.assertEqual(len(list(self.store.raw.glob("*.json"))), 2)
        aggregate = next(self.store.sanitized.glob("*-aggregate.json"))
        self.assertTrue(json.loads(aggregate.read_text(encoding="utf-8"))["pagination_complete"])

    def test_external_pagination_link_stops_before_second_request(self):
        data = page("/pt-br", total=1)
        data["batching"] = {"next": "https://evil.test/page"}
        with (
            patch.object(requests.Session, "send", return_value=response(data)) as send,
            self.assertRaises(InventoryError),
        ):
            self.runner.collection("/pt-br")
        self.assertEqual(send.call_count, 1)

    def test_pagination_cycle_is_partial(self):
        data = page("/pt-br", total=2)
        data["batching"] = {"next": "/pt-br"}
        with (
            patch.object(requests.Session, "send", return_value=response(data)) as send,
            self.assertRaises(InventoryError) as caught,
        ):
            self.runner.collection("/pt-br")
        self.assertEqual(caught.exception.kind, "pagination_cycle")
        self.assertEqual(send.call_count, 1)

    def test_missing_batch_link_cannot_claim_full_inventory(self):
        with (
            patch.object(requests.Session, "send", return_value=response(page("/pt-br", total=3))),
            self.assertRaises(InventoryError) as caught,
        ):
            self.runner.collection("/pt-br")
        self.assertEqual(caught.exception.kind, "incomplete_pagination")

    def test_children_only_follow_observed_ids(self):
        data = page(
            "/en/model", [{"@id": "https://portal.test/site/en/model/about", "id": "about"}]
        )
        with patch.object(
            requests.Session, "send", return_value=response(page("/en/model/about"))
        ) as send:
            self.runner.children("/en/model", data)
        self.assertEqual(send.call_args.args[0].url, "https://portal.test/site/en/model/about")

    def test_unrelated_child_is_blocked(self):
        with patch.object(requests.Session, "send") as send, self.assertRaises(InventoryError):
            self.runner.children(
                "/en/model", {"items": [{"@id": "https://portal.test/site/es/other"}]}
            )
        send.assert_not_called()

    def test_sample_paths_discovered_not_from_csv(self):
        path = "/pt-br/observed/cefet_mg"
        data = page("/pt-br", [{"@id": "https://portal.test/site" + path, "id": "cefet_mg"}])
        with patch.object(requests.Session, "send", return_value=response(data)) as send:
            result = self.runner.discover_sample("CEFET-MG")
        self.assertEqual(result, "https://portal.test/site" + path)
        self.assertIn("/pt-br/@search?", send.call_args.args[0].url)
        self.assertNotIn("instituicoes_brasileiras", send.call_args.args[0].url)

    def test_ambiguous_sample_requires_human_binding(self):
        items = [
            {"@id": "https://portal.test/site/pt-br/a/ufsc"},
            {"@id": "https://portal.test/site/pt-br/b/ufsc"},
        ]
        with patch.object(requests.Session, "send", return_value=response(page("/pt-br", items))):
            self.assertIsNone(self.runner.discover_sample("UFSC"))
        self.assertEqual(len(self.runner.report["pending"][0]["observed_candidates"]), 2)

    def test_invalid_collection_shape_is_rejected(self):
        with (
            patch.object(requests.Session, "send", return_value=response({"items": "wrong"})),
            self.assertRaises(InventoryError),
        ):
            self.runner.collection("/pt-br")

    def test_changed_count_cannot_certify_live_pagination(self):
        first = page("/pt-br", total=2)
        first["batching"] = {"next": "/pt-br?b_start=1"}
        second = page("/pt-br", total=3)
        with (
            patch.object(requests.Session, "send", side_effect=[response(first), response(second)]),
            self.assertRaises(InventoryError) as caught,
        ):
            self.runner.collection("/pt-br")
        self.assertEqual(caught.exception.kind, "pagination_changed")

    def test_duplicate_items_preserved_as_raw_but_not_certified(self):
        child = {"@id": "https://portal.test/site/pt-br/a"}
        first = page("/pt-br", [child], total=2)
        first["batching"] = {"next": "/pt-br?b_start=1"}
        second = page("/pt-br", [child], total=2)
        with (
            patch.object(requests.Session, "send", side_effect=[response(first), response(second)]),
            self.assertRaises(InventoryError) as caught,
        ):
            self.runner.collection("/pt-br")
        self.assertEqual(caught.exception.kind, "pagination_duplicate")
        self.assertEqual(len(list(self.store.raw.glob("*.json"))), 2)

    def test_schema_stage_whole_flow_is_get_only_and_handles_types_list(self):
        def send(session, prepared, **options):
            self.assertEqual(prepared.method, "GET")
            path = prepared.url.removeprefix(BASE).split("?", 1)[0]
            if path == "/@types":
                return response([{"id": "Document", "@id": BASE + "/@types/Document"}])
            if path.startswith("/@types/"):
                return response(
                    {"type": "object", "required": ["title"]},
                    content_type="application/json+schema",
                )
            if path.endswith("/@workflow"):
                return response({"state": "private", "transitions": [{"id": "publish"}]})
            if path.endswith("/@translations"):
                return response({"items": []})
            if path == "/pt-br/@search":
                from urllib.parse import parse_qs, urlsplit

                acronym = parse_qs(urlsplit(prepared.url).query)["SearchableText"][0]
                child = {"@id": "https://portal.test/site/pt-br/observed/" + acronym.lower()}
                return response(page("/pt-br", [child]))
            return response(page(path))

        with patch.object(requests.Session, "send", autospec=True, side_effect=send) as transport:
            report = self.runner.execute("schemas")
        self.assertNotIn("error", report)
        urls = [call.args[1].url for call in transport.call_args_list]
        self.assertIn(BASE + "/@types", urls)
        self.assertIn(BASE + "/@types/Document", urls)
        self.assertTrue(any(url.endswith("/@workflow") for url in urls))
        self.assertTrue(any(url.endswith("/@translations") for url in urls))
        self.assertFalse(any(url.endswith("/@workflow/publish") for url in urls))


class ReconciliationTests(unittest.TestCase):
    def test_all_nine_categories_without_mutation(self):
        actual = {
            "slug": "old_slug",
            "@type": "Folder",
            "language": "pt-br",
            "title": "Observed",
            "review_state": "private",
            "subjects": [],
            "block_types": {"b": "title"},
            "children": [{"id": "extra"}],
        }
        wanted = {
            "fields": {
                "slug": "expected-slug",
                "@type": "Document",
                "language": "en",
                "title": "Approved literal",
                "review_state": "published",
                "subjects": ["new"],
            },
            "block_types": ["slate"],
            "children": ["about"],
        }
        before = deepcopy(actual)
        conflicts = compare_page(actual, wanted)
        self.assertEqual(
            {item["category"] for item in conflicts},
            {
                "slug conflict",
                "structure mismatch",
                "language mismatch",
                "title/name mismatch",
                "workflow mismatch",
                "metadata mismatch",
                "block mismatch",
                "missing page",
                "unexpected page",
            },
        )
        self.assertEqual(actual, before)

    def test_missing_metadata_not_assumed_empty(self):
        result = compare_page({}, {"fields": {"language": "en"}})
        self.assertEqual(result[0]["observed"], {"status": "not_observed"})

    def test_models_ignore_uuid_differences(self):
        english = {"block_types": {"one": "slate"}, "block_order": ["slate"]}
        spanish = {"block_types": {"otro": "slate"}, "block_order": ["slate"]}
        self.assertEqual(compare_models(english, spanish), [])

    def test_approved_translations_are_literal_not_generated(self):
        data = {
            "local_resolutions": [
                {
                    "rule": "approved_institutional_translations",
                    "field": "translated_name",
                    "status": "resolved_in_overlay",
                    "institution": "EXAMPLE",
                    "language": "en",
                    "value": "Approved  literal",
                    "source_references": [{"cell": "C2"}],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            result = approved_names(path)
        self.assertEqual(result[("example", "en")]["value"], "Approved  literal")

    def test_duplicate_approved_name_conflict_never_resolved(self):
        item = {
            "rule": "approved_institutional_translations",
            "field": "translated_name",
            "status": "resolved_in_overlay",
            "institution": "EXAMPLE",
            "language": "en",
            "value": "One",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay.json"
            path.write_text(
                json.dumps({"local_resolutions": [item, {**item, "value": "Two"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(InventoryError):
                approved_names(path)

    def test_current_workbook_mismatch_stops_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overlay.json"
            path.write_text(json.dumps({"local_resolutions": []}), encoding="utf-8")
            workbook = Path(directory) / "production.xlsx"
            workbook.write_bytes(b"changed local source")
            with self.assertRaises(InventoryError) as caught:
                approved_names(path, workbook)
        self.assertEqual(caught.exception.kind, "source_conflict")

    def test_legacy_csv_is_only_comparison_evidence(self):
        path = Path(__file__).parent.parent / "studyinbr" / "lista_ies_completa.csv"
        result = legacy_expectations(path)
        self.assertEqual(result["ufac"]["expected_slug"], "ufac")
        self.assertIn("cefet_mg", result)
        self.assertNotIn("cefet-mg", result)

    def test_csv_conflicting_rows_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_text(
                "Sigla;Onde criar;nome_curto;Título\nEXAMPLE;https://portal.test/site/en;a;One\nEXAMPLE;https://portal.test/site/en;b;Two\n",
                encoding="utf-8",
            )
            with self.assertRaises(InventoryError) as caught:
                legacy_expectations(path)
        self.assertEqual(caught.exception.kind, "source_conflict")


class CLITests(unittest.TestCase):
    def test_missing_token_stops_before_network_without_snapshots(self):
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"PLONE_BASE_URL": BASE}, clear=True),
            patch.object(requests.Session, "send") as send,
            redirect_stdout(output),
        ):
            status = main([])
        self.assertEqual(status, 1)
        send.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["type"], "configuration")

    def test_client_and_cli_do_not_import_operational_legacy(self):
        import ast

        root = Path(__file__).parent.parent / "src" / "studybr"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            self.assertNotIn("config", imports)
            self.assertNotIn("api_client", imports)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, ("post", "put", "patch", "delete"))


if __name__ == "__main__":
    unittest.main()
