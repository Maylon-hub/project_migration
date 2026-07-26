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
        self.token = token.strip() if token else ""
        self.username = username
        self.password = password

        # Inicializa a sessão HTTP do requests com os cabeçalhos padrão
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

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
        """Resolve caminhos relativos ou ajusta URLs absolutas."""
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        
        rel_path = path_or_url.lstrip("/")
        return f"{self.base_url}/{rel_path}"

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
                return response.json() if response.content else {}
            else:
                logger.error(
                    f"❌ Falha ao atualizar conteúdo ({response.status_code}). "
                    f"Resposta: {response.text[:300]}"
                )
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erro de conexão ao enviar PATCH para '{target_url}': {e}")
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
