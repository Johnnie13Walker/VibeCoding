import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";

export async function readJsonFile(filePath, fallbackValue) {
  try {
    const raw = await readFile(filePath, "utf-8");
    return JSON.parse(raw);
  } catch {
    return fallbackValue;
  }
}

export async function writeJsonFile(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}
