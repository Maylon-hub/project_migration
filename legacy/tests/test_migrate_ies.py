import unittest
import importlib
import json

# Importação dinâmica para módulos iniciados por número (2_migrate_ies.py)
migrate_module = importlib.import_module("2_migrate_ies")
replace_placeholders = migrate_module.replace_placeholders
load_templates = migrate_module.load_templates
load_dataset = migrate_module.load_dataset


class TestMigrateIES(unittest.TestCase):

    def test_replace_placeholders(self):
        """Valida a substituição de chaves estáticas no template."""
        sample_template = {
            "blocks": {
                "b1": {
                    "@type": "title",
                    "title": "Universidade Federal de São Carlos (UFSCar) em São Carlos - SP (São Paulo)"
                }
            }
        }
        replacements = {
            "Universidade Federal de São Carlos": "Universidade Federal do Acre",
            "UFSCar": "UFAC",
            "São Carlos": "Rio Branco",
            "São Paulo": "Acre",
            "SP": "AC"
        }

        replaced = replace_placeholders(sample_template, replacements)
        text = replaced["blocks"]["b1"]["title"]

        self.assertIn("Universidade Federal do Acre", text)
        self.assertIn("UFAC", text)
        self.assertIn("Rio Branco", text)
        self.assertIn("AC", text)

    def test_load_templates(self):
        """Valida o carregamento dos 4 arquivos de template JSON."""
        templates = load_templates()
        self.assertIn("home", templates)
        self.assertIn("sobre-nos", templates)
        self.assertIn("vida-na-ies", templates)
        self.assertIn("estudantes-internacionais", templates)

    def test_load_dataset(self):
        """Valida o carregamento do arquivo CSV de IES."""
        df = load_dataset("studyinbr/lista_ies_completa.csv")
        self.assertFalse(df.empty)
        self.assertIn("Sigla", df.columns)
        self.assertIn("Universidade", df.columns)
        self.assertIn("Onde criar", df.columns)


if __name__ == "__main__":
    unittest.main()
