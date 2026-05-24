import { PDFParse } from "pdf-parse";
import { getLLMClient, LLM_MODEL } from "./llm";
import { getCollection } from "./database";
import { TextChunker } from "./chunker";

const SYSTEM_INSTRUCTION =
  "You are a document parser. Convert this raw text extracted from a PDF page into clean Markdown.\n" +
  "- Preserve tables using Markdown table syntax.\n" +
  "- Keep headers and document structure.\n" +
  "- Ignore page numbers and running headers/footers.\n" +
  "- Return ONLY the formatted Markdown. Do not include any intro/outro comments or markdown code fences.";

export class PDFProcessor {
  private chunker: TextChunker;

  constructor() {
    this.chunker = new TextChunker(256, 20);
  }

  async processAndIngest(
    pdfBuffer: Buffer,
    filename: string
  ): Promise<void> {
    console.log(`Processing ${filename}...`);

    const markdownContent = await this.parsePDF(pdfBuffer);

    if (!markdownContent) {
      throw new Error("Failed to extract content from PDF");
    }

    const chunks = this.chunker.splitText(markdownContent);
    console.log(`Split document into ${chunks.length} chunks.`);

    const collection = getCollection();
    const documents = chunks.map((chunkText, i) => ({
      content: chunkText,
      filename,
      chunk_index: i,
      $vectorize: chunkText,
    }));

    if (documents.length > 0) {
      await collection.insertMany(documents);
      console.log(
        `Successfully ingested ${documents.length} chunks from ${filename} into Astra DB`
      );
    }
  }

  private async parsePDF(pdfBuffer: Buffer): Promise<string> {
    const client = getLLMClient();
    const parser = new PDFParse({ data: pdfBuffer });
    const textResult = await parser.getText();
    await parser.destroy();

    const fullMarkdown: string[] = [];

    for (let i = 0; i < textResult.pages.length; i++) {
      const text = textResult.pages[i].text.trim();
      if (!text) continue;

      console.log(`Formatting page ${i + 1}/${textResult.pages.length}...`);

      const response = await client.chat.completions.create({
        model: LLM_MODEL,
        messages: [
          { role: "system", content: SYSTEM_INSTRUCTION },
          { role: "user", content: text },
        ],
        temperature: 0.1,
      });

      const pageMarkdown = response.choices[0].message.content;
      if (pageMarkdown) {
        fullMarkdown.push(pageMarkdown.trim());
      }
    }

    return fullMarkdown.join("\n\n");
  }
}
