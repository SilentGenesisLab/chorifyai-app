# Source Ledger

Audited 2026-07-11. External repositories are research inputs, not installed runtime dependencies.

| Source | License / revision | Adopted | Rejected |
| --- | --- | --- | --- |
| [OpenAI Codex imagegen](https://github.com/openai/codex/blob/5c19155/codex-rs/skills/src/assets/samples/imagegen/SKILL.md) | Apache-2.0 / `5c19155` | Generate/edit split, asset roles, invariants, single-change iterations | No assumption that a built-in tool equals our server API |
| [Open Design ecommerce workflow](https://github.com/nexu-io/open-design/blob/4567a0d/skills/ecommerce-image-workflow/SKILL.md) | Apache-2.0 / `4567a0d` | Product truth, role images, manifest, honest QC | No unsupported marketplace claims |
| [Google Stitch generate-design](https://github.com/google-labs-code/stitch-skills/blob/3f64079/plugins/stitch-design/skills/generate-design/SKILL.md) | Apache-2.0 / `3f64079` | UI brief, structural variants, targeted revision | Stitch MCP is not an MVP dependency |
| [Anthropic frontend-design](https://github.com/anthropics/skills/blob/9d2f1ae/skills/frontend-design/SKILL.md) | Apache-2.0 / `9d2f1ae` | Explicit visual direction and non-generic design critique | A bitmap is not a runnable UI |
| [GPT-Image2-Skill](https://github.com/wuyoscar/GPT-Image2-Skill/tree/e48b023) | MIT / `e48b023` | Image taxonomy, exact-text prompting, edit invariants | Marketing quality adjectives as API capabilities |
| [Product Engineer Agent](https://github.com/michaelboeding/skills/blob/84abf02/skills/product-engineer-agent/SKILL.md) | MIT / `84abf02` | Separate industrial form, mechanics, manufacturing, and user views | AI render as CAD or manufacturing proof |
| [Inpaint Anything](https://github.com/geekyutao/Inpaint-Anything/tree/5bfa9f3) | Apache-2.0 / `5bfa9f3` | Click/region selection, candidate masks, boundary refinement | Heavy segmentation runtime in the MVP |

Primary API facts come from the [OpenAI image editing guide](https://developers.openai.com/api/docs/guides/image-generation#edit-images) and [Images API](https://developers.openai.com/api/reference/resources/images/methods/edit). Mask guidance is treated as best effort; strict preservation comes from local compositing.
