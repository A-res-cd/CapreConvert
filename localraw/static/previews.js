import { request, attachment } from "./api.js";
import { imageExportType, jobConverter } from "./converters.js";

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 12;
let gallery = null;
let onError = () => {};

function node(tag, content = "", className = "") {
  const element = document.createElement(tag);
  element.textContent = content;
  if (className) element.className = className;
  return element;
}
function readPreference(jobId) {
  try {
    const value = JSON.parse(localStorage.getItem("localraw-preview:" + jobId));
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}
function remember() {
  if (!gallery) return;
  try {
    localStorage.setItem(
      "localraw-preview:" + gallery.id,
      JSON.stringify({
        selected: [...gallery.selected],
        active: gallery.active,
        page: gallery.page,
      }),
    );
  } catch {
    /* Browser preferences never authorize an export. */
  }
}
function previewURL(file, thumbnail = false) {
  return (
    attachment(gallery.id, `previews/${encodeURIComponent(file.output_id)}`) +
    (thumbnail ? "?thumbnail=true" : "")
  );
}
function viewedPhoto() {
  return gallery?.files.find((file) => file.output_id === gallery.active);
}

function selectionControls() {
  const total = gallery?.files.length || 0;
  const count = gallery?.selected.size || 0;
  const busy = gallery?.busy || false;
  const type = gallery?.type || "JPG";
  $("export-selection-count").textContent =
    `${count} of ${total} results selected`;
  $("export-selected").disabled = !count || busy;
  $("export-selected").textContent = busy
    ? `Preparing selected ${type}s…`
    : !count
      ? `Export selected ${type}s ↓`
      : `Export ${count} ${type}${count === 1 ? " ↓" : "s · ZIP ↓"}`;
  $("select-all-previews").disabled = !total || busy || count === total;
  $("clear-preview-selection").disabled = !count || busy;
  $("select-viewed-photo").disabled = !viewedPhoto() || busy;
  $("select-viewed-photo").checked = Boolean(
    gallery?.selected.has(gallery.active),
  );
  for (const card of $("preview-grid").children) {
    const selected = gallery.selected.has(card.dataset.outputId);
    card.classList.toggle("is-selected", selected);
    card.classList.toggle(
      "is-viewed",
      card.dataset.outputId === gallery.active,
    );
    card.querySelector("input").checked = selected;
    card.querySelector("input").disabled = busy;
    card
      .querySelector("button")
      .setAttribute(
        "aria-pressed",
        String(card.dataset.outputId === gallery.active),
      );
  }
}
function selectPhoto(id, checked) {
  if (!gallery || gallery.busy) return;
  if (checked) gallery.selected.add(id);
  else gallery.selected.delete(id);
  $("export-status").textContent = "";
  selectionControls();
  remember();
}
function showPhoto(id) {
  if (!gallery) return;
  gallery.active = id;
  pdfPage = 1;
  const index = gallery.files.findIndex((file) => file.output_id === id);
  gallery.page = Math.floor(index / PAGE_SIZE);
  renderGrid();
  renderViewer();
  selectionControls();
  remember();
}
let previewSequence = 0;
let blobURL = null;
let pdfPage = 1;
let pdfPages = 1;
async function renderViewer() {
  const file = viewedPhoto();
  if (!file) return;
  const current = gallery;
  const sequence = ++previewSequence;
  const image = $("active-preview");
  if (blobURL) {
    URL.revokeObjectURL(blobURL);
    blobURL = null;
  }
  image.hidden = true;
  image.removeAttribute("src");
  $("docx-content").hidden = true;
  $("docx-content").replaceChildren();
  $("pdf-preview-controls").hidden = true;
  $("preview-message").hidden = false;
  $("preview-message").textContent = "Loading output preview…";
  $("preview-filename").textContent = file.output_name;
  const dimensions = file.width
    ? `${file.width} × ${file.height} pixels · `
    : file.pages
      ? `${file.pages} pages · `
      : "";
  const savings = Number.isFinite(file.savings_percent)
    ? ` · ${Math.abs(file.savings_percent).toFixed(1)}% ${file.savings_percent < 0 ? "larger" : "smaller"}`
    : "";
  $("preview-dimensions").textContent =
    `${gallery.type} · ${dimensions}${(file.size_bytes / 1024).toFixed(1)} KiB${savings} · ${(file.warnings || []).join(" ")}`;
  $("preview-position").textContent =
    `Result ${gallery.files.indexOf(file) + 1} of ${gallery.files.length}`;
  $("previous-preview").disabled = gallery.files.length < 2;
  $("next-preview").disabled = gallery.files.length < 2;
  $("preview-download").href = attachment(
    gallery.id,
    `results/${encodeURIComponent(file.output_id)}`,
  );
  const kind = gallery.kind;
  if (kind === "image" && file.preview) {
    image.alt = `Reduced output preview of ${file.output_name}`;
    image.src = previewURL(file);
    return;
  }
  if (kind === "none") {
    $("preview-message").textContent =
      "Preview unavailable for this format. Download remains available.";
    return;
  }
  try {
    const response = await fetch(
      attachment(
        current.id,
        `output-preview/${encodeURIComponent(file.output_id)}`,
      ) + `?page=${kind === "pdf" ? pdfPage : 1}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) {
      const failure = await response.json();
      throw new Error(
        failure.error?.message ||
          failure.message ||
          "Preview unavailable. Retry shortly; download remains available.",
      );
    }
    if (gallery !== current || sequence !== previewSequence) return;
    if (kind === "docx") {
      const content = await response.json();
      if (gallery !== current || sequence !== previewSequence) return;
      const container = $("docx-content");
      container.append(node("p", content.notice, "field-hint"));
      for (const block of content.blocks || []) {
        if (block.type === "paragraph") container.append(node("p", block.text));
        if (block.type === "table") {
          const table = node("table");
          for (const row of block.rows) {
            const tr = node("tr");
            for (const cell of row) tr.append(node("td", cell));
            table.append(tr);
          }
          container.append(table);
        }
      }
      if (content.truncated)
        container.append(
          node(
            "p",
            "Preview truncated at its content limit. Download the document for all content.",
            "field-hint",
          ),
        );
      container.hidden = false;
      $("preview-message").hidden = true;
    } else {
      if (gallery !== current || sequence !== previewSequence) return;
      image.alt = `Reduced output preview of ${file.output_name}`;
      image.src = response.url;
      if (kind === "pdf") {
        pdfPages = Number(response.headers.get("X-Preview-Pages")) || 1;
        $("pdf-preview-controls").hidden = false;
        $("pdf-page-status").textContent = `Page ${pdfPage} of ${pdfPages}`;
        $("pdf-previous").disabled = pdfPage <= 1;
        $("pdf-next").disabled = pdfPage >= pdfPages;
      }
    }
  } catch (error) {
    if (gallery === current && sequence === previewSequence)
      $("preview-message").textContent =
        `${error.message} Direct Download still works.`;
  }
}

function renderGrid() {
  const pageCount = Math.max(1, Math.ceil(gallery.files.length / PAGE_SIZE));
  gallery.page = Math.min(Math.max(0, gallery.page), pageCount - 1);
  const files = gallery.files.slice(
    gallery.page * PAGE_SIZE,
    (gallery.page + 1) * PAGE_SIZE,
  );
  const signature = JSON.stringify(
    files.map((file) => [file.output_id, Boolean(file.preview)]),
  );
  if ($("preview-grid").dataset.signature !== signature) {
    const focused = document.activeElement.closest?.(".preview-tile");
    const focusId = focused?.dataset.outputId;
    const focusType = document.activeElement.tagName;
    const cards = files.map((file) => {
      const card = node("article", "", "preview-tile");
      card.dataset.outputId = file.output_id;
      const open = node("button", "", "preview-open");
      open.type = "button";
      open.setAttribute("aria-label", `Preview ${file.output_name}`);
      if (file.preview?.thumbnail) {
        const image = document.createElement("img");
        image.src = previewURL(file, true);
        image.alt = "";
        image.loading = "lazy";
        image.decoding = "async";
        image.width = file.preview.thumbnail.width;
        image.height = file.preview.thumbnail.height;
        image.addEventListener(
          "error",
          () => {
            image.replaceWith(
              node("span", "Preview unavailable", "thumbnail-placeholder"),
            );
          },
          { once: true },
        );
        open.append(image);
      } else open.append(node("span", "View output", "thumbnail-placeholder"));
      open.append(node("span", file.output_name, "preview-tile-name"));
      open.addEventListener("click", () => showPhoto(file.output_id));
      const label = node("label", "", "preview-tile-selection");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.setAttribute(
        "aria-label",
        `Export ${file.output_name} as ${gallery.type}`,
      );
      checkbox.addEventListener("change", () =>
        selectPhoto(file.output_id, checkbox.checked),
      );
      label.append(checkbox, node("span", `Export ${gallery.type}`));
      card.append(open, label);
      return card;
    });
    $("preview-grid").replaceChildren(...cards);
    $("preview-grid").dataset.signature = signature;
    if (focusId) {
      const retained = cards.find((card) => card.dataset.outputId === focusId);
      retained
        ?.querySelector(focusType === "INPUT" ? "input" : "button")
        .focus({ preventScroll: true });
    }
  }
  $("preview-page").textContent = `${gallery.page + 1} / ${pageCount}`;
  $("previous-preview-page").disabled = gallery.page === 0;
  $("next-preview-page").disabled = gallery.page + 1 >= pageCount;
}

export function clearPreviews() {
  gallery = null;
  previewSequence += 1;
  if (blobURL) URL.revokeObjectURL(blobURL);
  blobURL = null;
  $("docx-content").hidden = true;
  $("preview-section").hidden = true;
  $("active-preview").hidden = true;
  $("active-preview").removeAttribute("src");
  $("preview-grid").replaceChildren();
  delete $("preview-grid").dataset.signature;
  $("export-status").textContent = "";
  selectionControls();
}
export function renderPreviews(job, files) {
  const ready = files.filter((file) => file.state === "succeeded");
  const signature = JSON.stringify(ready);
  if (gallery?.id === job.id && gallery.signature === signature) return;
  if (gallery?.id !== job.id) {
    clearPreviews();
    const saved = readPreference(job.id);
    gallery = {
      id: job.id,
      type: imageExportType(job),
      kind: jobConverter(job).preview_kind || "none",
      selected: new Set(
        Array.isArray(saved.selected)
          ? saved.selected.filter((id) => typeof id === "string")
          : [],
      ),
      active: saved.active,
      page: Number.isInteger(saved.page) ? saved.page : 0,
      busy: false,
    };
  }
  gallery.files = ready;
  gallery.signature = signature;
  const available = new Set(ready.map((file) => file.output_id));
  gallery.selected = new Set(
    [...gallery.selected].filter((id) => available.has(id)),
  );
  if (!available.has(gallery.active)) gallery.active = ready[0]?.output_id;
  $("preview-section").hidden = false;
  $("preview-count").textContent =
    `${ready.length} result${ready.length === 1 ? "" : "s"} ready`;
  $("preview-intro-copy").textContent =
    `Review committed ${gallery.type}s, then choose results to export. Images shown here are reduced previews.`;
  $("preview-export-hint").textContent =
    `One result downloads as ${gallery.type}. Multiple results download in a ZIP, with folders preserved.`;
  $("preview-empty").hidden = Boolean(ready.length);
  $("preview-layout").hidden = !ready.length;
  renderGrid();
  renderViewer();
  selectionControls();
}
async function exportSelected() {
  if (!gallery || gallery.busy || !gallery.selected.size) return;
  const current = gallery;
  const selected = current.files.filter((file) =>
    current.selected.has(file.output_id),
  );
  current.busy = true;
  selectionControls();
  $("export-status").textContent =
    selected.length > 1
      ? `Preparing a ZIP containing only your selected ${current.type}s…`
      : `Starting ${current.type} download…`;
  try {
    let url;
    if (selected.length === 1)
      url = attachment(
        current.id,
        `results/${encodeURIComponent(selected[0].output_id)}`,
      );
    else {
      const result = await request(`/jobs/${current.id}/exports`, {
        method: "POST",
        body: JSON.stringify({
          output_ids: selected.map((file) => file.output_id),
        }),
      });
      url = attachment(
        current.id,
        `exports/${encodeURIComponent(result.export_id)}`,
      );
    }
    if (gallery === current) {
      $("export-status").textContent =
        `${selected.length} selected ${current.type}${selected.length === 1 ? "" : "s"} ready. Download starting…`;
      window.location.assign(url);
    }
  } catch (error) {
    if (gallery === current) {
      $("export-status").textContent =
        "Export could not start. Your selection is kept; try again.";
      onError(error);
    }
  } finally {
    current.busy = false;
    if (gallery === current) selectionControls();
  }
}
export function initializePreviews(reportError) {
  for (const [id, delta] of [
    ["pdf-previous", -1],
    ["pdf-next", 1],
  ])
    $(id).addEventListener("click", () => {
      if (!gallery || pdfPage + delta < 1 || pdfPage + delta > pdfPages) return;
      pdfPage += delta;
      renderViewer();
    });
  onError = reportError;
  $("select-all-previews").addEventListener("click", () => {
    if (!gallery || gallery.busy) return;
    gallery.selected = new Set(gallery.files.map((file) => file.output_id));
    selectionControls();
    remember();
  });
  $("clear-preview-selection").addEventListener("click", () => {
    if (!gallery || gallery.busy) return;
    gallery.selected.clear();
    selectionControls();
    remember();
  });
  $("select-viewed-photo").addEventListener("change", (event) =>
    selectPhoto(gallery.active, event.target.checked),
  );
  for (const [id, delta] of [
    ["previous-preview", -1],
    ["next-preview", 1],
  ])
    $(id).addEventListener("click", () => {
      if (!gallery?.files.length) return;
      const index = gallery.files.findIndex(
        (file) => file.output_id === gallery.active,
      );
      showPhoto(
        gallery.files[
          (index + delta + gallery.files.length) % gallery.files.length
        ].output_id,
      );
    });
  for (const [id, delta] of [
    ["previous-preview-page", -1],
    ["next-preview-page", 1],
  ])
    $(id).addEventListener("click", () => {
      if (!gallery) return;
      gallery.page += delta;
      renderGrid();
      selectionControls();
      remember();
    });
  $("active-preview").addEventListener("load", () => {
    $("active-preview").hidden = false;
    $("preview-message").hidden = true;
  });
  $("active-preview").addEventListener("error", () => {
    $("active-preview").hidden = true;
    $("preview-message").hidden = false;
    $("preview-message").textContent =
      `Preview could not load. Refresh the batch to try again; ${gallery?.type || "image"} downloads remain available.`;
  });
  $("export-selected").addEventListener("click", exportSelected);
}
