import unittest

from vulcan_celox.core.redact import MASK, redact

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

    def test_texto_comum_intacto(self):
        for text in ("php artisan migrate --seed", "MAX_TOKENS=8000", "AUTH_GUARD=true", "cd ~/Lerd/loja && ls -la",
                     "DB_PASSWORD=${DB_PASSWORD}", "composer require laravel/sanctum", "SESSION_DRIVER=file"):
            self.assertEqual(redact(text), (text, 0), text)

    def test_idempotente(self):
        once, _ = redact(f"TOKEN={ANT}")
        self.assertEqual(redact(once), (once, 0))
        self.assertIn(MASK, once)


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
