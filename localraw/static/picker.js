// Pending homepage choices never write workspace, uploads or job settings.
const $ = (id) => document.getElementById(id);
const validID = /^[a-z][a-z0-9_]{0,63}$/;
export function initializePicker(open, retry) {
  const input = $("picker-input"),
    output = $("picker-output");
  let formats = new Map(),
    entries = [],
    selectedInput = "",
    selectedOutput = "";
  let ready = false;
  const placeholder = (text) => new Option(text, "");
  function grouped(select, ids, hint) {
    select.replaceChildren(placeholder(hint));
    for (const [category, label] of [
      ["images", "Images"],
      ["documents", "Documents"],
    ]) {
      const group = document.createElement("optgroup");
      group.label = label;
      for (const format of formats.values()) {
        if (format.category !== category || !ids.has(format.id)) continue;
        const option = new Option(format.label, format.id);
        group.append(option);
      }
      if (group.children.length) select.append(group);
    }
  }
  function matches() {
    return entries.filter(
      (entry) =>
        entry.source_format === selectedInput &&
        entry.target_format === selectedOutput,
    );
  }
  function status() {
    const candidates = matches();
    let message = !selectedInput
      ? "Choose an input file type."
      : !output.options.length || output.options.length === 1
        ? "No supported conversion is available for this input."
        : !selectedOutput
          ? "Choose an output file type."
          : "Ready to open this converter.";
    if (selectedInput && selectedInput === selectedOutput)
      message = "Optimize size, quality or dimensions.";
    if (candidates.length > 1)
      message =
        "Multiple engines advertise this pair. Use a specific converter link; this picker cannot choose an engine.";
    else if (candidates.length === 1 && candidates[0].available !== true)
      message =
        (selectedInput === selectedOutput
          ? "Optimize size, quality or dimensions. "
          : "This conversion needs setup. ") +
        (candidates[0].setup_message ||
          "This converter needs setup on the host computer.");
    $("open-converter").disabled =
      !ready || candidates.length !== 1 || candidates[0].available !== true;
    $("picker-status").textContent = message;
  }
  function outputs(preferred = selectedOutput) {
    const ids = new Set(
      entries
        .filter((entry) => entry.source_format === selectedInput)
        .map((entry) => entry.target_format),
    );
    grouped(output, ids, "Choose output type");
    selectedOutput = ids.has(preferred)
      ? preferred
      : ids.size === 1
        ? [...ids][0]
        : "";
    output.value = selectedOutput;
    output.disabled = !ready || !selectedInput || !ids.size;
    status();
  }
  input.addEventListener("change", () => {
    selectedInput = input.value;
    outputs();
  });
  output.addEventListener("change", () => {
    selectedOutput = output.value;
    status();
  });
  $("conversion-picker").addEventListener("submit", (event) => {
    event.preventDefault();
    const candidates = matches();
    if (ready && candidates.length === 1 && candidates[0].available === true)
      open(candidates[0].id);
  });
  $("picker-retry").addEventListener("click", async () => {
    await retry();
    (ready ? input : $("picker-retry")).focus();
  });
  return {
    loading() {
      ready = false;
      input.disabled = output.disabled = $("open-converter").disabled = true;
      $("conversion-picker").setAttribute("aria-busy", "true");
      $("picker-status").textContent = "Loading supported conversions…";
      $("picker-retry").hidden = true;
    },
    failure(message) {
      ready = false;
      input.replaceChildren(placeholder("Choose input type"));
      output.replaceChildren(placeholder("Choose output type"));
      input.disabled = output.disabled = $("open-converter").disabled = true;
      $("conversion-picker").setAttribute("aria-busy", "false");
      $("picker-status").textContent = message;
      $("picker-retry").hidden = false;
    },
    capabilities(capabilities, catalog) {
      formats = catalog;
      entries = (capabilities.conversions || []).filter(
        (entry) =>
          validID.test(entry.id) &&
          formats.has(entry.source_format) &&
          formats.has(entry.target_format),
      );
      ready = true;
      $("conversion-picker").setAttribute("aria-busy", "false");
      $("picker-retry").hidden = true;
      const ids = new Set(entries.map((entry) => entry.source_format));
      grouped(input, ids, "Choose input type");
      if (!ids.has(selectedInput)) selectedInput = "";
      input.value = selectedInput;
      input.disabled = !ids.size;
      outputs();
      if (!entries.length)
        $("picker-status").textContent =
          "No supported conversions are advertised by this host.";
    },
    synchronize(id) {
      const entry = entries.find((entry) => entry.id === id);
      if (!ready || !entry) return;
      selectedInput = entry.source_format;
      input.value = selectedInput;
      outputs(entry.target_format);
    },
  };
}
