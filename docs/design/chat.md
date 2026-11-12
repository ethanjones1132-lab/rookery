# Rookery chat: native, with an upgrade

Owner: Claude (design lane). Status: building, Nov 8 2026.
Requirement (Ethan): the chat happens inside the Rookery page by default. "Dock beside chat" is an option, not the default.
Ethan's note: most Hermes complaints are about the UI. Rookery's chat must look native, and be better.

## 1. Native: what we reuse, pixel for pixel

Hermes's own Bot Mode rooms (`apps/desktop/src/plugins/hermes-bots/group-room-ui.tsx`) are a plugin-built chat that matches the main thread. Rookery builds on the same parts, all exported from `@hermes/plugin-sdk`:

| Part | SDK export | Fallback (older desktop) |
|---|---|---|
| Assistant text | `MessageTextContent` (core markdown and media) | plain pre-wrapped text |
| Composer ring and fill | `composerSurfaceRing`, `composerInputBacking` | scoped CSS on the same tokens |
| Send and Stop, icon buttons | `Button` + `PRIMARY_ICON_BTN` / `GHOST_ICON_BTN` | our own buttons |
| Icons, tooltips, spinner | `Codicon`, `Tip`, `GlyphSpinner` | inline SVG, `title`, CSS spinner |
| User bubble | `--dt-user-bubble` fill, `--ui-stroke-tertiary` hairline, `rounded-xl` | same tokens |
| Type scale | `--conversation-text-font-size`, `--dt-line-height` | same tokens |

Every SDK part is feature-detected, so the page never crashes on a desktop build that lacks one.

## 2. The upgrade: what the main thread doesn't do

1. **Edit receipts, not tool spam.** A `rookery_*` call doesn't print a raw tool row. Each edit becomes one plain sentence ("Kick · 6 hits added", "Swing 50% → 58%") built from the engine's own `project.updated` diff, so it states what changed, not what was called. Hovering a receipt lights the exact pads in the rack.
2. **A turn is one block.** While Hermes works, the newest receipts stream in (the last four show; earlier ones fold away). When the turn ends, the block collapses to one summary line: "Built 5 tracks · 14 edits · 6/6 checks". Click to expand.
3. **Undo the turn.** The summary has "Undo turn", which reverts every edit that turn made (`POST /undo {steps: N}`). It only shows while those edits are still the latest.
4. **Render receipts play.** A render line shows the check lights and the hash, plus a play button that drives the page's own engine. There is only one audio engine.
5. **Status lives on the composer.** A slim strip on the composer's top edge says what Hermes is doing in present tense ("Writing the hats", "Rendering", "Thinking"), with elapsed time and Stop. Nothing jumps around in the transcript.
6. **Calm scroll.** The transcript sticks to the bottom only while you're at the bottom. Scroll up and it stays put, with a "New activity" pill to jump back down.
7. **Context you can see.** The composer shows a chip for the project Hermes will work on. It's on by default, and you click it to drop it. The chip is sent as a one-line `[Rookery: name]` header and drawn as a chip in your bubble, never as raw text.
8. **Suggestions that fit the beat.** With the input empty and Hermes idle, pills above the composer offer next moves that fit the project (starter prompts with no project; "Dustier", "Fill in bar 4", "Swing it harder" after a render).
9. **Reasoning stays out of the way.** Reasoning shows as "Thinking" in the status strip, not as a wall of text.

## 3. Layout

- **Wide (≥ 1100 px):** instrument on the left (flex), chat rail on the right (380 px; drag to resize between 320 and 560 px; the width persists). The rail runs full height: header, transcript, composer.
- **Narrow:** the chat becomes a bottom sheet. Collapsed, it shows the composer and the status line; opened, it takes 60% of the height.
- **Collapsed rail:** a 40 px strip with the chat icon and an unread dot. One click brings the chat back.
- **Header:** the model name (quiet), New chat, Dock beside chat, Collapse.

## 4. Session model

- There is one current Hermes session for Rookery. Its stored id persists in `ctx.storage` (`chat.session`), so the agent keeps context across projects ("now a trap version of that"). **New chat** starts another.
- Create is lazy: `session.create {request_id, source:'desktop', model?, provider?}` runs on the first send, so no empty "Untitled" rows.
  - **No `title`.** The desktop's owner protocol treats a title as the session's identity: every create titled "Rookery" came back as the first Rookery session, with its old model and history. Hermes auto-titles from the first message instead, like its own chats. Verified live on Nov 8.
  - **Fresh `request_id` per create.** The desktop memoizes one per identical params, and a repeated id is answered with the same session.
- **Model:** the composer's control row has Hermes's own model pill, rebuilt from the SDK's parts (`Button`, `Tip`, `DropdownMenu*`, `Badge`, `DisclosureCaret`) with core's class strings from `composer/model-pill.tsx` and `shell/model-catalog-menu.tsx`:
  - a ghost pill "Name · Tag ⌄" with the accent dot when Rookery has its own pick;
  - a `w-72` menu opening upward, with search (Enter takes the top match);
  - collapsible provider groups, and rows with variant badges, prices, green "Free" and a check on the current model;
  - a "Default" row that returns to Hermes's model.
  The catalog is `model.options`, cached for 2 minutes and bounded at 20 s. A new pick persists (`chat.model`) and starts a new chat, because a session's model is fixed at create. Re-picking the current model keeps the chat. Builds without the dropdown parts fall back to a scoped-CSS picker.
  - Not carried over from core: favorites (stars), reasoning and speed submenus, plan-limit lines. Those live in Hermes's own stores, which the SDK doesn't expose.
- **Keyboard:** Hermes fires every Ctrl/Cmd chord globally, even inside text fields (`lib/keybinds/combo.ts`). A user binding on Ctrl+A therefore fires from the Rookery composer exactly as it does from the main one. That's parity, not a bug.
- On reopen, `session.resume {session_id: stored}` returns the runtime id plus history, which repaints the transcript.
- Send: `prompt.submit {session_id, text}`. Stop: `session.interrupt {session_id}`. Busy comes from the stream itself (start → complete), cross-checked against `host.state.busyBySession`.
- Stream: gateway events filtered by `session_id`: `message.start | message.delta | message.complete`, `tool.start | tool.complete`, `reasoning.delta`, plus `approval.request | clarify.request`. Edits come from `plugin.rookery.project.updated` (`source: 'agent'`), attached to the open turn.
- **Escape hatch:** an approval or clarify request gets a notice row, "Hermes needs your answer", with **Answer in chat** (`host.openSession(stored)`). Rookery never answers approvals itself.

## 5. Dock beside chat (option)

**Dock beside chat** runs `host.openSession(stored)`, which puts the same conversation in the main thread, then `host.openWorkspace('rookery', {dock: {pane:'workspace', pos:'right'}})`, which docks the instrument beside it with its own chat rail hidden. **Bring chat back** undoes it. Both paths are feature-detected. If `openWorkspace` is missing, the option is hidden.

## 6. Motion and states

- Receipts enter with a 120 ms rise and fade. The summary collapse uses a height transition. Reduced motion turns all of it off.
- Streaming text shows a soft caret at the end. Nothing jumps when the final text lands.
- States: no gateway ("Hermes is offline": composer disabled, a reason shown); sending; streaming; error (the turn's error as a notice row, with Retry); interrupted ("Stopped").
- Keyboard: Enter sends, Shift+Enter adds a new line, Esc stops while busy, ⌘/Ctrl+L focuses the chat.
