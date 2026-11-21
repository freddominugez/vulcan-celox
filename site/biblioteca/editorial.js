"use strict";

for (const button of document.querySelectorAll("button[data-copy]")) {
  button.addEventListener("click", async () => {
    const source = document.getElementById(button.dataset.copy);
    const status = button.parentElement.querySelector(".copy-status");
    try {
      await navigator.clipboard.writeText(source.textContent);
      status.textContent = "Prompt copiado.";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = "Texto selecionado. Use o atalho de copiar ou baixe o Markdown.";
    }
  });
}
