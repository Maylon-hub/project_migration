import unittest
from unittest.mock import MagicMock, patch
import requests

from config import API_TOKEN, API_URL, API_USERNAME, API_PASSWORD
from api_client import PloneRestClient


class TestPloneRestClient(unittest.TestCase):

    def setUp(self):
        self.client = PloneRestClient(
            api_url="https://plone.test/site",
            token="test_token_123",
            auto_login=False
        )

    def test_headers_initialization(self):
        """Verifica se os cabeçalhos obrigatórios foram injetados corretamente."""
        headers = self.client.session.headers
        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Authorization"], "Bearer test_token_123")

    @patch.object(requests.Session, "post")
    def test_login_success(self, mock_post):
        """Testa a autenticação dinâmica via POST para /@login obtendo o token JWT."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "dynamic_jwt_token_456"}
        mock_post.return_value = mock_response

        success = self.client.login("admin", "secret")

        self.assertTrue(success)
        self.assertEqual(self.client.session.headers["Authorization"], "Bearer dynamic_jwt_token_456")
        mock_post.assert_called_once_with(
            "https://plone.test/site/@login",
            json={"login": "admin", "password": "secret"},
            timeout=(10, 30)
        )

    def test_resolve_url(self):
        """Testa o pré-processamento de URLs relativas e absolutas."""
        self.assertEqual(
            self.client._resolve_url("noticias"),
            "https://plone.test/site/noticias"
        )
        self.assertEqual(
            self.client._resolve_url("https://outrosite.com/item"),
            "https://outrosite.com/item"
        )

    @patch.object(requests.Session, "post")
    def test_create_content_success(self, mock_post):
        """Valida a criação de conteúdo via POST."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"@id": "https://plone.test/site/noticia-1", "title": "Notícia Teste"}
        mock_post.return_value = mock_response

        payload = {"@type": "News Item", "title": "Notícia Teste"}
        result = self.client.create_content("/noticias", payload)

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Notícia Teste")
        mock_post.assert_called_once_with("https://plone.test/site/noticias", json=payload, timeout=(10, 60))

    @patch.object(requests.Session, "patch")
    def test_update_content_success(self, mock_patch):
        """Valida a atualização de conteúdo via PATCH."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"title": "Titulo Atualizado"}'
        mock_response.json.return_value = {"title": "Titulo Atualizado"}
        mock_patch.return_value = mock_response

        payload = {"title": "Titulo Atualizado"}
        result = self.client.update_content("/noticias/noticia-1", payload)

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "Titulo Atualizado")
        mock_patch.assert_called_once_with("https://plone.test/site/noticias/noticia-1", json=payload, timeout=(10, 60))

    @patch.object(requests.Session, "post")
    def test_publish_content_success(self, mock_post):
        """Valida a alteração de estado no workflow para publicado."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        success = self.client.publish_content("/noticias/noticia-1")

        self.assertTrue(success)
        mock_post.assert_called_once_with("https://plone.test/site/noticias/noticia-1/@workflow/publish", json={}, timeout=(10, 30))


if __name__ == "__main__":
    unittest.main()
