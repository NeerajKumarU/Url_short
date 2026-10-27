(() => {
  const themeStorageKey = "theme";
  const accentStorageKey = "accent-color";
  const validThemes = ["light", "dark", "system"];
  const validAccents = ["purple", "blue", "emerald", "orange"];
  const themeLabels = {
    light: { label: "Light", icon: "☀" },
    dark: { label: "Dark", icon: "☾" },
    system: { label: "System", icon: "▣" },
  };
  const root = document.documentElement;
  const systemTheme = window.matchMedia?.("(prefers-color-scheme: dark)");
  const themeOptions = document.querySelectorAll("[data-theme-option]");
  const accentOptions = document.querySelectorAll("[data-accent-option]");
  const themeToggles = document.querySelectorAll("[data-theme-toggle]");
  const appearanceStatus = document.querySelector("#appearance-status");

  const announcePreference = (message) => {
    if (!appearanceStatus) return;
    appearanceStatus.textContent = message;
    window.setTimeout(() => { appearanceStatus.textContent = "Saved automatically"; }, 1600);
  };

  const applyTheme = (preference) => {
    const selected = validThemes.includes(preference) ? preference : "system";
    const effective = selected === "system" ? (systemTheme?.matches ? "dark" : "light") : selected;
    root.dataset.theme = effective;
    root.dataset.themePreference = selected;
    root.style.colorScheme = effective;
    themeOptions.forEach((control) => { control.checked = control.value === selected; });
    themeToggles.forEach((control) => {
      const current = themeLabels[selected];
      const next = validThemes[(validThemes.indexOf(selected) + 1) % validThemes.length];
      const icon = control.querySelector("[data-theme-toggle-icon]");
      const label = control.querySelector("[data-theme-toggle-label]");
      if (icon) icon.textContent = current.icon;
      if (label) label.textContent = current.label;
      control.setAttribute("aria-label", `Theme: ${current.label}. Change to ${themeLabels[next].label}`);
      control.title = `Theme: ${current.label}`;
    });
    const themeColor = document.querySelector("#theme-color-meta");
    if (themeColor) themeColor.content = effective === "dark" ? "#07090f" : "#f4f6fb";
  };

  const applyAccent = (preference) => {
    const selected = validAccents.includes(preference) ? preference : "purple";
    root.dataset.accent = selected;
    accentOptions.forEach((control) => { control.checked = control.value === selected; });
  };

  const savePreference = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_) { /* Keep the in-page choice. */ }
  };

  applyTheme(root.dataset.themePreference || "system");
  applyAccent(root.dataset.accent || "purple");

  themeOptions.forEach((control) => {
    control.addEventListener("change", () => {
      if (!control.checked) return;
      savePreference(themeStorageKey, control.value);
      applyTheme(control.value);
      announcePreference(`${themeLabels[control.value].label} theme selected`);
    });
  });

  accentOptions.forEach((control) => {
    control.addEventListener("change", () => {
      if (!control.checked) return;
      savePreference(accentStorageKey, control.value);
      applyAccent(control.value);
      announcePreference(`${control.value.charAt(0).toUpperCase()}${control.value.slice(1)} accent selected`);
    });
  });

  themeToggles.forEach((control) => {
    control.addEventListener("click", () => {
      const current = root.dataset.themePreference || "system";
      const next = validThemes[(validThemes.indexOf(current) + 1) % validThemes.length];
      savePreference(themeStorageKey, next);
      applyTheme(next);
      announcePreference(`${themeLabels[next].label} theme selected`);
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
