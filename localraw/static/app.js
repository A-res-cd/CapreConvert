import { request, sendFile, setCSRF, attachment } from "./api.js";
import { initializeNavigation } from "./navigation.js";
import {
  converterFor,
  jobConverter,
  configureConverters,
  supportedConversion,
} from "./converters.js";
import { initializePicker } from "./picker.js";
import {
  initializePreviews,
  renderPreviews,
  clearPreviews,
} from "./previews.js";

const $ = (id) => document.getElementById(id);
const terminal = new Set([
  "completed",
  "completed_with_errors",
  "cancelled",
  "failed",
  "interrupted",
]);
const labels = {
  queued: "In the queue",
  inspecting: "Looking through your files",
  converting: "Developing your photos",
  packaging: "Wrapping things up",
  completed: "Your JPEGs are ready.",
  completed_with_errors: "Ready, with a few exceptions.",
  cancelling: "Stopping your batch…",
  cancelled: "Batch cancelled.",
  failed: "This batch needs another look.",
  interrupted: "Host restarted. Batch interrupted.",
};
const state = {
  files: [],
  connected: false,
  uploading: false,
  abort: null,
  job: null,
  timer: null,
  generation: 0,
  historyLimit: 25,
  filesSignature: "",
  conversion: "cr3_to_jpg",
  view: "home",
  history: [],
  restoreSequence: 0,
};
const preference = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* Storage is only a UI hint. */
    }
  },
};
const bytes = (value) =>
  value >= 1024 ** 3
    ? `${(value / 1024 ** 3).toFixed(2)} GiB`
    : value >= 1024 ** 2
      ? `${(value / 1024 ** 2).toFixed(1)} MiB`
      : `${value.toLocaleString()} bytes`;
