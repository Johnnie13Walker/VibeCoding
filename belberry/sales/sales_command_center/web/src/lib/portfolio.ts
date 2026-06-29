import 'server-only';

import { readFile } from 'node:fs/promises';
import { createSign } from 'node:crypto';
import {
  parseClients,
  parseWdCases,
  mergeWdCases,
  parseCaseTab,
  applyCaseLinks,
  parseContragents,
  applyRevenue,
  aggregateNiches,
  aggregateServices,
  type PortfolioProject,
  type NicheCount,
} from './portfolio-shared';

const SHEET_ID = process.env.PORTFOLIO_SHEET_ID || '1TSEei_ncr3SQmiYT074Q17HOzmxxtrPV447j27N_BZw';
// Мастер-таблица «Продажи» — вкладка «Контрагенты» (ИНН + выручка ГИР БО).
const MASTER_SHEET_ID = process.env.PORTFOLIO_MASTER_SHEET_ID || '17SBisFgKrf3hRP_zjVPC2e4wMzlq8j8HDC2bvkyS74Y';
const SA_PATH = process.env.PORTFOLIO_SA_JSON || process.env.GOOGLE_SA_JSON || '/etc/scc/finance-sa.json';
const SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const TTL_MS = 60 * 60 * 1000; // снимок ETL обновляется раз в день → кэш 1 час

const b64url = (s: string | Buffer) =>
  Buffer.from(s).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');

interface SaCreds {
  client_email: string;
  private_key: string;
}
let credsCache: SaCreds | null = null;
async function loadCreds(): Promise<SaCreds> {
  if (credsCache) return credsCache;
  const raw = await readFile(SA_PATH, 'utf8');
  const j = JSON.parse(raw);
  if (!j.client_email || !j.private_key) throw new Error(`Portfolio SA json incomplete: ${SA_PATH}`);
  credsCache = { client_email: j.client_email, private_key: j.private_key };
  return credsCache;
}

let tokenCache: { token: string; exp: number } | null = null;
async function getToken(): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  if (tokenCache && tokenCache.exp - 120 > now) return tokenCache.token;
  const { client_email, private_key } = await loadCreds();
  const header = b64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
  const claim = b64url(JSON.stringify({ iss: client_email, scope: SCOPE, aud: TOKEN_URL, exp: now + 3600, iat: now }));
  const signer = createSign('RSA-SHA256');
  signer.update(`${header}.${claim}`);
  signer.end();
  const signature = signer.sign(private_key, 'base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  const jwt = `${header}.${claim}.${signature}`;
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion: jwt }),
  });
  const payload = await res.json();
  if (!res.ok || !payload.access_token) throw new Error(`Portfolio OAuth error: ${res.status}`);
  tokenCache = { token: String(payload.access_token), exp: now + 3600 };
  return tokenCache.token;
}

async function valuesGet(token: string, range: string, spreadsheetId: string = SHEET_ID): Promise<string[][]> {
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${encodeURIComponent(range)}?majorDimension=ROWS`;
  const res = await fetch(url, { headers: { authorization: `Bearer ${token}` } });
  const payload = await res.json();
  if (!res.ok) throw new Error(`Sheets API ${res.status}`);
  return (payload.values as string[][]) || [];
}

export interface PortfolioData {
  projects: PortfolioProject[];
  niches: NicheCount[];
  services: NicheCount[];
  totalProjects: number;
  withCaseCount: number;
  withRevenueCount: number;
  updatedAt: number;
}

let dataCache: PortfolioData | null = null;

/** Витрина портфолио из Google Sheet («Клиенты» + кейсы «Портфолио WD»). Кэш 1 час. */
export async function getPortfolio(): Promise<PortfolioData> {
  if (dataCache && Date.now() - dataCache.updatedAt < TTL_MS) return dataCache;
  const token = await getToken();
  const [clientsRows, wdRows, caseRows, contragentRows] = await Promise.all([
    valuesGet(token, "'Клиенты'!A13:Q1200"),
    valuesGet(token, "'Портфолио WD'!A1:Q1000"),
    valuesGet(token, "'Кейсы сайта'!A2:D2000").catch(() => [] as string[][]),
    valuesGet(token, "'Контрагенты'!A2:F1016", MASTER_SHEET_ID).catch(() => [] as string[][]),
  ]);
  const projects = applyRevenue(
    applyCaseLinks(
      mergeWdCases(parseClients(clientsRows), parseWdCases(wdRows)),
      parseCaseTab(caseRows),
    ),
    parseContragents(contragentRows),
  );
  dataCache = {
    projects,
    niches: aggregateNiches(projects),
    services: aggregateServices(projects),
    totalProjects: projects.length,
    withCaseCount: projects.filter((p) => p.caseUrl).length,
    withRevenueCount: projects.filter((p) => p.revenue && p.revenue > 0).length,
    updatedAt: Date.now(),
  };
  return dataCache;
}
