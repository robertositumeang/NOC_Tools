import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("./static/index.html", import.meta.url), "utf8");
const snippet = html.match(
  /<div id="gasSnippet"[^>]*>([\s\S]*?)<\/div>/,
)?.[1];

test("writes immediately below the last Site ID, not formula-filled rows", () => {
  assert.ok(snippet, "Apps Script snippet should be present in the Ticket Checker UI");

  const siteIds = Array.from({ length: 4194 }, () => [""]);
  siteIds[4179] = ["PB0852"];
  siteIds[4180] = ["#N/A"];
  const writes = new Map();
  const sheet = {
    getLastRow: () => 4195,
    getRange(row, column, rowCount) {
      if (rowCount !== undefined) {
        assert.equal(row, 2);
        assert.equal(column, 3);
        return { getDisplayValues: () => siteIds };
      }
      return {
        setValue(value) {
          writes.set(`${row}:${column}`, value);
        },
      };
    },
  };
  const context = {
    SpreadsheetApp: {
      getActiveSpreadsheet: () => ({
        getSheetByName: (name) => name === "Database TT" ? sheet : null,
      }),
    },
    ContentService: {
      MimeType: { JSON: "application/json" },
      createTextOutput(content) {
        return {
          content,
          setMimeType() {
            return this;
          },
        };
      },
    },
  };

  vm.runInNewContext(snippet, context);
  const response = context.doPost({
    postData: {
      contents: JSON.stringify({
        rows: [{ "Site ID": "PB0898", "Alarm ID": "A3-PB0898-1" }],
      }),
    },
  });

  assert.deepEqual(JSON.parse(response.content), {
    ok: true,
    written: 1,
    startRow: 4182,
  });
  assert.equal(writes.get("4182:3"), "PB0898");
  assert.equal(writes.get("4182:13"), "A3-PB0898-1");
  assert.equal(writes.has("4196:3"), false);
});
