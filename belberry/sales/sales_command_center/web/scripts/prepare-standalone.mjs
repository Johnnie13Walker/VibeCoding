import { cp, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const standaloneDir = path.join(root, '.next', 'standalone');

async function copyIfExists(from, to) {
  if (!existsSync(from)) {
    return;
  }

  await rm(to, { recursive: true, force: true });
  await mkdir(path.dirname(to), { recursive: true });
  await cp(from, to, { recursive: true });
}

await copyIfExists(path.join(root, '.next', 'static'), path.join(standaloneDir, '.next', 'static'));
await copyIfExists(path.join(root, 'public'), path.join(standaloneDir, 'public'));
