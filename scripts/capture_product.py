"""Capture the actual macOS app with isolated demonstration projects in the three product locales."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sites/celox-landing/dist/assets/screens"
EVIDENCE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/product-captures"
APP = ROOT / "dist/Vulcan Celox.app/Contents/MacOS/vulcan-celox"


def capture():
    OUT.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="celox-demo-") as temp:
        base = Path(temp)
        project = base / "atlas"
        (project / "src").mkdir(parents=True)
        (project / "docs").mkdir()
        (project / "package.json").write_text(json.dumps({"name": "atlas", "private": True,
            "scripts": {"dev": "vite --host 127.0.0.1", "build": "vite build", "test": "vitest run"},
            "dependencies": {"react": "^19.0.0", "vite": "^6.0.0"}}))
        (project / "src/checkout.ts").write_text('''import { validateOrder } from "./validation";
import type { Order, Receipt } from "./types";

export async function checkout(order: Order): Promise<Receipt> {
  const validated = validateOrder(order);
  const response = await fetch("/api/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(validated),
  });

  if (!response.ok) {
    throw new Error(`Order failed: ${response.status}`);
  }

  const receipt: Receipt = await response.json();
  return { ...receipt, items: validated.items.length };
}
''')
        (project / "src/types.ts").write_text("export interface Order { items: string[]; customer: string; }\nexport interface Receipt { id: string; items: number; }\n")
        (project / "src/validation.ts").write_text("import type { Order } from './types';\nexport const validateOrder = (order: Order) => order;\n")
        (project / "README.md").write_text("# Atlas\n\nDemonstration workspace for Vulcan Celox.\n")
        (project / "docs/release.md").write_text("# Release checklist\n\n- Review\n- Test\n- Commit\n")
        port_file = base / "api.port"
        with port_file.open("w") as output:
            fake = subprocess.Popen([sys.executable, "-I", str(ROOT / "tests/tools/fake_lerd_api.py"),
                                     "--site-path", "atlas=" + str(project)], stdout=output, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if port_file.exists() and port_file.stat().st_size:
                    break
                time.sleep(0.1)
            port = port_file.read_text().strip().splitlines()[0]
            for lang in ("pt", "en", "es"):
                for name, route in (("overview", "#/overview"), ("code", "#/codigo"), ("agents", "#/agentes"),
                                    ("prompts", "#/prompts"), ("terminals", "#/terminals"), ("settings", "#/config")):
                    if os.environ.get("VULCAN_CAPTURE_SCREENS") and name not in os.environ["VULCAN_CAPTURE_SCREENS"].split(","):
                        continue
                    env = dict(os.environ)
                    env.update(VULCAN_CELOX_HOME=str(base / (name + lang)), VULCAN_LEGACY_HOME=str(base / "legacy"),
                        VULCAN_VALET_HOME=str(base / "valet"), VULCAN_VALET_BIN=str(base / "absent"),
                        VULCAN_LERD_BIN=str(ROOT / "tests/tools/fake-lerd"), VULCAN_LERD_DATA=str(base / "lerd"),
                        VULCAN_LERD_API="http://127.0.0.1:" + port, VULCAN_KEYSTORE="memory", VULCAN_AUTOSTART="0",
                        VULCAN_UPDATE_CHECK="0", VULCAN_LANGUAGE=lang, HOME=str(base), SHELL="/bin/sh",
                        CLAUDE_CONFIG_DIR=str(ROOT / "tests/fixtures/agents/claude"), CODEX_HOME=str(ROOT / "tests/fixtures/agents/codex"))
                    labels = {"pt": "Revisar autenticação", "en": "Review authentication", "es": "Revisar autenticación"}
                    common = """const A=await import('./js/api.mjs');
await A.patch('/api/preferences',{theme:'escuro'});
await A.post('/api/node-projects',{path:DEMO,name:'atlas'});
await A.post('/api/tasks',{title:TITLE,priority:1});
window.dispatchEvent(new CustomEvent('vulcan-node-changed'));
const M=await import('./js/app.mjs'); await M.loadNodeProjects(); M.route();
const wait=async(fn)=>{for(let i=0;i<100;i++){const v=fn();if(v)return v;await new Promise(r=>setTimeout(r,40));}throw new Error('capture timeout');};
""".replace("DEMO", json.dumps(str(project))).replace("TITLE", json.dumps(labels[lang]))
                    extra = ""
                    if name == "code":
                        extra = "await A.post('/api/files/roots',{path:DEMO}); location.hash='#/codigo/'+encodeURIComponent(DEMO)+'/'+encodeURIComponent('src/checkout.ts'); await wait(()=>document.querySelector('.cm-content'));".replace("DEMO", json.dumps(str(project)))
                    elif name == "terminals":
                        extra = """const T=await import('./js/terminal-pool.mjs');
await T.terminals.create({cwd:DEMO,title:'Atlas / app',theme:'homebrew',command:"printf 'Atlas workspace\\n\\n$ npm run dev\\n  VITE ready\\n  Local: http://127.0.0.1:5173/\\n\\nDemonstration output.\\n'",agent:'shell'});
await T.terminals.create({cwd:DEMO,title:'Atlas / review',theme:'oceano',command:"printf 'Review checklist\\n\\n  [x] Review changes\\n  [x] Run tests\\n  [ ] Open pull request\\n'",agent:'shell'});
await wait(()=>document.querySelector('.terminal-workspace, .tw, .xterm'));
""".replace("DEMO", json.dumps(str(project)))
                    elif name == "settings":
                        extra = "const b=await wait(()=>document.querySelector('[data-lang=es]')); b.closest('section').scrollIntoView({block:'start'});"
                    elif name == "prompts":
                        extra = "const b=await wait(()=>document.querySelector('[data-pick=seguranca]')); b.click();"
                    js = "(async()=>{const tag='product capture pending';window.__vtErrors.push(tag);try{" + common + extra + "window.__vtErrors.splice(window.__vtErrors.indexOf(tag),1);}catch(e){window.__vtErrors.push(String(e));}})();"
                    target = OUT / (name + "-" + lang + ".png")
                    run = subprocess.run([str(APP), "--snapshot", str(target), "--route", route, "--size", "1320x840", "--wait", "7", "--eval", js], env=env, capture_output=True, text=True, timeout=60)
                    (EVIDENCE / (name + "-" + lang + ".log")).write_text(run.stdout + run.stderr)
                    if run.returncode == 0:
                        subprocess.run(["sips", "-Z", "1800", str(target), "--out", str(target)], check=True, stdout=subprocess.DEVNULL)
                    results.append({"screen": name, "language": lang, "exit_code": run.returncode,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None})
                    print(name, lang, run.returncode, flush=True)
        finally:
            fake.terminate()
            fake.wait(timeout=10)
    (EVIDENCE / "product-captures.json").write_text(json.dumps(results, indent=2) + "\n")
    return 1 if any(row["exit_code"] for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(capture())
