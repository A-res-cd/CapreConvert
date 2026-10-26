// Public workspace descriptions; server capabilities decide host availability.
export const converters = {
  docx_to_pdf: {
    id: "docx_to_pdf",
    label: "DOCX → PDF",
    source: "DOCX",
    output: "PDF",
    description: "Turn Word documents into PDFs, privately on your computer.",
    completed: "Your PDFs are ready.",
    footnote: "Local document conversion · originals untouched",
    limitations: [],
  },
  pdf_to_docx: {
    id: "pdf_to_docx",
    label: "PDF → DOCX",
    source: "PDF",
    output: "DOCX",
    description: "Extract selectable PDF text into an editable Word document.",
    completed: "Your Word documents are ready.",
    footnote: "Text extraction only · no OCR or original page layout",
    limitations: [
      "Text only. No OCR; images and original layouts are not preserved.",
    ],
  },
  cr3_to_jpg: {
    id: "cr3_to_jpg",
    label: "CR3 → JPG",
    source: "CR3",
    output: "JPEG",
    description:
      "Develop Canon CR3 photos at full resolution, individually or in a ZIP.",
    completed: "Your JPEGs are ready.",
    footnote: "Full visible size · sRGB · 4:4:4 color",
    limitations: [],
  },
  cr3_to_png: {
    id: "cr3_to_png",
    label: "CR3 → PNG",
    source: "CR3",
    output: "PNG",
    description:
      "Develop Canon CR3 photos into full-resolution, lossless PNG files.",
    completed: "Your PNGs are ready.",
    footnote: "Full visible size · sRGB · lossless PNG encoding",
    limitations: [],
  },
};

const presentation = { ...converters };
let advertised = null;
const validID = /^[a-z][a-z0-9_]{0,63}$/;
export function configureConverters(capabilities) {
  const formats = new Map(
    (capabilities.formats || [])
      .filter(
        (format) =>
          validID.test(format.id) &&
          ["images", "documents"].includes(format.category),
      )
      .map((format) => [format.id, format]),
  );
  advertised = new Set();
  for (const entry of capabilities.conversions || []) {
    const source = formats.get(entry.source_format);
    const target = formats.get(entry.target_format);
    if (!validID.test(entry.id) || !source || !target) continue;
    advertised.add(entry.id);
    const output = target.short_label || target.label;
    converters[entry.id] = {
      description: "Convert files locally with the settings below.",
      completed: `Your ${output.toUpperCase()} images are ready.`,
      footnote:
        "sRGB normalized pixels. Lossy recompression cannot restore detail.",
      source: source.short_label || source.label,
      output: output.toUpperCase(),
      ...presentation[entry.id],
      ...entry,
    };
  }
  return formats;
}
export function supportedConversion(id) {
  return (
    typeof id === "string" && validID.test(id) && Boolean(advertised?.has(id))
  );
}
export function converterFor(kind) {
  if (kind == null || kind === "") return converters.cr3_to_jpg;
  return Object.hasOwn(converters, kind) ? converters[kind] : null;
}

export function jobConverter(job) {
  return converterFor(job?.settings?.conversion);
}

export function imageExportType(job) {
  return jobConverter(job).output_extension.slice(1).toUpperCase();
}
