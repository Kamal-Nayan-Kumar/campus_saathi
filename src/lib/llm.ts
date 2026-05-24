import OpenAI from "openai";

let client: OpenAI | null = null;

export function getLLMClient(): OpenAI {
  if (!client) {
    const apiKey =
      process.env.OPENCODE_API_KEY || process.env.OPENCODE_GO_API_KEY;
    if (!apiKey) {
      throw new Error(
        "OPENCODE_API_KEY (or OPENCODE_GO_API_KEY) not found in environment variables"
      );
    }

    client = new OpenAI({
      apiKey,
      baseURL: "https://opencode.ai/zen/go/v1",
    });
  }
  return client;
}

export const LLM_MODEL = "deepseek-v4-flash";

export async function chat(
  systemPrompt: string,
  userContent: string,
  temperature = 0.1
): Promise<string> {
  const c = getLLMClient();
  const response = await c.chat.completions.create({
    model: LLM_MODEL,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userContent },
    ],
    temperature,
  });
  return response.choices[0].message.content || "";
}

export async function chatJSON(
  systemPrompt: string,
  userContent: string
): Promise<string> {
  const c = getLLMClient();
  const response = await c.chat.completions.create({
    model: LLM_MODEL,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userContent },
    ],
    temperature: 0.1,
    response_format: { type: "json_object" },
  });
  return response.choices[0].message.content || "";
}
