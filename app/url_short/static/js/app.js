(() => {
  const themeStorageKey = "theme";
  const accentStorageKey = "accent-color";
  const sidebarStorageKey = "orbitlink-sidebar-collapsed";
  const validThemes = ["light", "dark", "system"];
  const validAccents = ["purple", "blue", "emerald", "orange"];
  const themeLabels = {
    light: { label: "Light", icon: "☀" },
    dark: { label: "Dark", icon: "☾" },
    system: { label: "System", icon: "▣" },
  };
  const root = document.documentElement;
  const systemTheme = window.matchMedia?.("(prefers-color-scheme: dark)");
  const desktopSidebar = window.matchMedia?.("(min-width: 1081px)");
  const themeOptions = document.querySelectorAll("[data-theme-option]");
  const accentOptions = document.querySelectorAll("[data-accent-option]");
  const themeToggles = document.querySelectorAll("[data-theme-toggle]");
  const appearanceStatus = document.querySelector("#appearance-status");

  const storageGet = (key) => {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  };
  const storageSet = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_) { /* Keep the in-page choice. */ }
  };

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

  applyTheme(root.dataset.themePreference || "system");
  applyAccent(root.dataset.accent || "purple");

  themeOptions.forEach((control) => {
    control.addEventListener("change", () => {
      if (!control.checked) return;
      storageSet(themeStorageKey, control.value);
      applyTheme(control.value);
      announcePreference(`${themeLabels[control.value].label} theme selected`);
    });
  });

  accentOptions.forEach((control) => {
    control.addEventListener("change", () => {
      if (!control.checked) return;
      storageSet(accentStorageKey, control.value);
      applyAccent(control.value);
      announcePreference(`${control.value.charAt(0).toUpperCase()}${control.value.slice(1)} accent selected`);
    });
  });

  themeToggles.forEach((control) => {
    control.addEventListener("click", () => {
      const current = root.dataset.themePreference || "system";
      const next = validThemes[(validThemes.indexOf(current) + 1) % validThemes.length];
      storageSet(themeStorageKey, next);
      applyTheme(next);
      announcePreference(`${themeLabels[next].label} theme selected`);
    });
  });

  systemTheme?.addEventListener?.("change", () => {
    if (root.dataset.themePreference === "system") applyTheme("system");
  });

  const publicToggle = document.querySelector(".nav-toggle");
  const publicMenu = document.querySelector(".nav-menu");
  if (publicToggle && publicMenu) {
    publicToggle.addEventListener("click", () => {
      const open = publicMenu.classList.toggle("is-open");
      publicToggle.setAttribute("aria-expanded", String(open));
    });
  }

  const sidebar = document.querySelector(".app-sidebar");
  const sidebarToggle = document.querySelector(".sidebar-toggle");
  const sidebarClose = document.querySelector(".sidebar-close");
  const sidebarBackdrop = document.querySelector(".sidebar-backdrop");
  const setMobileSidebar = (open) => {
    if (!sidebar || !sidebarToggle || !sidebarBackdrop) return;
    sidebar.classList.toggle("is-open", open);
    sidebarBackdrop.classList.toggle("is-open", open);
    sidebarToggle.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("sidebar-open", open);
  };
  const setDesktopSidebar = (collapsed) => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    sidebarToggle?.setAttribute("aria-expanded", String(!collapsed));
    storageSet(sidebarStorageKey, collapsed ? "true" : "false");
  };
  const syncSidebarMode = () => {
    if (desktopSidebar?.matches) {
      setMobileSidebar(false);
      setDesktopSidebar(storageGet(sidebarStorageKey) === "true");
    } else {
      document.body.classList.remove("sidebar-collapsed");
      sidebarToggle?.setAttribute("aria-expanded", "false");
    }
  };
  syncSidebarMode();
  desktopSidebar?.addEventListener?.("change", syncSidebarMode);
  sidebarToggle?.addEventListener("click", () => {
    if (desktopSidebar?.matches) setDesktopSidebar(!document.body.classList.contains("sidebar-collapsed"));
    else setMobileSidebar(!sidebar?.classList.contains("is-open"));
  });
  sidebarClose?.addEventListener("click", () => setMobileSidebar(false));
  sidebarBackdrop?.addEventListener("click", () => setMobileSidebar(false));
  sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
    if (!desktopSidebar?.matches) setMobileSidebar(false);
  }));

  const showToast = (message, kind = "success") => {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("aria-live", "polite");
      document.body.append(stack);
    }
    const toast = document.createElement("div");
    toast.className = `notice notice-${kind}`;
    const text = document.createElement("span");
    text.textContent = message;
    const close = document.createElement("button");
    close.type = "button";
    close.className = "notice-close";
    close.setAttribute("aria-label", "Dismiss notification");
    close.textContent = "×";
    toast.append(text, close);
    stack.append(toast);
    const dismiss = () => {
      toast.classList.add("is-leaving");
      window.setTimeout(() => toast.remove(), 180);
    };
    close.addEventListener("click", dismiss);
    window.setTimeout(dismiss, 4200);
  };

  document.querySelectorAll(".notice").forEach((notice) => {
    const close = notice.querySelector(".notice-close");
    const dismiss = () => {
      notice.classList.add("is-leaving");
      window.setTimeout(() => notice.remove(), 180);
    };
    close?.addEventListener("click", dismiss);
    window.setTimeout(dismiss, 7000);
  });

  document.querySelectorAll(".copy-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const value = button.dataset.copy || "";
      try {
        await navigator.clipboard.writeText(value);
        showToast("Copied to clipboard");
      } catch (_) {
        window.prompt("Copy this value:", value);
      }
    });
  });

  const topbarMenus = document.querySelectorAll(".topbar-menu");
  topbarMenus.forEach((menu) => {
    menu.addEventListener("toggle", () => {
      if (!menu.open) return;
      topbarMenus.forEach((other) => { if (other !== menu) other.open = false; });
    });
  });
  document.addEventListener("click", (event) => {
    topbarMenus.forEach((menu) => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });

  document.querySelectorAll(".action-menu").forEach((menu) => {
    menu.addEventListener("toggle", () => {
      if (!menu.open) return;
      document.querySelectorAll(".action-menu[open]").forEach((other) => { if (other !== menu) other.open = false; });
    });
  });

  const confirmDialog = document.querySelector("#confirm-dialog");
  const confirmMessage = document.querySelector("#confirm-message");
  let pendingForm = null;
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!confirmDialog?.showModal) {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        return;
      }
      event.preventDefault();
      pendingForm = form;
      if (confirmMessage) confirmMessage.textContent = form.dataset.confirm;
      confirmDialog.showModal();
    });
  });
  confirmDialog?.addEventListener("close", () => {
    if (confirmDialog.returnValue === "confirm" && pendingForm) {
      HTMLFormElement.prototype.submit.call(pendingForm);
    }
    pendingForm = null;
  });

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      if (form.dataset.confirm) return;
      const submit = form.querySelector("button[type='submit']");
      if (!submit || submit.closest(".profile-popover")) return;
      submit.setAttribute("aria-busy", "true");
      submit.classList.add("is-loading");
    });
  });

  const globalSearch = document.querySelector("#global-search-input");
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setMobileSidebar(false);
      topbarMenus.forEach((menu) => { menu.open = false; });
      document.querySelectorAll(".action-menu[open]").forEach((menu) => { menu.open = false; });
    }
    const target = event.target;
    const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
    if (event.key === "/" && !typing && globalSearch) {
      event.preventDefault();
      globalSearch.focus();
    }
  });
})();
