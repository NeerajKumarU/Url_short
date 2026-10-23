(() => {
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
