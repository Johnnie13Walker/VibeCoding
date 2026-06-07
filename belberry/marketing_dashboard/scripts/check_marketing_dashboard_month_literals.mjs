import { readFile } from "node:fs/promises";

const ROOT = new URL(".", import.meta.url);
const FILES = [
  "build_ceo_dashboard.mjs",
  "build_cohort_filter_sheet.mjs",
  "build_event_filter_sheet.mjs",
  "build_operational_sheets.mjs",
  "build_source_dynamics_sheet.mjs",
  "build_spam_source_sheet.mjs",
  "build_support_sheets.mjs",
  "beautify_dashboard_tabs.mjs",
  "send_marketing_dashboard_telegram_status.py",
  "verify_marketing_dashboard_live.mjs",
];

const FORBIDDEN = [
  { pattern: /Апрель 2026|Май 2026|Июнь 2026|Июль 2026|Август 2026|Сентябрь 2026|Октябрь 2026|Ноябрь 2026|Декабрь 2026/g, reason: "период должен считаться из JSON, а не быть прошит текстом" },
  { pattern: /2026-0[4-9]|2026-1[0-2]/g, reason: "месяц селектора должен браться из данных, а не быть прошит литералом" },
];

const findings = [];
for (const file of FILES) {
  const text = await readFile(new URL(file, ROOT), "utf8");
  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    for (const rule of FORBIDDEN) {
      rule.pattern.lastIndex = 0;
      const matches = [...line.matchAll(rule.pattern)];
      for (const match of matches) {
        findings.push({
          file,
          line: index + 1,
          literal: match[0],
          reason: rule.reason,
        });
      }
    }
  });
}

if (findings.length) {
  console.error(JSON.stringify({ status: "FAIL", findings }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ status: "OK", checkedFiles: FILES.length }, null, 2));
