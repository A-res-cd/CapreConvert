// Paper workspace shell. Native links remain usable without a navigation framework.
export function initializeNavigation() {
  const root = document.documentElement;
  const toggle = document.getElementById("navigation-toggle");
  const scrim = document.getElementById("navigation-scrim");
  const sidebar = document.getElementById("workspace-navigation");
  const main = document.getElementById("main");
  const mobile = matchMedia("(max-width: 900px)");
  const links = [...sidebar.querySelectorAll(".navigation-link")];
  const preview = document.getElementById("preview-section");
  const previewLink = document.getElementById("preview-navigation-link");
  let view = "home";
  let conversionLabel = "Convert files";
  let collapsed = false;
  let drawerOpen = false;
  try {
    collapsed = localStorage.getItem("localraw-navigation") === "collapsed";
  } catch {
    /* optional preference */
  }

  function sync() {
    root.dataset.navigation = collapsed ? "collapsed" : "expanded";
    root.toggleAttribute("data-navigation-open", mobile.matches && drawerOpen);
    toggle.setAttribute(
      "aria-expanded",
      String(mobile.matches ? drawerOpen : !collapsed),
    );
    scrim.hidden = !(mobile.matches && drawerOpen);
    main.inert = mobile.matches && drawerOpen;
    sidebar.inert = mobile.matches && !drawerOpen;
  }
  function closeDrawer(restoreFocus = false) {
    drawerOpen = false;
    sync();
    if (restoreFocus) toggle.focus();
  }
  function current(id) {
    const active = links.find(
      (link) =>
        link.dataset.section === (id === "converter" ? "home-view" : id),
    );
    if (!active) return;
    for (const link of links) {
      const selected = link === active;
      link.classList.toggle("is-current", selected);
      if (selected) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    }
    document.getElementById("current-section-label").textContent =
      view === "converter" ? conversionLabel : active.textContent.trim();
  }
  toggle.addEventListener("click", () => {
    if (mobile.matches) {
      drawerOpen = !drawerOpen;
      sync();
      if (drawerOpen) links[0].focus();
    } else {
      collapsed = !collapsed;
      sync();
      try {
        localStorage.setItem(
          "localraw-navigation",
          collapsed ? "collapsed" : "expanded",
        );
      } catch {
        /* optional preference */
      }
    }
  });
  scrim.addEventListener("click", () => closeDrawer(true));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && drawerOpen) {
      event.preventDefault();
      closeDrawer(true);
    }
  });
  for (const link of links)
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") {
        event.preventDefault();
        return;
      }
      current(link.dataset.section);
      if (mobile.matches) closeDrawer();
    });
  sidebar
    .querySelector(".navigation-help")
    .addEventListener("click", () => closeDrawer());
  function previewAvailability() {
    previewLink.setAttribute("aria-disabled", String(preview.hidden));
    if (preview.hidden && previewLink.classList.contains("is-current"))
      current(view === "home" ? "home-view" : "converter");
  }
  new MutationObserver(previewAvailability).observe(preview, {
    attributes: true,
    attributeFilter: ["hidden"],
  });
  const sections = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter(
        (entry) =>
          entry.isIntersecting &&
          !entry.target.hidden &&
          (view === "home"
            ? entry.target.id === "home-view"
            : entry.target.id !== "home-view"),
      );
      if (visible.length) current(visible[visible.length - 1].target.id);
    },
    { rootMargin: "-70px 0px -55% 0px" },
  );
  for (const id of [
    "home-view",
    "converter",
    "settings-title",
    "activity",
    "preview-section",
  ])
    sections.observe(document.getElementById(id));
  mobile.addEventListener("change", () => {
    drawerOpen = false;
    sync();
  });
  document.addEventListener("capre:route", (event) => {
    view = event.detail.view;
    conversionLabel = document.getElementById("converter-title").textContent;
    current(view === "home" ? "home-view" : "converter");
    if (mobile.matches) closeDrawer();
  });
  previewAvailability();
  sync();
}
