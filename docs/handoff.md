# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-16 · Mobile Phase 2: phone-width layout, on the PC

The previous session (2026-10-13) checked the Android plan against the code and built Phase 3
(idempotent creation), the PC half of Phase 1 (Flask serves the build) and Phase 4 (the offline
outbox). This one built Phase 2 on the PC. The docs were read directly (no `session-scout`), and
`finance-guard` audited the change: 0 findings, found directly by `subagent_type`.

### What was done
- **Walked every banking screen at 360 and 412 px** in Playwright phone emulation, against a
  scratch backend seeded with `seed_three_years_mock.py --scale 1`. A script measured sideways
  overflow and every control under 40 px, and took screenshots. **No screen scrolled sideways.**
  The real problems:
  - the section tabs overflowed at 360 px (Metas and Importar were cut off);
  - on Cartões, an invoice label had ~40 px left and its badges were drawn over the amount;
  - `Button` sm/md, `SegmentedControl` and `Tabs` were 36–40 px tall;
  - in "+ Novo" the type picker took three rows, so the form plus Salvar didn't fit on screen.
- **Fixes**, all frontend; details in `mobile-docs/steps-to-production.md` → Phase 2:
  - tabs drop the icon below `sm`;
  - on phones the Cartões amount sits under the label;
  - controls are 44 px below `lg`, the `IconButton` rule, now in `ui.jsx` itself;
  - Início's panel-title links get a bigger hit area;
  - "+ Novo" has a one-row type picker (Despesa, Receita, Transferir, Cartão). It opens on a large
    amount field that is focused for every type, in typing order (valor, categoria, descrição),
    with data and conta side by side at the end;
  - for the keyboard: the sheet height is `92dvh` and the viewport meta has
    `interactive-widget=resizes-content`;
  - `inputMode` is set on the numeric fields.
- **Checked by script:**
  - the despesa form plus Salvar fits in 360×780;
  - with the viewport shrunk to 360×420 (what the keyboard leaves), the amount field and Salvar
    are both visible;
  - a despesa typed and saved through the phone-emulated sheet arrives, with its toast;
  - the desktop modal and Cartões look the same as before at 1400 px.
  - `vite build` is clean and the frontend rule tests pass (16). No backend file changed, so the
    backend suite was not run.

### What was not done and why
- **The "done when" (one-handed despesa in under ten seconds) needs the real phone**, so it waits
  on Phase 1's phone half (Tailscale). The comma question goes with it: does the owner's decimal
  keyboard type a separator that `type="number"` accepts? Chrome accepts the locale's separator,
  but keyboards differ. If it fails, the fix is a `type="text"` amount field with our own parsing,
  plus a test for that parsing.
- **Investment screens** were only checked to be readable (as the plan says). Operações still has
  a 32 px "Ocultar" button. Posição's sell button passes `lg:h-8`, which now competes with the
  default `lg:h-9`: harmless, and desktop only.
- The initial balance in Ajustes › Contas got no `inputMode`: it can be negative, and Android's
  decimal keyboard has no minus key. Rule priority was left alone for the same reason.
- Dark mode was not walked again: the change only resizes things and adds no colours.

### Waiting on the owner (carried, unchanged)
- For Phase 1: Tailscale on PC and phone, MagicDNS and HTTPS certificates enabled in the tailnet
  (this publishes the PC's machine name in the public certificate log), and the `.env` values
  (`JWT_SECRET`, `JWT_EXP_DAYS=180`, `CORS_ORIGINS`; see `.env.example`).
- For Phase 5: Android Studio with the SDK, the phone with USB debugging, a place outside the
  repository for the release keystore.
- For Phase 6: at least five real notification texts per bank app (Itaú, BTG, Banco do Brasil),
  copied exactly. Cover credit, debit, Pix sent and received, an estorno and a declined purchase.
  Also say which apps are installed (Itaú Cartões? Ourocard?). The texts stay on this machine.
- For Phase 8: one real statement file per bank, for the dedup test.
- An eye on Phase 4's screens on the PC ("Pendentes", pending rows, estimate labels).
- Still open in `docs/next-steps.md`: the walk-through on the fresh database, the "no mês" pill,
  `NET_WORTH` goals, the unguarded movement delete, the multi-currency removal, three low test
  pins, the brapi 1-ticker limit.

### Next session
Nothing more on the mobile plan can be done without the owner: every remaining phase needs the
phone, Tailscale, Android Studio or real notification texts. Pick from the other open items in
`docs/next-steps.md` (for example the unguarded movement delete), or do Phase 1's phone half and
the Phase 2 phone test once Tailscale is set up.

### Learned
- **Phone walk tooling** lives in this session's scratchpad (`app/serve.py`, `walk.cjs`,
  `slices.cjs`, `keyboard.cjs`). It is gone next session, so here is the recipe:
  - `serve.py` sets the env (`DATABASE_PATH` and friends) before `import app`, then signs up with
    `{"username", "email", "password"}`. `username` is required; signup returns 400 without it.
  - It then runs the seed through `importlib` with `seed.BACKEND_DIR` pointed at the scratchpad,
    so the seed's pre-wipe backup lands there.
  - It writes `auth.json` with the minted token and serves on :5003. Vite runs on :5176.
- **A full-page phone screenshot is unreadable** once scaled down (Extrato is ~20 000 px tall).
  Take viewport-sized slices at scroll offsets instead.
- **Simulating the keyboard:** `interactive-widget=resizes-content` makes the layout viewport
  shrink with the keyboard. So a `setViewportSize({height: 420})` after the sheet opens is a fair
  stand-in.
- **When classes conflict, Tailwind decides by its stylesheet order, not by the order in
  `className`.** A `className="h-11"` on a `size="sm"` Button (then `h-9`) came out 36 px on
  Cartões. Put responsive sizes in the component's own size table, not in per-call overrides.
- The Playwright cache now also has `chromium_headless_shell-1248`. Pass its `executablePath`.
- Carried: `core.autocrlf` is true (open Python patch files with `encoding="utf-8"`); a `"""`
  heredoc fails in the Bash tool (write scripts with the Write tool); Chrome refuses ports
  5060/5061; `tmp_path` fails here (use `tempfile.mkdtemp(dir=...)`); run
  `python -m pytest` plain (`-q` is in `pytest.ini`); `node --test` wants the glob, not a
  directory; Git Bash rewrites arguments starting with `/` unless `MSYS_NO_PATHCONV=1`; open
  `finance.db` read-only with `file:<path>?mode=ro`.
