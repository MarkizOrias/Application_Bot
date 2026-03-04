// src/utils/generateDocx.ts
// Converts a Markdown CV string into a .docx file using the `docx` package.
// Handles: H1/H2/H3 headings, bullet lists, inline bold (**text**), plain paragraphs.

import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  AlignmentType,
  BorderStyle,
  ISectionOptions,
} from "docx";
import * as fs from "fs";

export async function generateDocx(markdownText: string, outputPath: string): Promise<void> {
  const lines    = markdownText.split("\n");
  const children: Paragraph[] = [];

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("### ")) {
      children.push(new Paragraph({
        text:    trimmed.slice(4),
        heading: HeadingLevel.HEADING_3,
        spacing: { before: 120, after: 60 },
      }));

    } else if (trimmed.startsWith("## ")) {
      children.push(new Paragraph({
        text:    trimmed.slice(3),
        heading: HeadingLevel.HEADING_2,
        spacing: { before: 200, after: 80 },
        border: {
          bottom: { style: BorderStyle.SINGLE, size: 6, color: "444444" },
        },
      }));

    } else if (trimmed.startsWith("# ")) {
      children.push(new Paragraph({
        children: [new TextRun({ text: trimmed.slice(2), bold: true, size: 32 })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
      }));

    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      children.push(new Paragraph({
        children: parseInline(trimmed.slice(2)),
        bullet:   { level: 0 },
        spacing:  { before: 40, after: 40 },
      }));

    } else if (trimmed === "" || trimmed === "---") {
      children.push(new Paragraph({ text: "", spacing: { before: 60, after: 60 } }));

    } else {
      // Italics-only lines (e.g. _Location, Switzerland_)
      const isItalic = trimmed.startsWith("_") && trimmed.endsWith("_");
      if (isItalic) {
        children.push(new Paragraph({
          children: [new TextRun({ text: trimmed.slice(1, -1), italics: true, color: "555555" })],
          spacing:  { before: 40, after: 40 },
        }));
      } else {
        children.push(new Paragraph({
          children: parseInline(trimmed),
          spacing:  { before: 40, after: 40 },
        }));
      }
    }
  }

  const doc = new Document({
    sections: [{
      properties: {},
      children,
    } as ISectionOptions],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
}

// ── Inline parser: handles **bold** and plain text segments ──────────────────
function parseInline(text: string): TextRun[] {
  // Split on **...** markers
  const parts = text.split(/(\*\*[^*]+\*\*)/);

  return parts
    .filter((p) => p.length > 0)
    .map((part) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return new TextRun({ text: part.slice(2, -2), bold: true });
      }
      // Strip stray italic markers from within regular text
      const clean = part.replace(/^_(.+)_$/, "$1");
      return new TextRun({ text: clean });
    });
}
