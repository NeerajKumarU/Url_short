(() => {
  const themeStorageKey = "orbitlink-theme";
  const root = document.documentElement;
  const systemTheme = window.matchMedia?.("(prefers-color-scheme: dark)");
  const themeSelects = document.querySelectorAll("[data-theme-select]");
  const applyTheme = (preference) => {
    const selected = ["light", "dark", "system"].includes(preference) ? preference : "system";
    const effective = selected === "system" ? (systemTheme?.matches ? "dark" : "light") : selected;
    root.dataset.theme = effective;
    root.dataset.themePreference = selected;
    root.style.colorScheme = effective;
    themeSelects.forEach((control) => { control.value = selected; });
    const themeColor = document.querySelector("#theme-color-meta");
    if (themeColor) themeColor.content = effective === "dark" ? "#07090f" : "#f4f6fb";
  };
  applyTheme(root.dataset.themePreference || "system");
  themeSelects.forEach((control) => {
    control.addEventListener("change", () => {
      const preference = control.value;
      try { localStorage.setItem(themeStorageKey, preference); } catch (_) { /* Keep the in-page choice. */ }
      applyTheme(preference);
    });
  });
  systemTheme?.addEventListener?.("change", () => {
    if (root.dataset.themePreference === "system") applyTheme("system");
  });

  const toggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".nav-menu");
  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  const sidebar = document.querySelector(".app-sidebar");
  const sidebarToggle = document.querySelector(".sidebar-toggle");
  const sidebarClose = document.querySelector(".sidebar-close");
  const sidebarBackdrop = document.querySelector(".sidebar-backdrop");
  const setSidebar = (open) => {
    if (!sidebar || !sidebarToggle || !sidebarBackdrop) return;
    sidebar.classList.toggle("is-open", open);
    sidebarBackdrop.classList.toggle("is-open", open);
    sidebarToggle.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("sidebar-open", open);
  };
  sidebarToggle?.addEventListener("click", () => setSidebar(!sidebar.classList.contains("is-open")));
  sidebarClose?.addEventListener("click", () => setSidebar(false));
  sidebarBackdrop?.addEventListener("click", () => setSidebar(false));
  sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setSidebar(false)));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSidebar(false);
  });

  document.querySelectorAll(".copy-button").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        const original = button.textContent;
        button.textContent = "Copied";
        window.setTimeout(() => { button.textContent = original; }, 1600);
      } catch (_) {
        window.prompt("Copy this link:", button.dataset.copy);
      }
    });
  });

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
})();
