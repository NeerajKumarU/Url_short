(() => {
  const landing = document.querySelector("[data-landing]");
  if (!landing) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finePointer = window.matchMedia("(pointer: fine)");
  const nav = document.querySelector("[data-landing-nav]");
  const navLinks = document.querySelector("#landing-navigation");
  const navToggle = document.querySelector(".landing-menu-toggle");

  const updateNavigation = () => nav?.classList.toggle("is-scrolled", window.scrollY > 24);
  updateNavigation();
  window.addEventListener("scroll", updateNavigation, { passive: true });

  navToggle?.addEventListener("click", () => {
    const open = navLinks?.classList.toggle("is-open") || false;
    navToggle.setAttribute("aria-expanded", String(open));
  });
  navLinks?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
    navLinks.classList.remove("is-open");
    navToggle?.setAttribute("aria-expanded", "false");
  }));

  const revealItems = document.querySelectorAll("[data-reveal]");
  if (reducedMotion.matches || !("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6%" });
    revealItems.forEach((item) => observer.observe(item));
  }

  document.querySelectorAll(".spotlight-card").forEach((card) => {
    card.addEventListener("pointermove", (event) => {
      const bounds = card.getBoundingClientRect();
      card.style.setProperty("--spot-x", `${event.clientX - bounds.left}px`);
      card.style.setProperty("--spot-y", `${event.clientY - bounds.top}px`);
    });
  });

  if (finePointer.matches && !reducedMotion.matches) {
    const cursor = document.querySelector(".landing-cursor-glow");
    window.addEventListener("pointermove", (event) => {
      if (!cursor) return;
      cursor.style.left = `${event.clientX}px`;
      cursor.style.top = `${event.clientY}px`;
      cursor.classList.add("is-visible");
    }, { passive: true });
    document.querySelectorAll("a, button, summary").forEach((control) => {
      control.addEventListener("pointerenter", () => cursor?.classList.add("is-active"));
      control.addEventListener("pointerleave", () => cursor?.classList.remove("is-active"));
    });

    document.querySelectorAll(".magnetic-button").forEach((button) => {
      button.addEventListener("pointermove", (event) => {
        const bounds = button.getBoundingClientRect();
        const x = (event.clientX - bounds.left - bounds.width / 2) * 0.12;
        const y = (event.clientY - bounds.top - bounds.height / 2) * 0.12;
        button.style.transform = `translate(${x}px, ${y}px)`;
      });
      button.addEventListener("pointerleave", () => { button.style.transform = ""; });
    });
  }

  const palette = document.querySelector("[data-command-palette]");
  const paletteInput = document.querySelector("[data-command-input]");
  const paletteLinks = [...document.querySelectorAll("[data-command-results] a")];
  const openPalette = () => {
    if (!palette) return;
    if (typeof palette.showModal === "function") palette.showModal();
    else palette.setAttribute("open", "");
    window.setTimeout(() => paletteInput?.focus(), 0);
  };
  const closePalette = () => {
    if (!palette) return;
    if (typeof palette.close === "function") palette.close();
    else palette.removeAttribute("open");
  };

  document.querySelectorAll("[data-command-open]").forEach((button) => button.addEventListener("click", openPalette));
  palette?.addEventListener("click", (event) => { if (event.target === palette) closePalette(); });
  paletteLinks.forEach((link) => link.addEventListener("click", closePalette));
  paletteInput?.addEventListener("input", () => {
    const query = paletteInput.value.trim().toLowerCase();
    paletteLinks.forEach((link) => { link.hidden = Boolean(query) && !link.textContent.toLowerCase().includes(query); });
  });

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      palette?.open ? closePalette() : openPalette();
    }
    if (event.key === "Escape") {
      navLinks?.classList.remove("is-open");
      navToggle?.setAttribute("aria-expanded", "false");
    }
  });

  const faqItems = document.querySelectorAll(".faq-grid details");
  faqItems.forEach((item) => item.addEventListener("toggle", () => {
    if (!item.open) return;
    faqItems.forEach((other) => { if (other !== item) other.open = false; });
  }));
})();
