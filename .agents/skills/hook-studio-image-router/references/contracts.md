# Image Production Contract

```json
{
  "request_id": "...",
  "tenant_id": "...",
  "conversation_id": "...",
  "action": "generate|edit|remove|replace|outpaint|composite|variant",
  "domain": "ecommerce|ui_ux|product_design|industrial_design|storyboard|general",
  "fidelity_label": "SOURCE_TRUE|REFERENCE_FAITHFUL|LOCAL_EDIT|CONCEPT_ONLY",
  "target_use": "...",
  "user_text": "...",
  "assets": [
    {"id": "...", "role": "edit_target|product_truth|identity|style|layout|insert|mask|annotation", "sha256": "..."}
  ],
  "truth_lock": {
    "verified_facts": [],
    "must_preserve": [],
    "allowed_changes": [],
    "forbidden_changes": []
  },
  "edit_region": {
    "mode": "none|mask|bbox|semantic|full",
    "mask_asset_id": null,
    "annotation_asset_id": null
  },
  "visual_spec": {
    "aspect": "9:16",
    "size": "auto",
    "quality": "auto",
    "exact_text": [],
    "composition": null,
    "lighting": null,
    "materials": []
  },
  "batch": {"count": 1, "variation_axes": [], "locked_fields": []}
}
```

Router output:

```json
{
  "router_version": "1.0.0",
  "skill_chain": [],
  "provider_requirements": [],
  "prompt_packet": {},
  "provider_payload_without_secrets": {},
  "confirmation_summary": {},
  "cost_range": {},
  "fallback_plan": [],
  "qc_contract": {},
  "source_versions": []
}
```

Reject a contract when the edit target is ambiguous, a reference has multiple conflicting roles, a concept is presented as source truth, or a critical exact-text/geometry requirement has no deterministic fallback.
