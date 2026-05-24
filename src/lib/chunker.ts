export class TextChunker {
  private chunkSize: number;
  private chunkOverlap: number;

  constructor(chunkSize = 256, chunkOverlap = 20) {
    this.chunkSize = chunkSize;
    this.chunkOverlap = chunkOverlap;
  }

  splitText(text: string): string[] {
    const sentences = text.match(/[^.!?\n]+[.!?\n]*/g) || [text];
    const chunks: string[] = [];

    let currentChunk: string[] = [];
    let currentWordCount = 0;
    const overlapSentenceCount = Math.ceil(this.chunkOverlap / 10);

    for (const sentence of sentences) {
      const trimmed = sentence.trim();
      if (!trimmed) continue;

      const words = trimmed.split(/\s+/).length;

      if (currentWordCount + words > this.chunkSize && currentChunk.length > 0) {
        chunks.push(currentChunk.join(" "));
        const overlapStart = Math.max(0, currentChunk.length - overlapSentenceCount);
        currentChunk = currentChunk.slice(overlapStart);
        currentWordCount = currentChunk.reduce(
          (sum, s) => sum + s.split(/\s+/).length,
          0
        );
      }

      currentChunk.push(trimmed);
      currentWordCount += words;
    }

    if (currentChunk.length > 0) {
      chunks.push(currentChunk.join(" "));
    }

    return chunks.length > 0 ? chunks : [text];
  }
}
