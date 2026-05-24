import { DataAPIClient, Db } from "@datastax/astra-db-ts";

let client: DataAPIClient | null = null;
let db: Db | null = null;

function getClient(): DataAPIClient {
  if (!client) {
    const token = process.env.ASTRA_DB_APPLICATION_TOKEN;
    if (!token) {
      throw new Error("Missing ASTRA_DB_APPLICATION_TOKEN");
    }
    client = new DataAPIClient(token);
  }
  return client;
}

function getDb(): Db {
  if (!db) {
    const endpoint = process.env.ASTRA_DB_API_ENDPOINT;
    if (!endpoint) {
      throw new Error("Missing ASTRA_DB_API_ENDPOINT");
    }
    db = getClient().db(endpoint);
  }
  return db;
}

export function getCollection(collectionName = "campus_saathi") {
  return getDb().collection(collectionName);
}
