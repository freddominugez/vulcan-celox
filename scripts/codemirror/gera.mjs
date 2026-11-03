// Gera web/vendor/codemirror.js em IIFE e reescreve no LICENSES.md a parte que lista os pacotes embutidos.
// Argumentos: <pasta com node_modules> <pasta web/vendor>
import { build } from "esbuild";
import { readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const [work, vendor] = process.argv.slice(2);
const MAX_BYTES = 800 * 1024;
const MARCA = "<!-- codemirror: gerado por scripts/vendorizar_codemirror.sh, não editar à mão -->";

const result = await build({
  absWorkingDir: work,
  entryPoints: ["entrada.js"],
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "CM",
  target: ["safari15"],
  legalComments: "none",
  charset: "utf8",
  metafile: true,
  write: false,
  banner: { js: "/* CodeMirror 6 e dependências, MIT. Lista completa em LICENSES.md. */" },
});
const code = result.outputFiles[0].contents;
if (code.length > MAX_BYTES) throw new Error(`codemirror.js com ${code.length} bytes, limite ${MAX_BYTES}`);
writeFileSync(join(vendor, "codemirror.js"), code);

const nomes = new Set();
for (const entrada of Object.keys(result.metafile.inputs)) {
  const m = entrada.match(/node_modules\/((?:@[^/]+\/)?[^/]+)\//);
  if (m) nomes.add(m[1]);
}

const blocos = [...nomes].sort().map((nome) => {
  const pasta = join(work, "node_modules", nome);
  const pkg = JSON.parse(readFileSync(join(pasta, "package.json"), "utf8"));
  if (pkg.license !== "MIT") throw new Error(`${nome}: licença ${pkg.license}, só MIT entra`);
  const arquivo = readdirSync(pasta).find((n) => /^licen[sc]e/i.test(n));
  if (!arquivo || !existsSync(join(pasta, arquivo))) throw new Error(`${nome}: sem arquivo de licença`);
  const texto = readFileSync(join(pasta, arquivo), "utf8").trim();
  return `## ${nome} ${pkg.version} (MIT)\n\n\`\`\`\n${texto}\n\`\`\``;
});

const caminho = join(vendor, "LICENSES.md");
const atual = readFileSync(caminho, "utf8");
const antes = atual.includes(MARCA) ? atual.slice(0, atual.indexOf(MARCA)) : atual.trimEnd() + "\n\n";
writeFileSync(caminho, `${antes}${MARCA}\n\n${blocos.join("\n\n")}\n`);
console.log(`codemirror.js: ${code.length} bytes, ${nomes.size} pacotes`);
