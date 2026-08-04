// Minimal reusable hamburger wiring.
// Usage:
//   import { wireHamburger } from "./js/uiUtils.js";
//   wireHamburger({ buttonId: "menuBtn", navId: "main-nav" });

export function wireHamburger({
  buttonId = "menuBtn",
  navId = "main-nav",
  openText = "✕ Menu",
  closedText = "☰ Menu",
  closeOnLinkClick = true,
  useClassOpen = false,
} = {}) {
  const init = () => {
    const btn = document.getElementById(buttonId);
    const nav = document.getElementById(navId);
    if (!btn || !nav) return;

    // Prevent double-binding if called twice
    if (btn.dataset.wired === "true") return;
    btn.dataset.wired = "true";

    const setOpen = (open) => {
      if (useClassOpen) {
        nav.classList.toggle("open", open);
      } else {
        nav.dataset.open = open ? "true" : "false";
      }
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      // Only set text if button doesn't have child elements (spans for hamburger icon)
      if (btn.children.length === 0) {
        btn.textContent = open ? openText : closedText;
      }
    };

    // Initial state
    let open = false;
    if (useClassOpen) {
      open = nav.classList.contains("open");
    } else {
      open = nav.dataset.open === "true";
    }
    setOpen(open);

    btn.addEventListener("click", () => {
      let open;
      if (useClassOpen) {
        open = nav.classList.contains("open");
      } else {
        open = nav.dataset.open === "true";
      }
      setOpen(!open);
    });

    if (closeOnLinkClick) {
      nav.addEventListener("click", (e) => {
        if (e.target instanceof HTMLAnchorElement) setOpen(false);
      });
    }
  };

  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
}