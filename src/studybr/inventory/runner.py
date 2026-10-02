"""Bounded batches: roots -> UGM -> discovered samples -> schemas/status."""

from copy import deepcopy
from urllib.parse import quote, urlencode

from studybr.api.errors import InventoryError, PloneError

from .comparison import compare_models, compare_page
from .snapshots import write_json

ROOTS = ("/pt-br", "/en", "/es")
MODELS = (
    "/en/higher-education-institutions/north-region/acre/ugm",
    "/es/instituciones-de-educacion-superior/region-norte/acre/ugm",
)
SAMPLES = ("UFAC", "UFSCar", "CEFET-MG", "UFAPE", "UFSC")
STAGES = ("roots", "models", "samples", "schemas")


class InventoryRunner:
    def __init__(
        self,
        client,
        store,
        max_pages=20,
        max_children=30,
        expectations=None,
        legacy=None,
        names=None,
    ):
        self.client = client
        self.store = store
        self.max_pages = max_pages
        self.max_children = max_children
        self.expectations = expectations or {}
        self.legacy = legacy or {}
        self.names = names or {}
        self.pages = {}
        self._reusable = set()
        self._cached_pages = {}
        self._scope = None
        self.report = {
            "schema_version": 1,
            "base_url": client.base_url,
            "diagnostic_only": True,
            "ready_for_write": False,
            "complete": False,
            "requests": [],
            "conflicts": [],
            "pending": [],
            "visibility": "Only content readable by this account; not proof of full portal coverage.",
        }

    def resume(self):
        previous, pages = self.store.previous()
        if previous.get("base_url") != self.client.base_url or previous.get(
            "source_hashes", {}
        ) != self.report.get("source_hashes", {}):
            raise InventoryError(
                "resume_conflict", "Endpoint or source hashes changed; use a new run."
            )
        for page in pages:
            path = self.client.path_of(page["url"])
            if page.get("api_path") != path or page.get("pagination_complete") is not True:
                raise InventoryError(
                    "resume_conflict", "Invalid prior aggregate; no implicit reuse."
                )
            self._cached_pages[path] = page
            if path not in ROOTS:
                self._reusable.add(path)
        self.report["previous_batches"] = previous.get("previous_batches", []) + [
            {
                "stage": previous.get("requested_stage"),
                "complete": previous.get("complete"),
                "requests_made": previous.get("requests_made"),
                "error": previous.get("error"),
            }
        ]
        self.report["reused_pages"] = []

    def authorize(self, path):
        if self._scope is not None:
            self._scope.add(self.client.path_of(path))

    def fetch(self, path, kind="page", model=False, optional=False):
        url = self.client.resolve(path)
        if self._scope is not None and self.client.path_of(url) not in self._scope:
            raise InventoryError(
                "endpoint_not_authorized", "Endpoint is outside the requested batch."
            )
        try:
            data = self.client.get(url)
        except PloneError as error:
            self.report["requests"].append({"url": url, **error.as_dict()})
            if optional and error.status == 404:
                self.report["conflicts"].append(
                    {
                        "category": "missing page" if kind == "page" else "metadata mismatch",
                        "url": url,
                        "evidence": "HTTP 404 for this account",
                        "kind": kind,
                    }
                )
                return None
            raise
        self.report["requests"].append({"url": url, "http_status": 200, "kind": kind})
        self.store.save(url, data, kind, model)
        return data

    def collection(self, path, kind="page", model=False, optional=False):
        """Follow server-provided batch links only, preserving every raw response."""
        current = path
        api_path = self.client.path_of(path)
        if self._scope is not None and api_path not in self._scope:
            raise InventoryError(
                "endpoint_not_authorized", "Endpoint is outside the requested batch."
            )
        if api_path in self._reusable:
            self._reusable.remove(api_path)
            self.report["reused_pages"].append(api_path)
            result = self._cached_pages[api_path]
            self.pages[api_path] = result
            expected = self.expectations.get(api_path)
            if expected:
                self.report["conflicts"].extend(
                    {"url": result["url"], **item} for item in compare_page(result, expected)
                )
            return {**result, "items": result["children"]}
        seen = set()
        combined = None
        total = None
        for _ in range(self.max_pages):
            url = self.client.resolve(current)
            if url in seen:
                raise InventoryError("pagination_cycle", "Paginação cíclica; inventário parcial.")
            seen.add(url)
            data = self.fetch(url, kind, model, optional=optional and combined is None)
            if data is None:
                return None
            if not isinstance(data, dict):
                raise InventoryError("invalid_shape", "Esperado objeto JSON para página ou busca.")
            if not isinstance(data.get("items", []), list) or not all(
                isinstance(item, dict) for item in data.get("items", [])
            ):
                raise InventoryError("invalid_shape", "items deve ser uma lista de objetos.")
            total_here = data.get("items_total")
            if total_here is not None and (
                isinstance(total_here, bool) or not isinstance(total_here, int) or total_here < 0
            ):
                raise InventoryError("invalid_shape", "items_total deve ser inteiro não negativo.")
            if combined is None:
                combined = deepcopy(data)
                total = data.get("items_total")
            else:
                if total_here is not None and total is not None and total_here != total:
                    raise InventoryError(
                        "pagination_changed",
                        "items_total mudou durante o lote; repetir inventário.",
                    )
                combined.setdefault("items", []).extend(deepcopy(data.get("items", [])))
            batching = data.get("batching") or {}
            if not isinstance(batching, dict):
                raise InventoryError("invalid_shape", "batching deve ser um objeto.")
            current = batching.get("next")
            if current:
                current = self.client.next_url(url, current)
            if not current:
                if isinstance(total, int) and len(combined.get("items", [])) != total:
                    raise InventoryError(
                        "incomplete_pagination",
                        "items_total diverge dos itens coletados; cobertura parcial.",
                    )
                identities = [
                    item.get("@id") or item.get("UID") or item.get("id")
                    for item in combined.get("items", [])
                ]
                known = [item for item in identities if isinstance(item, str)]
                if len(known) != len(set(known)):
                    raise InventoryError(
                        "pagination_duplicate",
                        "Itens repetidos entre batches; evidências preservadas, cobertura não confirmada.",
                    )
                if kind == "page":
                    canonical = self.client.resolve(path)
                    result = self.store.save(
                        canonical,
                        combined,
                        kind,
                        model,
                        aggregate=True,
                        api_path=self.client.path_of(path),
                    )
                    self.pages[self.client.path_of(path)] = result
                    expected = self.expectations.get(self.client.path_of(path))
                    if expected:
                        self.report["conflicts"].extend(
                            {"url": canonical, **item} for item in compare_page(result, expected)
                        )
                return combined
        raise InventoryError("pagination_limit", "Limite de páginas atingido; inventário parcial.")

    def children(self, path, data):
        children = data.get("items", [])
        if len(children) > self.max_children:
            raise InventoryError(
                "children_limit", "Limite de subpáginas atingido; não expandido silenciosamente."
            )
        parent = self.client.path_of(path).rstrip("/")
        for child in children:
            child_url = child.get("@id") if isinstance(child, dict) else None
            if not child_url:
                self.report["pending"].append(
                    {"parent": parent, "reason": "Child without observed @id; path not invented."}
                )
                continue
            child_path = self.client.path_of(child_url)
            if child_path.rsplit("/", 1)[0] != parent:
                raise InventoryError("unsafe_child", "Referência de filho fora do pai observado.")
            self.authorize(child_url)
            self.collection(child_url, model=True, optional=True)

    def discover_sample(self, acronym):
        # Scope is the verified /pt-br context; CSV URLs are never queried.
        query = urlencode({"SearchableText": acronym, "b_size": 50})
        self.authorize("/pt-br/@search")
        data = self.collection("/pt-br/@search?" + query, kind="search", optional=True)
        if data is None:
            return None
        candidates = {}
        variants = {
            acronym.casefold(),
            acronym.casefold().replace("-", "_"),
            acronym.casefold().replace("-", ""),
        }
        for item in data.get("items", []):
            if not isinstance(item, dict) or not item.get("@id"):
                continue
            path = self.client.path_of(item["@id"])
            slug = path.rstrip("/").rsplit("/", 1)[-1].casefold()
            if path.startswith("/pt-br/") and (
                slug in variants or any(slug.startswith(v + "-") for v in variants)
            ):
                candidates[path] = item["@id"]
        if len(candidates) != 1:
            self.report["pending"].append(
                {
                    "institution": acronym,
                    "reason": "No unique observed home; human path binding required.",
                    "observed_candidates": sorted(candidates),
                    "search_items": len(data.get("items", [])),
                }
            )
            return None
        return next(iter(candidates.values()))

    def reconcile_sample(self, acronym, path):
        page = self.pages[self.client.path_of(path)]
        expected = self.legacy.get(acronym.casefold())
        if expected:
            csv_path = self.client.path_of(expected["expected_url"])
            actual_path = self.client.path_of(path)
            if csv_path != actual_path:
                self.report["conflicts"].append(
                    {
                        "category": "slug conflict",
                        "institution": acronym,
                        "source": "legacy CSV",
                        "expected_path": csv_path,
                        "observed_path": actual_path,
                    }
                )
            self.report["conflicts"].extend(
                {"institution": acronym, "source": "legacy CSV", **item}
                for item in compare_page(
                    page, {"fields": {"title": expected["expected_title"], "language": "pt-br"}}
                )
            )
        else:
            self.report["pending"].append(
                {
                    "institution": acronym,
                    "reason": "No exact CSV institution binding; aliases are not automatically resolved.",
                }
            )
        for language in ("en", "es"):
            name = self.names.get((acronym.casefold(), language))
            self.report["pending"].append(
                {
                    "institution": acronym,
                    "language": language,
                    "reason": "Translation home not inventoried in this bounded batch; no automatic title construction.",
                    "approved_name": name["value"] if name else None,
                    "source_references": name["source_references"] if name else [],
                }
            )

    def execute(self, stage="roots"):
        self.report["requested_stage"] = stage
        try:
            if stage not in STAGES:
                raise InventoryError("configuration", "Unknown inventory stage.")
            self._scope = set(ROOTS)
            # Every invocation validates protected roots first; no /@govsite auth test.
            for root in ROOTS:
                if self.collection(root, optional=True) is None:
                    self.report["pending"].append(
                        {"reason": "Root missing/inaccessible; later batches not started."}
                    )
                    return self.report
                self.report["conflicts"].extend(
                    {"url": self.client.resolve(root), **item}
                    for item in compare_page(
                        self.pages[root], {"fields": {"language": root.lstrip("/")}}
                    )
                )
            if stage == "roots":
                self.report["complete"] = True
                return self.report
            for model in MODELS:
                self.authorize(model)
                data = self.collection(model, model=True, optional=True)
                if data is not None:
                    self.report["conflicts"].extend(
                        {"url": self.client.resolve(model), **item}
                        for item in compare_page(
                            self.pages[model], {"fields": {"language": model.split("/")[1]}}
                        )
                    )
            if all(path in self.pages for path in MODELS):
                self.report["conflicts"].extend(
                    {"source": "UGM EN/ES comparison", **item}
                    for item in compare_models(*(self.pages[path] for path in MODELS))
                )
            if stage == "models":
                self.report["complete"] = all(path in self.pages for path in MODELS)
                return self.report
            for model in MODELS:
                if model in self.pages:
                    self.children(model, {"items": self.pages[model]["children"]})
            for acronym in SAMPLES:
                path = self.discover_sample(acronym)
                if path:
                    self.authorize(path)
                    data = self.collection(path, model=True, optional=True)
                    if data is not None:
                        self.reconcile_sample(acronym, path)
                        self.children(path, data)
            if stage == "schemas":
                self.authorize("/@types")
                self.fetch("/@types", kind="types", optional=True)
                types = {page.get("@type") for page in self.pages.values()} - {None}
                for portal_type in sorted(types):
                    self.authorize("/@types/" + quote(portal_type, safe=""))
                    self.fetch(
                        "/@types/" + quote(portal_type, safe=""), kind="schema", optional=True
                    )
                for path in list(self.pages):
                    # GET only; transition URLs are rejected by the client.
                    self.authorize(path.rstrip("/") + "/@workflow")
                    self.authorize(path.rstrip("/") + "/@translations")
                    self.fetch(path.rstrip("/") + "/@workflow", kind="workflow", optional=True)
                    self.fetch(
                        path.rstrip("/") + "/@translations", kind="translations", optional=True
                    )
            self.report["complete"] = not self.report["pending"] and all(
                path in self.pages for path in MODELS
            )
            return self.report
        except PloneError as error:
            self.report["error"] = error.as_dict()
            return self.report
        finally:
            self.report["requests_made"] = self.client.requests_made
            self.report["pages_observed"] = len(self.pages)
            write_json(self.store.sanitized / "summary.json", self.client.redact(self.report))
