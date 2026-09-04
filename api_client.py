"""
Cliente HTTP REST API do Plone 6 (plone.restapi)
=================================================

Gerencia a sessão HTTP, autenticação dinâmica via JWT (/@login), cabeçalhos e as operações CRUD
e de Workflow no CMS Plone 6 / Volto.
"""

import logging
from typing import Any, Dict, Optional
import requests
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import API_PASSWORD, API_TOKEN, API_URL, API_USERNAME

# Configuração do Logger local do módulo
logger = logging.getLogger("PloneRestClient")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class PloneRestClient:
    """Cliente para a REST API do Plone 6 com suporte a sessões autenticadas via JWT."""

    def __init__(
        self,
        api_url: str = API_URL,
        token: Optional[str] = API_TOKEN,
        username: Optional[str] = API_USERNAME,
        password: Optional[str] = API_PASSWORD,
        auto_login: bool = True
    ):
        self.base_url = api_url.rstrip("/")
        if "++api++" not in self.base_url:
            self.base_url = f"{self.base_url}/++api++"

        self.token = token.strip() if token else ""
        self.username = username
        self.password = password

        # Inicializa a sessão HTTP do requests com os cabeçalhos padrão e retries
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        # Configura retries com backoff exponencial para resiliência a falhas de rede/API
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        logger.info(f"PloneRestClient inicializado para o endpoint: '{self.base_url}'")

        # Se auto_login for True e username/password forem fornecidos, realiza o login automático via /@login
        if auto_login and self.username and self.password and self.username != "SEU_USERNAME":
            login_success = self.login(self.username, self.password)
            if not login_success and self.token and self.token != "SEU_TOKEN_JWT_AQUI":
                logger.warning("⚠️  Falha no login automático. Recorrendo ao API_TOKEN estático...")
                self._set_bearer_token(self.token)
        elif self.token:
            self._set_bearer_token(self.token)

    def _set_bearer_token(self, token: str):
        """Injeta o token JWT no cabeçalho Authorization com o prefixo Bearer."""
        auth_header = token if token.startswith("Bearer ") else f"Bearer {token}"
        self.session.headers["Authorization"] = auth_header
        self.token = token

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """Autentica na API do Plone 6 enviando um POST para /@login e injeta o token JWT obtido.

        :param username: Nome de usuário / login no Plone.
        :param password: Senha de acesso.
        :return: True se a autenticação foi realizada com sucesso, False caso contrário.
        """
        user = username or self.username or API_USERNAME
        passwd = password or self.password or API_PASSWORD

        login_url = f"{self.base_url}/@login"
        logger.info(f"POST [Autenticando] Usuário '{user}' em -> '{login_url}'")

        payload = {
            "login": user,
            "password": passwd
        }

        try:
            response = self.session.post(login_url, json=payload, timeout=(10, 30))

            if response.status_code == 200:
                data = response.json()
                jwt_token = data.get("token")
                if jwt_token:
                    self._set_bearer_token(jwt_token)
                    logger.info("🔑 Autenticação JWT realizada com sucesso! Token injetado nas requisições.")
                    return True
                else:
                    logger.error("❌ Resposta do /@login não contém a chave 'token'.")
                    return False
            else:
                logger.error(
                    f"❌ Falha de autenticação ({response.status_code}) em '{login_url}'. "
                    f"Resposta: {response.text[:200]}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão ao enviar POST de login para '{login_url}': {e}")
            return False

    def _resolve_url(self, path_or_url: str) -> str:
        """Resolve caminhos relativos ou ajusta URLs absolutas injetando ++api++."""
        url = path_or_url
        if not url.startswith("http://") and not url.startswith("https://"):
            rel_path = url.lstrip("/")
            return f"{self.base_url}/{rel_path}"
        
        # Injeta ++api++ se for uma URL absoluta do frontend
        if "++api++" not in url:
            original_base = self.base_url.replace("/++api++", "")
            if url.startswith(original_base):
                url = url.replace(original_base, self.base_url, 1)
        
        return url

    def create_content(self, container_url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Envia uma requisição POST para criar um novo objeto no Plone 6.

        :param container_url: URL ou caminho da pasta recipiente.
        :param payload: Dicionário contendo os dados do conteúdo (ex: @type, title, blocks).
        :return: Dicionário da resposta JSON do Plone 6 ou None em caso de falha.
        """
        target_url = self._resolve_url(container_url)
        content_type = payload.get("@type", "Conteúdo")
        title = payload.get("title", payload.get("id", "sem título"))

        logger.info(f"POST [Criando {content_type}] '{title}' em -> '{target_url}'")

        try:
            response = self.session.post(target_url, json=payload, timeout=(10, 60))

            if response.status_code in (200, 201):
                res_data = response.json()
                created_id = res_data.get("@id", res_data.get("id", target_url))
                logger.info(f"✅ Conteúdo criado com sucesso! ID: {created_id}")
                return res_data
            else:
                logger.error(
                    f"❌ Falha ao criar conteúdo ({response.status_code}). "
                    f"Resposta: {response.text[:300]}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão ao enviar POST para '{target_url}': {e}")
            return None

    def update_content(self, content_url: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Envia uma requisição PATCH para atualizar um objeto existente no Plone 6.

        :param content_url: URL ou caminho do objeto a ser atualizado.
        :param payload: Dicionário contendo os campos a modificar.
        :return: Dicionário com o conteúdo atualizado ou None em caso de erro.
        """
        target_url = self._resolve_url(content_url)
        title = payload.get("title", target_url)

        logger.info(f"PATCH [Atualizando] '{title}' -> '{target_url}'")

        try:
            response = self.session.patch(target_url, json=payload, timeout=(10, 60))

            if response.status_code in (200, 204):
                logger.info(f"✅ Conteúdo atualizado com sucesso em '{target_url}'!")
                return response.json() if response.content else {"status": "success", "status_code": response.status_code}
            else:
                logger.error(
                    f"❌ Falha ao atualizar conteúdo ({response.status_code}). "
                    f"Resposta: {response.text[:300]}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão ao enviar PATCH para '{target_url}': {e}")
            return None

    def get_content(self, content_url: str) -> Optional[Dict[str, Any]]:
        """Obtém os dados completos de um objeto existente no Plone 6 via GET.

        :param content_url: URL ou caminho do objeto.
        :return: Dicionário com os dados do objeto ou None em caso de erro.
        """
        target_url = self._resolve_url(content_url)
        try:
            response = self.session.get(target_url, timeout=(10, 30))
            if response.status_code == 200:
                return response.json()
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão ao enviar GET para '{target_url}': {e}")
            return None

    def publish_content(self, content_url: str) -> bool:
        """Envia uma requisição POST para o endpoint /@workflow/publish alterando o estado para publicado.

        :param content_url: URL ou caminho do objeto a ser publicado.
        :return: True se publicado com sucesso ou já publicado, False caso contrário.
        """
        base_target = self._resolve_url(content_url).rstrip("/")
        workflow_url = f"{base_target}/@workflow/publish"

        logger.info(f"POST [Publicando Workflow] -> '{workflow_url}'")

        try:
            response = self.session.post(workflow_url, json={}, timeout=(10, 30))

            if response.status_code == 200:
                logger.info(f"📢 Conteúdo em '{base_target}' publicado com sucesso!")
                return True
            elif response.status_code == 400:
                logger.warning(
                    f"⚠️ Transição de workflow não aplicável ({response.status_code}). "
                    f"Pode já estar publicado. Resposta: {response.text[:200]}"
                )
                return True
            else:
                logger.error(
                    f"❌ Erro ao alterar estado de workflow ({response.status_code}): {response.text[:300]}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão no workflow de publicação para '{base_target}': {e}")
            return False

    def retract_to_private(self, content_url: str) -> bool:
        """Altera o estado do workflow para privado (retract/reject), garantindo que o conteúdo não fique público.

        :param content_url: URL ou caminho do objeto.
        :return: True se já for privado ou alterado para privado com sucesso, False em caso de erro.
        """
        base_target = self._resolve_url(content_url).rstrip("/")
        workflow_url = f"{base_target}/@workflow"

        logger.info(f"POST [Garantindo estado PRIVADO no Workflow] -> '{workflow_url}'")

        try:
            # 1. Consulta o estado atual e transições disponíveis
            wf_resp = self.session.get(workflow_url, timeout=(10, 30))
            if wf_resp.status_code == 200:
                wf_data = wf_resp.json()
                transitions = wf_data.get("transitions", [])
                history = wf_data.get("history", [])
                current_state = history[-1].get("review_state") if history else None

                if current_state in ("private", "draft"):
                    logger.info(f"🔒 Conteúdo em '{base_target}' já está no estado privado ('{current_state}').")
                    return True

                # Procura por transições que retornem a privado (ex: retract, reject, hide)
                transition_ids = [t.get("@id", t.get("id", "")).split("/")[-1] for t in transitions]
                target_transition = None
                for candidate in ["retract", "reject", "hide", "make_private"]:
                    if candidate in transition_ids:
                        target_transition = candidate
                        break

                if target_transition:
                    post_url = f"{workflow_url}/{target_transition}"
                    logger.info(f"Executando transição '{target_transition}' em -> '{post_url}'")
                    trans_resp = self.session.post(post_url, json={}, timeout=(10, 30))
                    if trans_resp.status_code in (200, 204):
                        logger.info(f"🔒 Conteúdo em '{base_target}' alterado com sucesso para PRIVADO via '{target_transition}'!")
                        return True
                    else:
                        logger.warning(f"Resposta na transição {target_transition} ({trans_resp.status_code}): {trans_resp.text[:200]}")
                        return trans_resp.status_code == 400
                else:
                    logger.info(f"Nenhuma transição de retração necessária/disponível em '{base_target}'. Transições: {transition_ids}")
                    return True

            elif wf_resp.status_code == 404:
                logger.error(f"❌ Conteúdo '{base_target}' não encontrado para verificação de workflow (404).")
                return False
            else:
                # Tenta enviar POST direto para @workflow/retract ou @workflow/reject como fallback
                for fallback_trans in ["retract", "reject"]:
                    fallback_url = f"{workflow_url}/{fallback_trans}"
                    f_resp = self.session.post(fallback_url, json={}, timeout=(10, 30))
                    if f_resp.status_code in (200, 400):
                        return True

                logger.warning(f"⚠️ Não foi possível obter detalhes de workflow ({wf_resp.status_code}) em '{workflow_url}'.")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão ao alterar estado para privado em '{base_target}': {e}")
            return False

