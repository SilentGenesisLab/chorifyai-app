# Mask Editing

## Direct Route

1. Preserve the untouched source image and hash it.
2. Normalize orientation and save a same-size PNG mask.
3. Treat fully transparent pixels as editable. Also accept black/white masks by converting luminance to alpha.
4. Send the source, optional mask, and preservation-first prompt to the server-only edit endpoint.
5. Persist partials when the provider returns them, the raw provider result, and the sanitized request trace.
6. Resize the raw provider result back to source dimensions before compositing.

## Deterministic Composite

1. Invert mask alpha to create the allowed edit region.
2. Threshold the allowed region so pixels outside it are exactly zero-weight.
3. Optionally blur the selection, then multiply it by the original allowed region so feathering cannot cross outside.
4. Composite edited pixels over the source.
5. Verify the outside-mask pixel difference is exactly zero.
6. Review target completion, boundary seams, lighting, product/identity drift, and exact text separately.

## Degraded Route

When the edit endpoint is unavailable:

1. Submit the source as the primary reference.
2. Optionally add one annotated localization image and one local crop.
3. State that annotations only locate the target and must not appear in output.
4. Generate a reference repaint.
5. Apply the same deterministic composite when a mask exists.

Do not claim a strict local edit when no mask exists. Label it `BEST_EFFORT_EDIT` and show the user what may drift.