function text(tag, content, className) {
  const node = document.createElement(tag);
  node.textContent = content;
  if (className) node.className = className;
  return node;
}
function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
function report(error) {
  notice(
    error.message || "Host is unavailable. Check your connection and refresh.",
  );
  if (error.status === 401) {
    clearPreviews();
    state.connected = false;
    $("pair-panel").hidden = state.view === "home";
    controls();
  }
}
function activeConverter() {
  const definition = converterFor(state.conversion) || converterFor();
  const capability = state.capabilities?.conversions?.find(
    (entry) => entry.id === definition.id,
  );
  return {
    input_extensions: [],
    output_extension: "",
    ...definition,
    available: false,
    ...capability,
  };
}
function resetJobPanel() {
  clearTimeout(state.timer);
  state.generation += 1;
  state.job = null;
  state.filesSignature = "";
  clearPreviews();
  $("job-panel").hidden = true;
  $("empty-results").hidden = false;
}
function updateWorkspace() {
  const kind = activeConverter();
  const raw = kind.engine === "raw";
  const raster = kind.engine === "raster";
  const image = raw || raster;
  $("home-view").hidden = state.view !== "home";
  $("converter-view").hidden = state.view !== "converter";
  $("pair-panel").hidden = state.connected || state.view === "home";
  document.querySelector(".navigation-help").href =
    state.view === "home" ? "#home-privacy-note" : "#privacy-note";
  document.documentElement.dataset.view = state.view;
  document.documentElement.dataset.conversion = kind.id;
  $("converter-title").textContent = kind.label;
  document.querySelector(".converter-hero").dataset.conversionLabel =
    kind.label;
  $("converter-description").textContent = kind.description;
  $("converter-limitations").replaceChildren(
    ...(kind.limitations || []).map((limitation) => text("p", limitation)),
  );
  $("converter-availability").hidden = kind.available !== false;
  $("converter-availability").textContent =
    kind.setup_message || "This converter needs setup on the host computer.";
  $("input-heading-copy").textContent = image
    ? "Add your photos"
    : "Add your documents";
  $("input-types").textContent = kind.input_extensions
    .map((extension) => extension.slice(1).toUpperCase())
    .join(" & ");
  $("input-card-title").textContent = image
    ? "Bring your photos in"
    : "Bring your documents in";
  $("file-input").accept = kind.input_extensions.join(",");
  $("drop-zone").setAttribute(
    "aria-label",
    raw
      ? "Choose CR3 photos or ZIP archives"
      : `Choose ${kind.source} ${raster ? "images" : "documents"}`,
  );
  $("drop-title").textContent = image
    ? "Good photos start here."
    : "Your next document starts here.";
  $("drop-copy").textContent = raw
    ? "Drop CR3 photos or ZIP archives"
    : `Drop ${kind.source} ${raster ? "images" : "documents"}`;
  $("settings-output-label").textContent = `${kind.output} OUTPUT`;
  $("settings-card-title").textContent = `${kind.output} settings`;
  $("jpeg-quality-settings").hidden = kind.id !== "cr3_to_jpg";
  $("white-balance-setting").hidden = !raw;
  $("raw-metadata-settings").hidden = !image;
  $("raster-settings").hidden = !raster;
  $("metadata-hint").textContent =
    raster || state.capabilities?.metadata_available
      ? "Supported capture fields only. Other tags are omitted."
      : "ExifTool unavailable. RAW capture tags omitted with a warning.";
  $("raster-jpeg-setting").hidden = kind.output_extension !== ".jpg";
  $("raster-webp-setting").hidden = kind.output_extension !== ".webp";
  $("raster-png-setting").hidden = kind.output_extension !== ".png";
  $("raster-background-setting").hidden = kind.output_extension !== ".jpg";
  $("settings-footnote").textContent = kind.footnote;
  for (const option of $("concurrency").options)
    option.textContent = `${option.value} ${raw ? "photo" : "file"}${option.value === "1" ? " · lower memory" : "s · more memory"}`;
  if (state.capabilities) {
    const limits = state.capabilities.limits;
    $("upload-limits").textContent = raw
      ? `CR3 up to ${bytes(limits.raw_max_bytes)} · ZIP up to ${bytes(limits.zip_max_bytes)}`
      : `${kind.source} up to ${bytes((raster ? limits.raster_max_bytes : limits.document_max_bytes) || 64 * 1024 ** 2)} per file`;
  }
  controls();
  document.dispatchEvent(
    new CustomEvent("capre:route", {
      detail: { view: state.view, conversion: kind.id },
    }),
  );
}
async function restoreWorkspaceJob() {
  if (
    !state.connected ||
    state.view !== "converter" ||
    state.job ||
    state.uploading
  )
    return;
  const sequence = ++state.restoreSequence;
  const conversion = state.conversion;
  let candidate = state.history.find(
    (job) => jobConverter(job).id === conversion,
  );
  const remembered = preference.get("localraw-job");
  if (remembered) {
    try {
      const owned = await request(`/jobs/${encodeURIComponent(remembered)}`);
      if (jobConverter(owned).id === conversion) candidate = owned;
    } catch (error) {
      if (error.status !== 404) throw error;
    }
  }
  if (
    sequence === state.restoreSequence &&
    state.view === "converter" &&
    state.conversion === conversion &&
    !state.job &&
    candidate
  )
    await showJob(candidate.id, candidate, { reveal: false });
}
function applyRoute({ restore = true } = {}) {
  const fragment = location.hash.slice(1);
  const parameters = new URLSearchParams(fragment);
  const selected = parameters.get("convert");
  const validSelected = selected && supportedConversion(selected);
  const workspaceAnchor = new Set([
    "converter",
    "settings-title",
    "activity",
    "preview-section",
    "privacy-note",
  ]);
  const view =
    validSelected || workspaceAnchor.has(fragment)
      ? "converter"
      : fragment === "main"
        ? state.view
        : "home";
  const conversion = validSelected
    ? selected
    : state.conversion || preference.get("localraw-conversion") || "cr3_to_jpg";
  if (state.uploading && conversion !== state.conversion) {
    notice("Finish or cancel the current upload before changing converters.");
    history.replaceState(
      null,
      "",
      `${location.pathname}${location.search}#convert=${state.conversion}`,
    );
    return;
  }
  if (conversion !== state.conversion) {
    state.files = [];
    resetJobPanel();
    state.conversion = conversion;
    selection();
  }
  state.view = view;
  if (view === "converter") picker.synchronize(state.conversion);
  if (selected && !validSelected && state.capabilities)
    notice("Unknown or unsupported converter. Choose file types below.");
  preference.set("localraw-conversion", state.conversion);
  updateWorkspace();
  if (
    workspaceAnchor.has(fragment) ||
    fragment === "main" ||
    fragment === "home-privacy-note"
  )
    requestAnimationFrame(() =>
      $(fragment)?.scrollIntoView({ block: "start" }),
    );
  if (restore) restoreWorkspaceJob().catch(report);
}
function openConverter(conversion, { restore = false } = {}) {
  if (!supportedConversion(conversion)) {
    notice("Unknown or unsupported converter.");
    return;
  }
  const fragment = `#convert=${conversion}`;
  if (location.hash !== fragment)
    history.pushState(null, "", location.pathname + location.search + fragment);
  applyRoute({ restore });
  if (restore && state.view === "converter" && state.conversion === conversion)
    requestAnimationFrame(() => {
      $("converter-title").tabIndex = -1;
      $("converter-title").focus({ preventScroll: true });
      document
        .querySelector(".converter-hero")
        .scrollIntoView({ block: "start" });
    });
}
function controls() {
  const busy = state.uploading;
  const kind = activeConverter();
  const disabled =
    !state.connected || !state.capabilities || busy || kind.available === false;
  $("converter").setAttribute("aria-busy", String(busy));
  $("drop-zone").disabled = disabled;
  $("settings-fields").disabled = disabled;
  $("start-button").disabled = disabled || !state.files.length;
  $("clear-files").disabled = busy;
  $("refresh-history").disabled = !state.connected;
  $("start-label").textContent = busy
    ? "Uploading your files…"
    : state.files.length
      ? `Convert ${state.files.length} input${state.files.length === 1 ? "" : "s"} to ${kind.output}`
      : `Convert to ${kind.output}`;
  $("gps").disabled = kind.engine === "document" || !$("metadata").checked;
}
function selection() {
  $("selected-files").replaceChildren();
  $("selection").hidden = !state.files.length;
  $("selection-count").textContent =
    `${state.files.length} selected · ${bytes(state.files.reduce((sum, file) => sum + file.size, 0))}`;
  state.files.forEach((file, index) => {
    const row = text("li", "", "file-row");
    row.append(
      text("span", file.name.split(".").pop().toUpperCase(), "file-icon"),
    );
    const info = text("div", "", "file-info");
    info.append(
      text("p", file.name, "file-name"),
      text("p", bytes(file.size), "field-hint"),
    );
    const remove = text("button", "×", "remove-file");
    remove.type = "button";
    remove.disabled = state.uploading;
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    remove.addEventListener("click", () => {
      state.files.splice(index, 1);
      selection();
    });
    row.append(info, remove);
    $("selected-files").append(row);
  });
  controls();
}
function addFiles(files) {
  if (!state.connected || state.uploading) return;
  const rejected = [];
  for (const file of files) {
    const extension = "." + file.name.split(".").pop().toLowerCase();
    const kind = activeConverter();
    if (!kind.input_extensions.includes(extension)) {
      rejected.push(file.name);
      continue;
    }
    const limit =
      extension === ".zip"
        ? state.capabilities.limits.zip_max_bytes
        : kind.is_raw
          ? state.capabilities.limits.raw_max_bytes
          : (kind.engine === "raster"
              ? state.capabilities.limits.raster_max_bytes
              : state.capabilities.limits.document_max_bytes) || 64 * 1024 ** 2;
    if (!file.size || file.size > limit) {
      rejected.push(`${file.name} (empty or too large)`);
      continue;
    }
    state.files.push(file);
  }
  notice(rejected.length ? `Could not add: ${rejected.join(", ")}` : "");
  selection();
}
function settings() {
  return {
    conversion: state.conversion,
    ...(activeConverter().engine === "raster"
      ? {
          raster: {
            preset: $("raster-preset").value,
            max_width: $("max-width").value
              ? Number($("max-width").value)
              : null,
            max_height: $("max-height").value
              ? Number($("max-height").value)
              : null,
            jpeg_quality: $("raster-jpeg-quality").value
              ? Number($("raster-jpeg-quality").value)
              : null,
            webp_quality: $("webp-quality").value
              ? Number($("webp-quality").value)
              : null,
            png_compression: $("png-compression").value
              ? Number($("png-compression").value)
              : null,
            webp_lossless: $("webp-lossless").checked,
            background: $("raster-background").value,
          },
        }
      : {}),
    jpeg_quality: Number($("quality").value),
    filename_suffix: $("suffix").value,
    white_balance: $("white-balance").value,
    preserve_metadata: $("metadata").checked,
    include_gps: $("metadata").checked && $("gps").checked,
    concurrency: Number($("concurrency").value),
  };
}
async function refreshHistory() {
  if (!state.connected) return;
  const result = { items: [], total: 0 };
  while (result.items.length < state.historyLimit) {
    const batch = await request(
      `/jobs?offset=${result.items.length}&limit=${Math.min(100, state.historyLimit - result.items.length)}`,
    );
    result.items.push(...batch.items);
    result.total = batch.total;
    if (result.items.length >= result.total) break;
  }
  $("job-history").replaceChildren();
  state.history = result.items;
  $("more-history").hidden = result.total <= result.items.length;
  if (!result.items.length)
    $("job-history").append(
      text(
        "p",
        "A fresh start. Your batches will appear here.",
        "empty-history",
      ),
    );
  result.items.forEach((job) => {
    const button = text(
      "button",
      "",
      "history-item" + (state.job?.id === job.id ? " selected" : ""),
    );
    button.type = "button";
    button.setAttribute("aria-pressed", String(state.job?.id === job.id));
    button.append(
      text(
        "strong",
        new Date(job.created_at * 1000).toLocaleString([], {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        }),
      ),
      text(
        "span",
        `${job.counters.succeeded} ready · ${jobConverter(job).label} · ${job.state.replaceAll("_", " ")}`,
      ),
    );
    button.addEventListener("click", () => {
      if (!state.uploading) showJob(job.id, job).catch(report);
    });
    $("job-history").append(button);
  });
  return result;
}
function renderFiles(files) {
  const signature = JSON.stringify(files);
  if (signature === state.filesSignature) return;
  state.filesSignature = signature;
  $("result-files").replaceChildren();
  const successful = files.filter((file) => file.state === "succeeded");
  $("download-primary").hidden = successful.length !== 1;
  if (successful.length === 1)
    $("download-primary").href = attachment(
      state.job.id,
      `results/${successful[0].output_id}`,
    );
  files.forEach((file) => {
    const row = text("li", "", "file-row");
    const extension = (file.output_name || file.name)
      .split(".")
      .pop()
      .toUpperCase();
    row.append(text("span", extension, "file-icon"));
    const info = text("div", "", "file-info");
    info.append(text("p", file.output_name || file.name, "file-name"));
    const details =
      file.state === "succeeded"
        ? `${file.width && file.height ? `${file.width} × ${file.height} · ` : ""}${bytes(file.size_bytes)}`
        : file.state.replaceAll("_", " ");
    info.append(text("p", details, "field-hint"));
    if (file.source_bytes)
      info.append(
        text(
          "p",
          `${bytes(file.source_bytes)} input → ${bytes(file.size_bytes || 0)} output${Number.isFinite(file.savings_percent) ? ` · ${Math.abs(file.savings_percent).toFixed(1)}% ${file.savings_percent < 0 ? "larger" : "smaller"}` : ""}${file.source_width ? ` · source ${file.source_width} × ${file.source_height}` : ""}`,
          "field-hint",
        ),
      );
    if (file.error) info.append(text("p", file.error, "error-text"));
    file.warnings.forEach((warning) =>
      info.append(text("p", warning, "field-hint")),
    );
    if (file.skipped_names?.length) {
      const detail = document.createElement("details");
      detail.className = "field-hint";
      detail.append(
        text(
          "summary",
          `Skipped entries (${file.skipped_count}; first ${file.skipped_names.length} shown)`,
        ),
      );
      file.skipped_names.forEach((name) => detail.append(text("p", name)));
      info.append(detail);
    }
    row.append(info);
    if (file.state === "succeeded") {
      const link = text(
        "a",
        `${extension === "JPG" ? "JPEG" : extension} ↓`,
        "result-link",
      );
      link.href = attachment(
        state.job.id,
        `results/${encodeURIComponent(file.output_id)}`,
      );
      link.setAttribute("aria-label", `Download ${file.output_name}`);
      row.append(link);
    } else row.append(text("span", file.state, "file-status"));
    $("result-files").append(row);
  });
}
function renderJob(job) {
  state.job = job;
  $("job-panel").hidden = false;
  $("empty-results").hidden = true;
  $("job-label").textContent = `BATCH ${job.id.slice(0, 8).toUpperCase()}`;
  const kind = jobConverter(job);
  $("job-state").textContent =
    job.state === "completed"
      ? kind.completed
      : job.state === "converting" && kind.engine === "document"
        ? "Converting your documents"
        : labels[job.state] || job.state;
  $("job-badge").textContent = job.state.replaceAll("_", " ");
  $("job-badge").className =
    "state-badge" +
    (job.state === "completed"
      ? " success"
      : ["failed", "completed_with_errors", "interrupted"].includes(job.state)
        ? " error"
        : "");
  const c = job.counters;
  $("review-previews").hidden = !c.succeeded;
  $("review-previews").textContent = "Output preview & export";
  $("job-detail").textContent =
    `${c.finished} of ${c.total} files finished · ${c.succeeded} ready · ${c.failed} failed · ${c.skipped} skipped · ${c.cancelled} cancelled`;
  if (c.total) {
    $("job-progress").max = c.total;
    $("job-progress").value = c.finished;
  } else $("job-progress").removeAttribute("value");
  $("upload-detail").textContent = job.active_files
    .map(
      (file) =>
        `${file.name}: ${file.state}${file.state === "decoding" ? " (no percentage available)" : ""}`,
    )
    .join(" · ");
  $("job-warnings").replaceChildren(
    ...job.warnings.map((warning) => text("p", warning)),
  );
  $("cancel-button").hidden = terminal.has(job.state);
  $("cancel-button").disabled = job.state === "cancelling";
  $("download-all").hidden = job.package_status !== "ready";
  $("download-all").href = attachment(job.id, "archive");
  $("download-report").hidden = !terminal.has(job.state);
  $("download-report").href = attachment(job.id, "summary");
  $("retry-button").hidden = !terminal.has(job.state);
  $("delete-job").hidden = !terminal.has(job.state);
  $("job-expiry").textContent = job.expires_at
    ? `Available until ${new Date(job.expires_at * 1000).toLocaleString()}. Deleting a batch removes its workspace copies.`
    : "Successful files stay available if you cancel. Browser disconnect does not cancel work.";
}
async function allFiles(id) {
  const files = [];
  for (let offset = 0; ; offset += 100) {
    const result = await request(
      `/jobs/${id}/files?offset=${offset}&limit=100`,
    );
    files.push(...result.items);
    if (files.length >= result.total) return files;
  }
}
async function poll(id, generation) {
  try {
    const [job, files] = await Promise.all([
      request(`/jobs/${id}`),
      allFiles(id),
    ]);
    if (generation !== state.generation) return;
    renderJob(job);
    renderFiles(files);
    renderPreviews(job, files);
    if (!terminal.has(job.state))
      state.timer = setTimeout(
        () => poll(id, generation),
        document.hidden ? 5000 : 1000,
      );
    else await refreshHistory();
  } catch (error) {
    if (generation !== state.generation) return;
    report(error);
    if (error.status === 404) {
      clearPreviews();
      $("job-state").textContent = "Batch expired or was deleted.";
      $("cancel-button").hidden = true;
    } else if (error.status !== 401)
      state.timer = setTimeout(() => poll(id, generation), 5000);
  }
}
async function showJob(id, summary = null, { reveal = true } = {}) {
  const owned = summary || (await request(`/jobs/${id}`));
  if (reveal) openConverter(jobConverter(owned).id);
  clearPreviews();
  clearTimeout(state.timer);
  state.generation += 1;
  state.filesSignature = "";
  preference.set("localraw-job", id);
  await poll(id, state.generation);
}
function idempotencyKey() {
  return Array.from(crypto.getRandomValues(new Uint32Array(4)), (number) =>
    number.toString(16).padStart(8, "0"),
  ).join("");
}
async function createJob(ids, chosen) {
  const options = {
    method: "POST",
    body: JSON.stringify({ upload_ids: ids, settings: chosen }),
    headers: { "Idempotency-Key": idempotencyKey() },
  };
  try {
    return await request("/jobs", options);
  } catch (error) {
    if (error.status) throw error;
    return request("/jobs", options);
  }
}
async function start(event) {
  event.preventDefault();
  if (state.uploading || !state.files.length) return;
  if (!/^[\p{L}\p{N}_ -]*$/u.test($("suffix").value)) {
    notice(
      "Suffix can contain letters, numbers, spaces, underscores and hyphens.",
    );
    $("suffix").focus();
    return;
  }
  if (
    state.files.length > 500 ||
    state.files.reduce((sum, file) => sum + file.size, 0) >
      state.capabilities.limits.job_upload_max_bytes
  ) {
    notice(
      "Batch exceeds the input count or total upload limit. Split it into smaller batches.",
    );
    return;
  }
  notice();
  state.uploading = true;
  state.abort = new AbortController();
  clearTimeout(state.timer);
  state.generation += 1;
  state.job = null;
  clearPreviews();
  selection();
  const chosen = settings(),
    inputs = [...state.files],
    ids = [];
  const total = inputs.reduce((sum, file) => sum + file.size, 0);
  let completedBytes = 0,
    accepted = false;
  $("empty-results").hidden = true;
  $("job-panel").hidden = false;
  $("job-state").textContent = "Bringing your files in…";
  $("job-label").textContent = "UPLOAD";
  $("job-badge").textContent = "Uploading";
  $("job-badge").className = "state-badge";
  $("job-progress").max = total;
  $("job-progress").value = 0;
  $("job-progress").setAttribute("aria-label", "Uploaded bytes");
  $("job-detail").textContent = `0 of ${inputs.length} inputs uploaded`;
  $("cancel-button").hidden = false;
  $("cancel-button").disabled = false;
  for (const id of [
    "review-previews",
    "download-all",
    "download-report",
    "retry-button",
    "delete-job",
  ])
    $(id).hidden = true;
  $("job-warnings").replaceChildren();
  $("result-files").replaceChildren();
  $("job-expiry").textContent = "";
  try {
    for (let index = 0; index < inputs.length; index += 1) {
      if (state.abort.signal.aborted)
        throw new DOMException("Cancelled", "AbortError");
      const file = inputs[index];
      const registration = await request("/uploads", {
        method: "POST",
        body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
      });
      ids.push(registration.upload_id);
      await sendFile(
        registration.upload_id,
        file,
        (loaded) => {
          $("job-progress").value = completedBytes + loaded;
          $("upload-detail").textContent =
            `${file.name} · ${bytes(loaded)} / ${bytes(file.size)} · batch ${bytes(completedBytes + loaded)} / ${bytes(total)}`;
        },
        state.abort.signal,
      );
      completedBytes += file.size;
      $("job-detail").textContent =
        `${index + 1} of ${inputs.length} inputs uploaded`;
    }
    if (state.abort.signal.aborted)
      throw new DOMException("Cancelled", "AbortError");
    const job = await createJob(ids, chosen);
    accepted = true;
    if (state.abort.signal.aborted)
      await request(`/jobs/${job.id}/cancel`, { method: "POST" });
    state.files = [];
    $("job-progress").setAttribute("aria-label", "Completed files");
    await showJob(job.id, job, { reveal: state.view === "converter" });
    await refreshHistory();
  } catch (error) {
    if (error.name === "AbortError") {
      $("job-state").textContent = "Upload cancelled.";
      $("job-badge").textContent = "Cancelled";
      $("upload-detail").textContent = "You can choose files and start again.";
    } else {
      report(error);
      $("job-state").textContent = "Upload or job creation needs another try.";
    }
    $("cancel-button").hidden = true;
    if (!accepted)
      await Promise.allSettled(
        ids.map((id) => request(`/uploads/${id}`, { method: "DELETE" })),
      );
    await refreshHistory().catch(() => {});
  } finally {
    state.uploading = false;
    selection();
  }
}
async function connected() {
  state.connected = true;
  $("pair-panel").hidden = true;
  notice();
  picker.loading();
  try {
    const caps = await request("/capabilities");
    const catalog = configureConverters(caps);
    state.capabilities = caps;
    picker.capabilities(caps, catalog);
    applyRoute({ restore: false });
    $("versions").textContent =
      `CapreConvert v${caps.application_version} · Local processing`;
    $("concurrency").querySelector('option[value="2"]').disabled =
      caps.limits.max_concurrency < 2;
    $("concurrency").value = String(caps.limits.default_concurrency);
  } catch (error) {
    state.capabilities = null;
    picker.failure(
      "Supported conversions could not load. Check the host connection and retry.",
    );
    if (error.status === 401) {
      state.connected = false;
      $("pair-panel").hidden = false;
    }
    controls();
    return;
  }
  await refreshHistory();
  await restoreWorkspaceJob();
}
async function initialize() {
  document.documentElement.dataset.theme =
    preference.get("localraw-theme") ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  $("theme-toggle").setAttribute(
    "aria-pressed",
    String(document.documentElement.dataset.theme === "dark"),
  );
  state.conversion =
    converterFor(preference.get("localraw-conversion"))?.id || "cr3_to_jpg";
  const parameters = new URLSearchParams(location.hash.slice(1));
  const credential = parameters.get("bootstrap");
  if (parameters.has("bootstrap")) {
    parameters.delete("bootstrap");
    const remaining = parameters.toString();
    window.history.replaceState(
      null,
      "",
      location.pathname + location.search + (remaining ? "#" + remaining : ""),
    );
  }
  applyRoute({ restore: false });
  try {
    let session;
    try {
      session = await request("/sessions");
    } catch (error) {
      if (error.status !== 401 || !credential) throw error;
      session = await request("/sessions", {
        method: "POST",
        body: JSON.stringify({ credential }),
      });
    }
    setCSRF(session.csrf_token);
    await connected();
  } catch (error) {
    $("pair-panel").hidden = false;
    picker.failure(
      error.status === 401
        ? "Pair this browser to load supported conversions."
        : "Could not connect to the host. Retry to load supported conversions.",
    );
    if (error.status !== 401) report(error);
    controls();
  }
}
$("file-input").addEventListener("change", (event) => {
  addFiles(event.target.files);
  event.target.value = "";
});
$("drop-zone").addEventListener("click", () => $("file-input").click());
for (const kind of ["dragenter", "dragover"])
  $("drop-zone").addEventListener(kind, (event) => {
    event.preventDefault();
    if (!state.uploading) $("drop-zone").classList.add("drag-over");
  });
