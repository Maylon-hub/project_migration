import unittest
import os
import tempfile
import json
from migration_to_plone_6 import NewsItem, PloneClient, load_progress, save_progress

class TestMigrationUtils(unittest.TestCase):

    def test_news_item_creation(self):
        """Valida inicialização e campos padrão da dataclass NewsItem."""
        item = NewsItem(
            title="Notícia Teste",
            body="<p>Conteúdo de teste</p>",
            url="https://www.gov.br/exemplo/noticia-1"
        )
        self.assertEqual(item.title, "Notícia Teste")
        self.assertEqual(item.body, "<p>Conteúdo de teste</p>")
        self.assertEqual(item.url, "https://www.gov.br/exemplo/noticia-1")
        self.assertEqual(item.summary, "")
        self.assertEqual(item.tags, [])

    def test_save_and_load_progress(self):
        """Valida que a gravação e leitura do progresso local persistem os dados corretamente."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prog_file = os.path.join(tmpdir, "progresso.json")
            done_urls = {"https://gov.br/noticia-1", "https://gov.br/noticia-2"}

            # Salva progresso
            save_progress(prog_file, done_urls)
            self.assertTrue(os.path.exists(prog_file))

            # Carrega progresso
            loaded_urls = load_progress(prog_file)
            self.assertEqual(loaded_urls, done_urls)

    def test_html_to_volto_blocks_paragraphs(self):
        """Valida a conversão de HTML simples (parágrafos e títulos) para blocos Slate do Volto."""
        html_content = "<h2>Título Principal</h2><p>Este é um <strong>parágrafo</strong> de teste com <a href='https://gov.br'>link</a>.</p>"
        blocks, layout = PloneClient._html_to_volto_blocks(html_content)

        self.assertIn("items", layout)
        self.assertGreater(len(layout["items"]), 0)

        # Verifica se os blocos gerados possuem o tipo slate
        block_types = [block.get("@type") for block in blocks.values()]
        self.assertIn("slate", block_types)

    def test_html_to_volto_blocks_empty(self):
        """Valida que HTML vazio gera ao menos um bloco padrão para o Volto."""
        blocks, layout = PloneClient._html_to_volto_blocks("")
        self.assertEqual(len(layout["items"]), 1)
        uid = layout["items"][0]
        self.assertEqual(blocks[uid]["@type"], "slate")

if __name__ == "__main__":
    unittest.main()
