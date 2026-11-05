// Badges at the top of a site's page. With Lerd or Valet they become buttons that change PHP, Node and HTTPS.

import { esc, icon } from "../dom.mjs";
import { t } from "../i18n.mjs";

export function siteBadges(s, live) {
  const chip = (action, cls, inner, title) => live
    ? `<button type="button" class="badge badge-btn ${cls}" data-action="${action}" title="${esc(title)}">${inner}</button>`
    : `<span class="badge ${cls}" title="${esc(title)}">${inner}</span>`;
  return [
    chip("site-php", "", `PHP ${esc(s.php || "?")}`, live ? t("Trocar a versão de PHP do site") : t("Versão de PHP")),
    s.node || live ? chip("site-node", "", `Node ${esc(s.node || "?")}`, live ? t("Trocar a versão de Node do site") : t("Versão de Node")) : "",
    chip("site-https", s.secured ? "badge-ok" : "", `${icon(s.secured ? "lock" : "unlock")}${s.secured ? "HTTPS" : "HTTP"}`,
      live ? (s.secured ? t("Desligar HTTPS") : t("Ligar HTTPS")) : (s.secured ? t("Servido com HTTPS") : t("Sem HTTPS"))),
    !s.exists ? `<span class="badge badge-err">${icon("alert")}${t("pasta não encontrada")}</span>` : "",
  ].join("");
}
