// Gera o site em dist/ a partir de src/: inclui os pedaços (partials), os ícones e os dados de site.config.json.
//   node build.mjs            → exige todos os dados preenchidos (publicação)
//   node build.mjs --draft    → permite dados vazios (aparecem como [preencher: ...]) para revisar
import { cpSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const src = join(root, 'src');
const out = join(root, 'dist');
const draft = process.argv.includes('--draft');
const cfg = JSON.parse(readFileSync(join(root, 'site.config.json'), 'utf8'));

const OPTIONAL = ['DOCUMENTO', 'CIDADE_UF', 'VIGENCIA']; // CNPJ e cidade, se houver (não publicamos CPF)
const missing = Object.entries(cfg).filter(([k, v]) => !k.startsWith('_') && !OPTIONAL.includes(k) && String(v).trim() === '').map(([k]) => k);
const doc = String(cfg.DOCUMENTO ?? '').trim();
cfg.DOC_PAREN = doc ? ` (${doc})` : '';
cfg.DOC_SEP = doc ? ` · ${doc}` : '';
const city = String(cfg.CIDADE_UF ?? '').trim();
cfg.CIDADE_FRASE = city ? `, com sede em ${city}` : '';
cfg.CIDADE_SEP = city ? ` · ${city}` : '';
if (!String(cfg.VIGENCIA ?? '').trim()) cfg.VIGENCIA = new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo' }).format(new Date());
if (missing.length && !draft) {
  console.error(`Preencha em site.config.json: ${missing.join(', ')} (ou rode com --draft para revisar).`);
  process.exit(1);
}

const icons = {
  check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  qr: '<rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/><path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/>',
  camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
  doc: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="m9 15 2 2 4-4"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  store: '<path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4"/><path d="M2 7h20"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  trend: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  car: '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
  play: '<path d="M6 3.8v16.4a1 1 0 0 0 1.5.86l13.1-8.2a1 1 0 0 0 0-1.72L7.5 2.94A1 1 0 0 0 6 3.8z" fill="currentColor" stroke="none"/>',
  apple: '<path d="M16.4 12.6c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.8-1.4-.1-2.8.9-3.5.9-.7 0-1.8-.8-3-.8-1.5 0-3 .9-3.8 2.3-1.6 2.8-.4 7 1.2 9.3.8 1.1 1.7 2.4 2.9 2.3 1.2 0 1.6-.7 3-.7s1.8.7 3 .7c1.3 0 2.1-1.1 2.8-2.3.9-1.3 1.3-2.6 1.3-2.6s-2.5-1-2.5-3.8zM14.1 5.8c.6-.8 1.1-1.8 1-2.8-.9 0-2 .6-2.7 1.4-.6.7-1.1 1.7-1 2.7 1 .1 2-.5 2.7-1.3z" fill="currentColor" stroke="none"/>',
  arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
const car = readFileSync(join(src, 'assets', 'car.svg'), 'utf8').trim();
const partial = (name) => readFileSync(join(src, 'partials', `${name}.html`), 'utf8');
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function render(text, depth = 0) {
  if (depth > 3) throw new Error('include recursivo');
  return text
    .replace(/<!--#include (\w[\w-]*)-->/g, (_, n) => render(partial(n), depth + 1))
    .replace(/<!--#icon (\w+)-->/g, (_, n) => {
      if (!icons[n]) throw new Error(`ícone desconhecido: ${n}`);
      return icon(n);
    })
    .replace(/<!--#car-->/g, car)
    .replace(/\{\{(\w+)\}\}/g, (_, k) => {
      if (k === 'YEAR') return String(new Date().getFullYear());
      if (!(k in cfg)) throw new Error(`dado desconhecido: {{${k}}}`);
      return String(cfg[k]).trim() || OPTIONAL.includes(k) || /^(DOC|CIDADE)_/.test(k) ? esc(cfg[k]) : `<mark>[preencher: ${k}]</mark>`;
    });
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
let pages = 0;
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const rel = relative(src, p);
    if (rel === 'partials') continue;
    if (statSync(p).isDirectory()) {
      mkdirSync(join(out, rel), { recursive: true });
      walk(p);
    } else if (extname(name) === '.html') {
      writeFileSync(join(out, rel), render(readFileSync(p, 'utf8')));
      pages++;
    } else {
      cpSync(p, join(out, rel));
    }
  }
})(src);
console.log(`site gerado em dist/ (${pages} páginas)${missing.length ? ` — RASCUNHO, faltam: ${missing.join(', ')}` : ''}`);
