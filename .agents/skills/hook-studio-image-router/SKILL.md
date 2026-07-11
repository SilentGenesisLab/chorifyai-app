---
name: hook-studio-image-router
description: Compile Hook Studio image generation and editing requests into executable, versioned production contracts. Use for ecommerce images, UI/UX concepts, product or industrial-design concepts, storyboards, general image creation, batch variants, exact-text images, reference repainting, masks, annotated arrows, local edits, object removal/replacement, outpainting, and multi-step conversational edits. Route source-truth work separately from concept work and never expose provider credentials.
---

# Hook Studio Image Router

Turn a loose Chinese conversation and uploaded assets into one provider-ready image contract. Do not call a provider until roles, allowed changes, invariants, cost, and fallback are explicit.

## Workflow

1. Classify `action`, `domain`, and `fidelity_label`.
2. Assign every asset exactly one role: `edit_target`, `product_truth`, `identity`, `style`, `layout`, `insert`, `mask`, or `annotation`.
3. Ask one question only when a missing fact blocks safe execution. Otherwise compile immediately.
4. Load this router plus at most two matching specialist skills.
5. Produce the contract in `references/contracts.md` and a concise Chinese confirmation summary.
6. Route through the server adapter. The browser never calls a provider and never receives a provider key.
7. Preserve the source, contract, mask, provider output, final composite, QC, cost, and user action as one version lineage.

## Fidelity Labels

- `SOURCE_TRUE`: The real SKU, packaging, exact UI, or verified geometry must not drift.
- `REFERENCE_FAITHFUL`: The result may change the scene but must preserve named product or identity invariants.
- `LOCAL_EDIT`: Change only a described or masked region; preserve everything else.
- `CONCEPT_ONLY`: Visual exploration may invent reasonable details and must not be presented as engineering truth.

## Domain Routing

- Ecommerce: use `product-consistency-locks`, then this router, then commercial QC. Prefer real packshot compositing for exact packaging or legal copy.
- UI/UX: use image generation for moodboards and visual concepts. Route a usable interface to React/HTML rather than presenting a bitmap as an implementable product.
- Product/industrial design: use `product-nine-view-builder` or `visual-realism-director`. Label renders without CAD, dimensions, loads, and manufacturing constraints as `CONCEPT_ONLY`.
- Local edit: use the mask rules below and the preservation contract. Use `identity-locked-inpainting` when a real person is the source truth.
- Storyboard: choose the lightest representation that makes outcome, action, camera, timing, and uncertainty understandable. A grid is optional, not a gate.

## Mask And Annotation Rules

- A mask is optional. A clear prompt or semantic target may be enough for a best-effort edit.
- Text, arrows, boxes, and circles are optional localization aids, not masks and not required inputs.
- When an annotation exists, state that it controls location only and must not appear in the result.
- Direct route: source image + optional PNG mask + prompt -> `/v1/images/edits`.
- Degraded route: source + optional annotation/crop -> reference repaint -> deterministic mask composite.
- Always store the raw provider output. When a mask exists, restore all outside-mask pixels from the source before delivery.
- A small feather may be used only inside the original selected region. Outside-mask pixels must remain source pixels.
- Never claim that model-native mask editing is pixel-exact. The deterministic composite is the strict preservation mechanism.

Read `references/mask-editing.md` before implementing or reviewing a local edit.

## Prompt Packet

Write prompts in this order:

```text
Asset roles -> requested change -> final desired state -> must preserve -> exact text -> forbidden output
```

For exact text, quote it verbatim and specify placement and typography. If a spelling, SKU, price, legal line, or UI label must be exact, plan deterministic code/post overlay as the final authority.

## Batch Rules

- One batch is a parent contract with independent child assets.
- Separate locked fields from variation axes.
- Use one prompt per distinct asset; `n` is only for variants of the same prompt.
- Execute in bounded waves selected from live provider latency and rate evidence. Do not expose a fixed global worker count as a product rule.
- Apply tenant-fair scheduling so a large batch cannot starve another customer or an interactive edit.

## Required Output

Return:

```text
任务类型与真实性等级:
素材角色与事实锁:
允许变化 / 必须保持:
Skill 链及版本:
生产提示包:
Provider 能力要求:
预算与批量矩阵:
降级路径:
QC 与第一失败点:
用户确认摘要:
```

## Data Capture

Persist `router_version`, specialist versions, contract version, source hashes, asset roles, mask/annotation, sanitized provider payload, provider capability snapshot, raw result, final result, QC, latency, cost units, retries, user revisions, selections, downloads, and deletes. Never persist credentials or raw authorization headers.

## References

- `references/contracts.md`: typed input/output and persistence fields.
- `references/mask-editing.md`: direct edit and deterministic composite procedure.
- `references/source-ledger.md`: audited official and community sources plus adoption decisions.
