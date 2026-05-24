import { chat, chatJSON } from "./llm";
import { getCollection } from "./database";
import { TranslationResult } from "@/types";

const SYSTEM_INSTR_TRANS = `You are a translator.
1. Detect the language of the query.
2. Translate it to English.
3. Return JSON: {"translation": "...", "detected_language": "..."}`;

function getSystemInstrGen(targetLang: string): string {
  return `You are a helpful assistant for a college.
Answer the user's question based strictly on the provided context.
Respond in the user's detected language: ${targetLang}.
If the info is missing, say so politely in ${targetLang}.`;
}

export async function processQuery(userQuery: string): Promise<string> {
  try {
    let englishQuery = userQuery;
    let userLang = "English";

    try {
      const translationRaw = await chatJSON(SYSTEM_INSTR_TRANS, userQuery);
      const cleaned = translationRaw
        .replace(/```json/g, "")
        .replace(/```/g, "")
        .trim();
      const result: TranslationResult = JSON.parse(cleaned);

      if (result.translation) {
        englishQuery = result.translation;
        userLang = result.detected_language || "English";
      }
    } catch {
      englishQuery = userQuery;
      userLang = "English";
    }

    console.log(
      `Debug: Original: ${userQuery}, Translated: ${englishQuery}, Lang: ${userLang}`
    );

    const safeQuery = englishQuery.slice(0, 1000);
    const contextText = await retrieveContext(safeQuery);

    if (!contextText) {
      return "I couldn't find any relevant documents to answer your question.";
    }

    const userContent = `Context:\n${contextText}\n\nUser Question: ${userQuery}\n\nAnswer:`;
    const finalAnswer = await chat(
      getSystemInstrGen(userLang),
      userContent,
      0.1
    );

    if (!finalAnswer) {
      return "Sorry, the AI model is currently overloaded. Please try again later.";
    }

    return finalAnswer;
  } catch (err) {
    console.error("CRITICAL ERROR in QueryEngine:", err);
    return "Sorry, something went wrong while processing your query. Please try again later.";
  }
}

async function retrieveContext(query: string): Promise<string> {
  try {
    const collection = getCollection();
    const results = collection.find(
      {},
      {
        sort: { $vectorize: query },
        limit: 5,
        projection: { content: 1 },
      }
    );

    const documents: string[] = [];
    for await (const doc of results) {
      if (doc.content) {
        documents.push(doc.content);
      }
    }

    return documents.join("\n\n");
  } catch (err) {
    console.error("Search error in Astra DB:", err);
    return "";
  }
}
