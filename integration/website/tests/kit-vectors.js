// Where the kit's golden vectors are: tests/fixtures/kit/ once W1 copied them into the website, else the kit's own
// integration/vectors/ (when these tests run inside the translator repository).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const inWebsite = fileURLToPath(new URL("./fixtures/kit/", import.meta.url));
const inKit = fileURLToPath(new URL("../../vectors/", import.meta.url));
export const VECTORS = existsSync(inWebsite) ? inWebsite : inKit;

export function vectors(folder) {
  const dir = `${VECTORS}${folder}/`;
  return readdirSync(dir).filter((f) => f.endsWith(".json")).sort().map((f) => JSON.parse(readFileSync(`${dir}${f}`, "utf8")));
}

export function vector(folder, name) {
  return JSON.parse(readFileSync(`${VECTORS}${folder}/${name}.json`, "utf8"));
}
