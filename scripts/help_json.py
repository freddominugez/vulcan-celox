"""Grava o conteúdo da Ajuda no layout do repositório: um bloco por linha, listas com um item por linha."""

import json
import sys

J = lambda v: json.dumps(v, ensure_ascii=False)


def block(b):
    key, value = next((k, v) for k, v in b.items() if isinstance(v, list)) if any(isinstance(v, list) for v in b.values()) else (None, None)
    if key is None:
        return "        " + J(b)
    rest = {k: v for k, v in b.items() if k != key}
    head = "        {" + "".join(f"{J(k)}: {J(v)}, " for k, v in rest.items()) + f"{J(key)}: ["
    return head + "\n" + ",\n".join("          " + J(x) for x in value) + "\n        ]}"


def dump(d):
    out = ["{", f'  "versao": {J(d["versao"])},', '  "secoes": [']
    secs = []
    for s in d["secoes"]:
        lines = ["    {"]
        for k, v in s.items():
            if k != "blocos":
                lines.append(f"      {J(k)}: {J(v)},")
        lines.append('      "blocos": [\n' + ",\n".join(block(b) for b in s["blocos"]) + "\n      ]")
        lines.append("    }")
        secs.append("\n".join(lines))
    out.append(",\n".join(secs))
    out.append("  ],")
    out.append('  "faq": [\n' + ",\n".join("    " + J(f) for f in d["faq"]) + "\n  ]")
    out.append("}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    path = sys.argv[1]
    data = json.load(open(path, encoding="utf-8"))
    open(path, "w", encoding="utf-8").write(dump(data))
