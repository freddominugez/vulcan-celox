import unittest

from vulcan_celox.core import i18n
from vulcan_celox.core.redact import MASK, MASK_EN, masked_count, redact

# synthetic values, assembled in parts so no scanner mistakes them for real secrets
ANT = "sk-ant-" + "api03-" + "Ab1" * 12
GH = "ghp_" + "Z9y8" * 8
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
JWT = "eyJ" + "hbGciOiJIUzI1" + ".eyJ" + "zdWIiOiIxMjM0" + "." + "SflKxwRJSMeKKF2QT4"


class RedactTest(unittest.TestCase):
    def check(self, text, must_hide, must_keep=()):
        out, count = redact(text)
        self.assertGreaterEqual(count, 1, text)
        for secret in must_hide:
            self.assertNotIn(secret, out)
        for kept in must_keep:
            self.assertIn(kept, out)
        return out

    def test_chaves_conhecidas(self):
        self.check(f"export ANTHROPIC_API_KEY={ANT}", [ANT], ["ANTHROPIC_API_KEY="])
        self.check(f"git remote set-url origin https://{GH}@github.com/x/y", [GH])
        self.check(f"aws configure set aws_access_key_id {AWS}", [AWS])
        self.check(f"curl -H 'Authorization: Bearer {JWT}' https://api", [JWT], ["Authorization: Bearer "])
        self.check("key " + "sb_secret_" + "abcDEF123456789", ["abcDEF123456789"])

    def test_variaveis_urls_e_flags(self):
        self.check("DB_PASSWORD=Sup3rS3nha!", ["Sup3rS3nha!"], ["DB_PASSWORD="])
        self.check('APP_KEY="base64:Qm9sYS1kZS1uZXZl"', ["Qm9sYS1kZS1uZXZl"], ['APP_KEY="'])
        self.check("DATABASE_URL=postgres://app:m1nhaSenha@db:5432/app", ["m1nhaSenha"], ["postgres://app:"])
        self.check("redis-cli -u redis://default:s3gr3d0@cache:6379", ["s3gr3d0"])
        self.check("php artisan user:create --password=admin123", ["admin123"], ["--password="])
        self.check("mysql -uroot -pr00tpass laravel", ["r00tpass"], ["mysql -uroot -p"])
        out = self.check("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAAB3Nza\n-----END OPENSSH PRIVATE KEY-----", ["AAAAB3Nza"])
        self.assertIn("chave privada removida", out)

    def test_senha_em_comando(self):
        self.check("curl -u fred:minha-senha https://x.test/a", ["minha-senha"], ["fred", "https://x.test/a"])
        self.check("curl -s --user=fred:minha-senha https://x.test", ["minha-senha"], ["fred"])
        self.check("sshpass -p minha-senha ssh a@b", ["minha-senha"], ["ssh a@b"])

    def test_texto_comum_intacto(self):
        for text in ("php artisan migrate --seed", "MAX_TOKENS=8000", "AUTH_GUARD=true", "cd ~/Lerd/loja && ls -la",
                     "DB_PASSWORD=${DB_PASSWORD}", "composer require laravel/sanctum", "SESSION_DRIVER=file"):
            self.assertEqual(redact(text), (text, 0), text)

    def test_idempotente(self):
        once, _ = redact(f"TOKEN={ANT}")
        self.assertEqual(redact(once), (once, 0))
        self.assertTrue(MASK in once or MASK_EN in once)


class CutPrivateKeyTest(unittest.TestCase):
    BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\nabcdefghijklmnopqrstuvwxyz0123456789ABCDEF"

    def test_so_o_fim_sobrou(self):
        masked, _ = redact(f"antes\n{self.BODY}\n-----END RSA PRIVATE KEY-----\ndepois")
        self.assertNotIn("MIIEvQ", masked)
        self.assertIn("antes", masked)
        self.assertIn("depois", masked)

    def test_so_o_comeco_sobrou(self):
        masked, _ = redact(f"-----BEGIN PRIVATE KEY-----\n{self.BODY}")
        self.assertNotIn("MIIEvQ", masked)

    def test_mascarar_de_novo_nao_muda_nada(self):
        text = ("DB_PASSWORD=abc123 mysql://u:p4ss@host/db --token xyz Bearer abcdefghijklmnop "
                "ghp_abcdefghijklmnopqrstuvwxyz mysql -psenha\n-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----")
        once, _ = redact(text)
        self.assertEqual(redact(once)[0], once)


class IdiomaDaMarcaTest(unittest.TestCase):
    """[segredo] in Portuguese and [secret] in English; either spelling counts as already masked."""

    def setUp(self):
        self.addCleanup(i18n.set_language, i18n.language())

    def masked(self, language, text):
        i18n.set_language(language)
        return redact(text)

    def test_as_duas_grafias(self):
        self.assertEqual(self.masked("pt", "DB_PASSWORD=abc12345")[0], "DB_PASSWORD=[segredo]")
        self.assertEqual(self.masked("en", "DB_PASSWORD=abc12345")[0], "DB_PASSWORD=[secret]")
        self.assertEqual(self.masked("en", f"export K={ANT}")[0], "export K=[secret]")

    def test_mascarar_de_novo_em_qualquer_idioma(self):
        text = ("DB_PASSWORD=abc123 mysql://u:p4ss@host/db --token xyz Bearer abcdefghijklmnop curl -u a:b https://x "
                "sshpass -p s3nha ssh a@b ghp_abcdefghijklmnopqrstuvwxyz mysql -psenha")
        for first, second in (("pt", "en"), ("en", "pt"), ("en", "en"), ("pt", "pt")):
            with self.subTest(first=first, second=second):
                once, count = self.masked(first, text)
                again, more = self.masked(second, once)
                self.assertEqual((again, more), (once, 0))
                self.assertEqual(masked_count(once), count)

    def test_memoria_antiga_em_portugues_com_a_interface_em_ingles(self):
        old = "comando: DB_PASSWORD=[segredo]\nmysql://app:[segredo]@db/x\nnovo: API_KEY=outra-chave-123"
        out, count = self.masked("en", old)
        self.assertEqual(count, 1)
        self.assertIn("DB_PASSWORD=[segredo]", out)
        self.assertIn("mysql://app:[segredo]@db/x", out)
        self.assertIn("API_KEY=[secret]", out)
        self.assertEqual(masked_count(out), 3)