for (const kind of ["dragleave", "drop"])
  $("drop-zone").addEventListener(kind, (event) => {
    event.preventDefault();
    $("drop-zone").classList.remove("drag-over");
  });
$("drop-zone").addEventListener("drop", (event) =>
  addFiles(event.dataTransfer.files),
);
document.addEventListener("dragover", (event) => event.preventDefault());
document.addEventListener("drop", (event) => event.preventDefault());
$("clear-files").addEventListener("click", () => {
  state.files = [];
  selection();
});
$("quality").addEventListener("input", () => {
  $("quality-value").value = $("quality").value;
});
$("metadata").addEventListener("change", () => {
  if (!$("metadata").checked) $("gps").checked = false;
  controls();
});
$("settings-form").addEventListener("submit", start);
$("pair-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("pair-error").textContent = "";
  try {
    const session = await request("/sessions", {
      method: "POST",
      body: JSON.stringify({ credential: $("pair-code").value.trim() }),
    });
    $("pair-code").value = "";
    setCSRF(session.csrf_token);
    await connected();
  } catch (error) {
    $("pair-error").textContent = error.message;
  }
});
$("theme-toggle").addEventListener("click", () => {
  const theme =
    document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  $("theme-toggle").setAttribute("aria-pressed", String(theme === "dark"));
  preference.set("localraw-theme", theme);
});
$("cancel-button").addEventListener("click", async () => {
  if (state.uploading) {
    state.abort?.abort();
    return;
  }
  if (!state.job) return;
  try {
    renderJob(
      await request(`/jobs/${state.job.id}/cancel`, { method: "POST" }),
    );
  } catch (error) {
    report(error);
  }
});
$("retry-button").addEventListener("click", async () => {
  if (!state.job) return;
  $("retry-button").disabled = true;
  try {
    const old = await request(`/jobs/${state.job.id}/summary`);
    const job = await createJob(old.retry_upload_ids, old.settings);
    await showJob(job.id);
    await refreshHistory();
  } catch (error) {
    report(error);
  } finally {
    $("retry-button").disabled = false;
  }
});
$("delete-job").addEventListener("click", async () => {
  if (!state.job) return;
  try {
    await request(`/jobs/${state.job.id}`, { method: "DELETE" });
    clearTimeout(state.timer);
    state.generation += 1;
    state.job = null;
    clearPreviews();
    $("job-panel").hidden = true;
    $("empty-results").hidden = false;
    await refreshHistory();
  } catch (error) {
    report(error);
  }
});
$("refresh-history").addEventListener("click", () =>
  refreshHistory().catch(report),
);
$("more-history").addEventListener("click", () => {
  state.historyLimit += 25;
  refreshHistory().catch(report);
});
document.addEventListener("visibilitychange", () => {
  if (
    !document.hidden &&
    state.job &&
    !terminal.has(state.job.state) &&
    !state.uploading
  ) {
    clearTimeout(state.timer);
    state.generation += 1;
    poll(state.job.id, state.generation);
  }
});
const picker = initializePicker(
  (id) => openConverter(id, { restore: true }),
  () => (state.connected ? connected() : initialize()),
);
initializePreviews(report);
initializeNavigation();
window.addEventListener("hashchange", () => applyRoute());
window.addEventListener("popstate", () => applyRoute());
initialize();
