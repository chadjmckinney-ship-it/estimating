/**
 * Parse every front-end script the way the BROWSER parses it.
 *
 *     node frontend/check.mjs
 *
 * `index.html` loads these with `type="module"`, and module parsing is not the
 * same as script parsing. `node --check app.js` checks the SCRIPT grammar,
 * where Annex B allows `<!--` as an HTML-like line comment. In a module it is
 * not a comment at all.
 *
 * That difference cost a day. An HTML comment inside a template literal
 * contained a name wrapped in backticks:
 *
 *     <!-- These boxes used to be filled from `estimate.margin_pct` — the ... -->
 *
 * A backtick inside a template literal ENDS IT. Parsed as a script the `<!--`
 * swallowed the line and `node --check` passed; parsed as a module the page
 * died on load with `SyntaxError: Unexpected identifier 'estimate'`, rendered
 * nothing but "Loading…", and looked for all the world like the API was down —
 * which is exactly how it was reported. The API was fine the whole time.
 *
 * Two rules follow, and this file enforces the first:
 *
 *   1. Check these files as MODULES. That is what runs.
 *   2. Nothing inside a template literal may contain a backtick, or a `${` that
 *      is not a real interpolation. Prose about the code goes in a JS comment
 *      outside the literal, where it cannot terminate anything.
 */

import { readdir, readFile, mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const JS_DIR = join(dirname(fileURLToPath(import.meta.url)), "assets", "js");

const scratch = await mkdtemp(join(tmpdir(), "fe-check-"));
let failed = 0;

for (const name of (await readdir(JS_DIR)).filter((n) => n.endsWith(".js")).sort()) {
  const src = await readFile(join(JS_DIR, name), "utf8");

  // Import it as a module rather than eval it: a real module parse, with no
  // chance of the script grammar being used by accident. Nothing executes —
  // these files only define functions and call render() behind a DOM guard —
  // but a parse error throws here with the line and column.
  const copy = join(scratch, name.replace(/\.js$/, ".mjs"));
  await writeFile(copy, src);
  try {
    await import(pathToFileURL(copy).href);
    console.log(`  ok    ${name}`);
  } catch (err) {
    if (err instanceof SyntaxError) {
      failed++;
      console.error(`  FAIL  ${name}: ${err.message}`);
      if (err.stack) console.error(err.stack.split("\n").slice(0, 4).join("\n"));
    } else {
      // Parsed fine; it just cannot RUN outside a browser (no `document`,
      // bare specifiers). That is expected and is not what this checks.
      console.log(`  ok    ${name}  (parsed; not runnable off-browser)`);
    }
  }
}

await rm(scratch, { recursive: true, force: true });

if (failed) {
  console.error(`\n${failed} file(s) will not parse as a module — the page will not load.`);
  process.exit(1);
}
console.log("\nAll front-end modules parse.");
