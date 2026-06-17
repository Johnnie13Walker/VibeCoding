import { getUsersWithCache } from "../storage/usersCache.js";

const NAME_SYNONYMS = {
  петя: "петр",
  петр: "петр",
  пётр: "петр",
  саша: "александр",
  саня: "александр",
  александр: "александр",
  дима: "дмитрий",
  дмитрий: "дмитрий",
  женя: "евгений",
  евгений: "евгений",
  женька: "евгений",
  миша: "михаил",
  михаил: "михаил",
  коля: "николай",
  николай: "николай",
  антон: "антон",
  сергей: "сергей",
  сережа: "сергей",
  серёжа: "сергей",
  максим: "максим",
  макс: "максим",
  андрей: "андрей",
  андрюха: "андрей",
  артем: "артем",
  артём: "артем",
  илья: "илья",
  костя: "константин",
  константин: "константин",
  валера: "валерий",
  валерий: "валерий",
  юра: "юрий",
  юрий: "юрий",
  оля: "ольга",
  ольга: "ольга",
  лена: "елена",
  елена: "елена",
  катя: "екатерина",
  екатерина: "екатерина",
  таня: "татьяна",
  татьяна: "татьяна",
  настя: "анастасия",
  анастасия: "анастасия",
  наташа: "наталья",
  наталья: "наталья",
  ира: "ирина",
  ирина: "ирина",
  юля: "юлия",
  юлия: "юлия",
  света: "светлана",
  светлана: "светлана",
  маша: "мария",
  мария: "мария"
};

function normalize(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^a-zа-я0-9\s]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function mapSynonyms(token) {
  if (NAME_SYNONYMS[token]) return NAME_SYNONYMS[token];
  const stems = [
    token.replace(/(ом|ем|ой|ей|ам|ям|ах|ях)$/, ""),
    token.replace(/(а|я|у|ю|е|и|ы)$/, "")
  ];
  for (const stem of stems) {
    if (NAME_SYNONYMS[stem]) return NAME_SYNONYMS[stem];
  }
  return token;
}

function tokens(text) {
  return normalize(text)
    .split(" ")
    .filter(Boolean)
    .map(mapSynonyms);
}

function buildAliases(user) {
  const name = normalize(user.name || "");
  const last = normalize(user.lastName || "");
  const second = normalize(user.secondName || "");
  const full = normalize(user.fullName || "");
  const variants = new Set([
    full,
    [name, last].filter(Boolean).join(" "),
    [last, name].filter(Boolean).join(" "),
    [last, name, second].filter(Boolean).join(" "),
    [name, last, second].filter(Boolean).join(" "),
    normalize(user.email || "")
  ]);

  return [...variants].filter(Boolean);
}

function scoreCandidate(queryNorm, queryTokens, user) {
  const aliases = buildAliases(user);
  const idStr = String(user.id);
  if (queryNorm === idStr) return 100;

  let score = 0;
  for (const alias of aliases) {
    if (alias === queryNorm) score = Math.max(score, 95);
    else if (alias.startsWith(queryNorm)) score = Math.max(score, 80);
    else if (alias.includes(queryNorm)) score = Math.max(score, 70);

    const aliasTokens = alias.split(" ").filter(Boolean);
    const common = queryTokens.filter((qt) => aliasTokens.includes(qt)).length;
    if (common > 0) {
      const tokenScore = Math.round((common / Math.max(queryTokens.length, 1)) * 60);
      score = Math.max(score, tokenScore);
    }
  }

  return score;
}

export function createPeopleResolver({ provider, cacheFile, ttlMs, logger = console }) {
  return {
    async resolvePerson(query) {
      const queryNorm = normalize(query);
      if (!queryNorm) return { type: "none" };

      const usersResult = await getUsersWithCache({
        cacheFile,
        ttlMs,
        provider,
        logger
      });

      if (usersResult.status === "not_configured") {
        return { type: "not_configured" };
      }
      if (usersResult.status !== "ok") {
        return { type: "none" };
      }

      const queryTokens = tokens(queryNorm);
      const scored = usersResult.users
        .map((user) => ({ user, score: scoreCandidate(queryNorm, queryTokens, user) }))
        .filter((row) => row.score >= 45)
        .sort((a, b) => b.score - a.score);

      if (scored.length === 0) {
        return { type: "none" };
      }

      const top = scored[0];
      const second = scored[1];
      if (!second || top.score - second.score >= 15 || top.score >= 95) {
        return { type: "single", user: top.user };
      }

      const candidates = scored
        .filter((row) => top.score - row.score <= 10)
        .slice(0, 7)
        .map((row) => row.user);

      return { type: "multiple", candidates };
    }
  };
}
