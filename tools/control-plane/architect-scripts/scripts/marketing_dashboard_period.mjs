export function monthsFromCohortByBrand(cohortByBrand = {}) {
  return Array.from(new Set(Object.keys(cohortByBrand).map((key) => String(key).split("|||")[0]).filter(Boolean))).sort();
}

export function formatPeriodLabel(months) {
  const cleanMonths = Array.from(new Set((months || []).filter(Boolean))).sort();
  if (!cleanMonths.length) return "";
  const fmt = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric", timeZone: "Europe/Moscow" });
  const toLabel = (month) => {
    const dt = new Date(`${month}-01T00:00:00+03:00`);
    const text = fmt.format(dt);
    return text.charAt(0).toUpperCase() + text.slice(1);
  };
  return `${toLabel(cleanMonths[0])} — ${toLabel(cleanMonths[cleanMonths.length - 1])}`;
}

export function latestMonth(months) {
  const cleanMonths = Array.from(new Set((months || []).filter(Boolean))).sort();
  return cleanMonths.at(-1) || "";
}
