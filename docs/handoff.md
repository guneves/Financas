# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-23 (afternoon) · UI remodel: Cartões + kit `Menu`

Asked to "keep working on next-steps.md, keep the files I've deleted deleted, then commit". The
owner had deleted `docs/ui-remodel-audit.md` and `docs/ui-remodel-prompt.md`; they are committed as
deletions here, and the one reference in `next-steps.md` now points at git history
(`git show 36e0164:docs/ui-remodel-audit.md`). The next plan item was the Cartões rework.

### What was done

- **Kit `Menu`** (`frontend/src/components/ui.jsx`): a "⋯" row menu, `items: [{ label, icon,
  onSelect, tone }]`. Rendered through a portal with `position: fixed` measured from the button,
  because inside an `Expand` (overflow hidden while animating) or an `overflow-clip` panel an
  absolute popup is cut. Opens upward when it doesn't fit below; closes on outside pointer, Esc
  (focus back to the trigger), scroll or resize; arrow keys move between items; first item focused
  on open.
- **Cartões** (`pages/lancamentos/Cartoes.jsx`): one panel per card (two columns on `xl`), card
  meta line (closing/due day, autopay account) and its "Em aberto". Shown: overdue/closed invoices
  and the running one; later invoices fold into "Próximas N faturas · até MM/AAAA" with their total
  (per-card toggle, rows inside keep only "Fecha em …"). "Pagar" is rendered only on a closed
  invoice; the header "Pagar fatura" only when the nearest invoice is payable. Purchase delete is in
  the `Menu` ("Excluir compra" / "Excluir compra e parcelas"); `handleDeleteCCPurchase` itself is
  unchanged. The four `SummaryStat` cards and `walletSummary` are gone; the total open across
  cards moved into the page description. `ProjectionHeader` untouched.
- **Verified** with Playwright on a scratch DB (seed at scale 1, backend :5003, Vite :5176) at
  1280 px light/dark and 390 px: no horizontal overflow (the first run caught 96 px on the phone —
  the grid's implicit column grew to content; fixed with `grid-cols-[minmax(0,1fr)]`), menu opens
  visible and focused, Esc closes and restores focus. A purchase dated 01/09 on Itaú was added to
  get a closed, overdue invoice: it shows "Em atraso" + the only Pagar, and the header button.
  `vite build` clean; backend suite green (backend untouched). `backend/finance.db` not touched.
- **`finance-guard`** (found by `subagent_type` directly): no findings — closed-only payment still
  guarded in `handlePayInvoice` and server-side, delete confirmation unchanged, the two removed
  balance cards took their masked values with them.

### What was not done and why

- The Pay flow itself (sheet → confirm) was not clicked in this session; its handler and
  `PayInvoiceSheet` are unchanged from the last walk.
- `Menu` is adopted on Cartões only. Extrato's hover icons, Posição, Operações, Proventos,
  Recorrentes and Ajustes still use icon pairs; `Toast` not built. Listed in `next-steps.md`.
- On the phone an overdue invoice row wraps its badges ("Em atraso", "Próxima") to two lines beside
  the Pagar button — readable, left as is.
- Carried: open decisions G (Ctrl K) and I (attention items) were never answered; `BRAPI_TOKEN`
  still empty in `backend/.env`; `backend/backups/finance-pre-mock-20260922-205415.db` is safe to
  delete; receipts not in the backup zip; amount/account conditions on import rules not built;
  none of the remodel has been walked by the owner.

### Next session

- Owner: walk the remodel (Início, Extrato, Cartões) in both themes, on the phone too — the
  walk-through list at the top of `next-steps.md`.
- Next build item: Posição / Operações / Proventos (quote editing into a sheet, one summary panel,
  row actions into `Menu`), then adopt `Menu` on Extrato.

### Non-obvious things learned

- **A CSS grid with no explicit columns sizes its one track to content** — a truncated line inside
  a card still widens the page on the phone. Use `grid-cols-[minmax(0,1fr)]` (same trick as
  `Expand`).
- A bash heredoc with `'EOF'` holding JSX template literals failed in this harness ("unexpected
  EOF looking for matching `'`"); write the text to a scratchpad file and apply it with a small
  Python script instead.
- Getting a payable invoice on scratch data: the seed pays every past invoice, so POST
  `/api/cc-expenses/purchases` with a `purchase_date` before the last closing day.
- Carried: scratch server = set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`, `ATTACHMENTS_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`, `CORS_ORIGINS` before `import app`, sign up with
  `app.app.test_client()`, set `seed_three_years_mock.BACKEND_DIR` to the scratchpad and call
  `main()` with `sys.argv` patched; auth JSON into `localStorage['@financeMVP:auth']`, theme into
  `'@financeMVP:theme'`. On Windows check `netstat -ano` for ports held by other sessions first.
  Dark mode is a token swap — never `dark:` classes or a non-theme colour family.
