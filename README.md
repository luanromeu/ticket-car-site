# ticket-car-site

Site institucional do TicketCar (`https://ticketcar.com.br`): landing page, Política de privacidade,
Termos de uso e a página de exclusão de conta (exigida pela Play Store).

HTML/CSS estático, sem framework e sem nada de terceiros (fontes, analytics). O `build.mjs` junta os
pedaços (`src/partials`), os ícones e os dados de `site.config.json` e gera `dist/`.

```bash
node build.mjs --draft   # revisar (dados vazios aparecem como [preencher: ...])
node build.mjs           # publicação: exige todos os dados de site.config.json
```

Hospedagem: bucket S3 privado + CloudFront (HTTPS) com os domínios `ticketcar.com.br` e `www.ticketcar.com.br`
(infraestrutura: `scripts/infra.py`, dados em `site-infra.json`, fora do git).

## Deploy (GitHub Actions, mesmo git flow dos outros repositórios)

```
feature/* ──PR──► develop ──(cria)──► release/X.Y.Z ──PR──► main ──► tag vX.Y.Z
                   CI: build          push: build           merge: publica em PRD
```

- **PR e develop:** o CI gera o site completo (falha se faltar dado em `site.config.json`) e confere os links internos.
- **release/X.Y.Z:** só build. O site não tem ambiente DEV: revise com `node build.mjs --draft` e abra `dist/`.
- **merge do PR release → main:** publica no bucket, limpa o cache do CloudFront e cria a tag `vX.Y.Z`.
  - Push direto na `main` não publica nada.
  - Versão com tag já existente não é publicada de novo.
- Credenciais via OIDC: papel `ticketcar-gh-site-prd`, aceito só na `main` deste repositório. É criado por `scripts/ci_role.py`.

O pedido de exclusão (`/excluir-conta/`) é enviado para `POST {API_URL}/v1/privacy/deletion-requests`
e aparece no admin em **Exclusões**. A API de PRD aceita as origens do site no CORS (`lightsail-setup`).

> Política de privacidade e Termos: textos-base escritos para o que o app faz hoje.
> Revise com um advogado antes do lançamento e sempre que o app passar a tratar dados novos.
