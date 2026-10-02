"""Additional contracts for the unified transport, scope and incremental storage."""

import hashlib
import json
import os
from unittest.mock import patch

import pytest
import requests

from studybr.api.client import ReadOnlyClient
from studybr.api.errors import InventoryError, PloneError
from studybr.inventory.cli import main
from studybr.inventory.runner import MODELS, ROOTS, InventoryRunner
from studybr.inventory.snapshots import SnapshotStore
from studybr.settings import Settings

BASE = "https://portal.test/site/++api++"


def response(data, status=200):
    result = requests.Response()
    result.status_code = status
    result.headers["Content-Type"] = "application/json"
    result._content = json.dumps(data).encode()
    result._content_consumed = True
    return result


def page(path):
    return {
        "@id": "https://portal.test/site" + path,
        "@type": "Document",
        "language": path.split("/")[1],
        "items": [],
        "items_total": 0,
    }


def runner(tmp_path, *, base=BASE, **settings):
    client = ReadOnlyClient(Settings(base, "fixture-credential", rest_path="", **settings))
    return InventoryRunner(client, SnapshotStore(tmp_path, "same-run"))


def seed(tmp_path):
    first = runner(tmp_path)
    with patch.object(
        requests.Session, "send", side_effect=[response(page(path)) for path in (*ROOTS, *MODELS)]
    ):
        assert first.execute("models")["complete"]
    return first


def test_resume_rechecks_roots_reuses_models_and_preserves_raw(tmp_path):
    first = seed(tmp_path)
    original = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in first.store.raw.glob("*.json")
    }
    resumed = runner(tmp_path)
    resumed.resume()
    with patch.object(
        requests.Session, "send", side_effect=[response(page(p)) for p in ROOTS]
    ) as send:
        report = resumed.execute("models")
    assert report["complete"]
    assert send.call_count == 3
    assert set(report["reused_pages"]) == set(MODELS)
    assert len(list(resumed.store.raw.glob("*.json"))) == 8
    assert original == {
        name: hashlib.sha256((resumed.store.raw / name).read_bytes()).hexdigest()
        for name in original
    }


def test_resume_after_401_uses_new_client_and_only_complete_aggregates(tmp_path):
    first = runner(tmp_path)
    responses = [response(page(p)) for p in (*ROOTS, MODELS[0])] + [response({}, 401)]
    with patch.object(requests.Session, "send", side_effect=responses):
        assert first.execute("models")["error"]["http_status"] == 401
    resumed = runner(tmp_path)
    resumed.resume()
    responses = [response(page(p)) for p in (*ROOTS, MODELS[1])]
    with patch.object(requests.Session, "send", side_effect=responses) as send:
        report = resumed.execute("models")
    assert report["complete"]
    assert send.call_count == 4
    assert report["reused_pages"] == [MODELS[0]]
    assert report["previous_batches"][0]["error"]["http_status"] == 401


def test_resume_401_stops_before_cached_models(tmp_path):
    seed(tmp_path)
    resumed = runner(tmp_path)
    resumed.resume()
    with patch.object(requests.Session, "send", return_value=response({}, 401)) as send:
        report = resumed.execute("models")
    assert send.call_count == 1
    assert report["reused_pages"] == []
    assert report["error"]["http_status"] == 401


