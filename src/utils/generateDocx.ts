// src/utils/generateDocx.ts
// Converts a Markdown CV string to a .docx file using the docx library.
import { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } from "docx";
import * as fs from "fs";

export async function generateDocx(markdown: string, outputPath: string): Promise<void> {
  const paragraphs: Paragraph[] = [];

  for (const line of markdown.split("\n")) {
    if (line.startsWith("# ")) {
      paragraphs.push(new Paragraph({
        text: line.slice(2).trim(),
        heading: HeadingLevel.HEADING_1,
        alignment: AlignmentType.CENTER,
      }));
    } else if (line.startsWith("## ")) {
      paragraphs.push(new Paragraph({
        text: line.slice(3).trim(),
        heading: HeadingLevel.HEADING_2,
      }));
    } else if (line.startsWith("### ")) {
      paragraphs.push(new Paragraph({
        text: line.slice(4).trim(),
        heading: HeadingLevel.HEADING_3,
      }));
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      paragraphs.push(new Paragraph({
        children: [new TextRun({ text: line.slice(2).trim() })],
        bullet: { level: 0 },
      }));
    } else if (line.trim() === "") {
      paragraphs.push(new Paragraph({ text: "" }));
    } else {
      // Handle **bold** inline
      const parts = line.split(/(\*\*[^*]+\*\*)/g);
      const runs = parts.map((part) =>
        part.startsWith("**") && part.endsWith("**")
          ? new TextRun({ text: part.slice(2, -2), bold: true })
          : new TextRun({ text: part }),
      );
      paragraphs.push(new Paragraph({ children: runs }));
    }
  }

  const doc = new Document({ sections: [{ properties: {}, children: paragraphs }] });
  fs.writeFileSync(outputPath, await Packer.toBuffer(doc));
}
