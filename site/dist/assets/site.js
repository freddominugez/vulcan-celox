/* Progressive enhancements: navigation, screenshots, accessible dialog and keyboard controls. */
(() => {
  "use strict";
  document.documentElement.classList.add("js");
  const data = JSON.parse(document.getElementById("page-data").textContent);
  const menuButton = document.querySelector(".menu-toggle");
  const menu = document.getElementById("mobile-menu");
  const setMenu = (open, focus = false) => {
    menu.hidden = !open;
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.setAttribute("aria-label", open ? data.closeMenu : data.menu);
    if (focus) menuButton.focus();
  };
  menuButton.addEventListener("click", () => setMenu(menu.hidden));
  menu.addEventListener("click", (event) => { if (event.target.closest("a")) setMenu(false); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) setMenu(false, true);
  });
  const desktop = window.matchMedia("(width > 62.5rem)");
  desktop.addEventListener("change", (event) => { if (event.matches) setMenu(false); });

  // Locale links keep the visitor's place rather than sending them to the beginning.
  const syncLanguageLinks = () => {
    const hash = location.hash;
    document.querySelectorAll("[data-language]").forEach((link) => {
      link.hash = hash;
    });
  };
  syncLanguageLinks();
  window.addEventListener("hashchange", syncLanguageLinks);

  const tabs = [...document.querySelectorAll("[data-screen]")];
  const tabList = document.querySelector(".screen-tabs");
  const mobileGallery = window.matchMedia("(max-width: 47.5rem)");
  const syncTabOrientation = () => tabList.setAttribute("aria-orientation", mobileGallery.matches ? "horizontal" : "vertical");
  syncTabOrientation();
  mobileGallery.addEventListener("change", syncTabOrientation);
  const galleryImage = document.getElementById("gallery-image");
  const galleryTrigger = document.querySelector("#showcase-panel [data-zoom]");
  const galleryPanel = document.getElementById("showcase-panel");
  const galleryCaption = document.getElementById("gallery-caption");
  const windowLabel = document.getElementById("gallery-window-label");
  const selectScreen = (id, focus = false) => {
    const screen = data.screens.find((item) => item.id === id);
    if (!screen) return;
    for (const tab of tabs) {
      const selected = tab.dataset.screen === id;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    }
    const imagePath = `/assets/screens/${screen.id}-${data.screenLang}.png`;
    galleryImage.src = imagePath;
    galleryTrigger.href = imagePath;
    galleryImage.alt = screen.alt;
    galleryCaption.textContent = screen.caption;
    windowLabel.textContent = screen.title;
    galleryPanel.setAttribute("aria-labelledby", `tab-${screen.id}`);
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectScreen(tab.dataset.screen));
    tab.addEventListener("keydown", (event) => {
      const next = mobileGallery.matches ? "ArrowRight" : "ArrowDown";
      const previous = mobileGallery.matches ? "ArrowLeft" : "ArrowUp";
      const keys = {
        [next]: (index + 1) % tabs.length,
        [previous]: (index - 1 + tabs.length) % tabs.length,
        Home: 0,
        End: tabs.length - 1,
      };
      if (event.key in keys) {
        event.preventDefault();
        selectScreen(tabs[keys[event.key]].dataset.screen, true);
      }
    });
  });

  const dialog = document.getElementById("screenshot-dialog");
  const dialogImage = document.getElementById("dialog-image");
  const dialogCaption = document.getElementById("dialog-caption");
  let returnFocus = null;
  const openImage = (image, trigger, caption) => {
    if (typeof dialog.showModal !== "function") return false;
    returnFocus = trigger;
    dialogImage.src = image.src;
    dialogImage.alt = image.alt;
    dialogCaption.textContent = caption || image.alt;
    dialog.showModal();
    document.body.classList.add("dialog-open");
    return true;
  };
  for (const trigger of document.querySelectorAll("[data-zoom]")) {
    trigger.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const image = trigger.querySelector("img");
      const caption = trigger === galleryTrigger ? galleryCaption.textContent : image.alt;
      if (openImage(image, trigger, caption)) event.preventDefault();
    });
  }
  const galleryZoom = document.querySelector("[data-gallery-zoom]");
  galleryZoom.addEventListener("click", () => openImage(galleryImage, galleryZoom, galleryCaption.textContent));
  document.querySelector("[data-close-dialog]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    }
  });
  dialog.addEventListener("close", () => {
    document.body.classList.remove("dialog-open");
    if (returnFocus) returnFocus.focus({ preventScroll: true });
  });

})();