@pytest.mark.parametrize("change", ["endpoint", "source", "aggregate"])
def test_resume_rejects_changed_evidence_before_network(tmp_path, change):
    first = seed(tmp_path)
    resumed = runner(tmp_path, base=BASE + "/other") if change == "endpoint" else runner(tmp_path)
    if change == "source":
        resumed.report["source_hashes"] = {"expectations": "new-hash"}
    if change == "aggregate":
        path = next(first.store.sanitized.glob("*-aggregate.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        data["pagination_complete"] = False
        path.write_text(json.dumps(data), encoding="utf-8")
    with patch.object(requests.Session, "send") as send, pytest.raises(InventoryError):
        resumed.resume()
    send.assert_not_called()


def test_cached_pages_do_not_expand_authorized_batch(tmp_path):
    seed(tmp_path)
    resumed = runner(tmp_path)
    resumed.resume()
    resumed._scope = set(ROOTS)
    with patch.object(requests.Session, "send") as send, pytest.raises(InventoryError) as error:
        resumed.collection(MODELS[0])
    assert error.value.kind == "endpoint_not_authorized"
    send.assert_not_called()


def test_unknown_stage_has_no_transport(tmp_path):
    inventory = runner(tmp_path)
    with patch.object(requests.Session, "send") as send:
        report = inventory.execute("everything")
    assert report["error"]["type"] == "configuration"
    assert not report["complete"]
    send.assert_not_called()


@pytest.mark.parametrize("run_id", ["../outside", "a/b", "a\\b", "C:outside"])
def test_run_identifier_cannot_escape_snapshot_root(tmp_path, run_id):
    with pytest.raises(InventoryError):
        SnapshotStore(tmp_path, run_id)
    assert not list(tmp_path.iterdir())


def test_query_batch_link_replaces_existing_query(tmp_path):
    inventory = runner(tmp_path)
    first = {**page("/pt-br"), "items_total": 1, "batching": {"next": "?b_start=1&b_size=1"}}
    second = {**page("/pt-br"), "items_total": 1, "items": [{"id": "one"}]}
    with patch.object(
        requests.Session, "send", side_effect=[response(first), response(second)]
    ) as send:
        assert len(inventory.collection("/pt-br?b_size=1")["items"]) == 1
    assert send.call_args.args[0].url == BASE + "/pt-br?b_start=1&b_size=1"


def test_same_host_pagination_cannot_escape_collection(tmp_path):
    inventory = runner(tmp_path)
    data = {**page("/pt-br"), "batching": {"next": "/es"}}
    with patch.object(requests.Session, "send", return_value=response(data)) as send:
        with pytest.raises(InventoryError) as error:
            inventory.collection("/pt-br")
    assert error.value.kind == "unsafe_pagination"
    assert send.call_count == 1


def test_stream_is_bounded_before_json_parsing(tmp_path):
    inventory = runner(tmp_path, max_response_bytes=8)
    with patch.object(requests.Session, "send", return_value=response({"too_long": "yes"})):
        with pytest.raises(InventoryError) as error:
            inventory.client.get("/pt-br")
    assert error.value.kind == "response_limit"


def test_server_cookie_is_discarded_before_next_get(tmp_path):
    inventory = runner(tmp_path)

    def send(prepared, **kwargs):
        assert "Cookie" not in prepared.headers
        inventory.client._session.cookies.set("private", "cookie-value")
        return response({})

    with patch.object(inventory.client._session, "send", side_effect=send):
        inventory.client.get("/pt-br")
        assert not inventory.client._session.cookies
        inventory.client.get("/en")
        assert not inventory.client._session.cookies


@pytest.mark.parametrize(
    "path,data",
    [
        ("/@types", [{"id": "Document"}]),
        ("/en/@workflow", {"state": "private", "transitions": [{"id": "publish"}]}),
        ("/en/@translations", {"items": []}),
    ],
)
def test_metadata_services_return_objects_or_lists_using_get(tmp_path, path, data):
    inventory = runner(tmp_path)
    with patch.object(requests.Session, "send", return_value=response(data)) as send:
        assert inventory.client.get(path) == data
    assert send.call_args.args[0].method == "GET"


def test_transition_and_embedded_credential_never_reach_transport(tmp_path):
    inventory = runner(tmp_path)
    with patch.object(requests.Session, "send") as send:
        for path in ("/en/@workflow/publish", "/en/fixture-credential"):
            with pytest.raises(PloneError):
                inventory.client.get(path)
    send.assert_not_called()


def test_cli_rejects_versionable_snapshot_destination_before_transport(capsys):
    with patch.dict(
        os.environ, {"PLONE_BASE_URL": BASE, "PLONE_TOKEN": "fixture-credential"}, clear=True
    ):
        with patch.object(requests.Session, "send") as send:
            assert main(["--output-dir", "tests"]) == 1
    send.assert_not_called()
    assert json.loads(capsys.readouterr().out)["type"] == "unsafe_output"
