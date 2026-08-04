---
name: rehydrate-input
description: 'Deprecated - replaced by plan-pipeline section 4F (input integration is now automatic at PLAN retire). Removed in v2.0.0.'
---

This surface is deprecated. Replaced by: plan-pipeline section 4F (input integration is now automatic at PLAN retire). Removed in: v2.0.0. Consume-side companion to write-input. Its input mode flipped integration_status to integrated on operator confirmation; plan-pipeline section 4F now does that automatically when a PLAN listing the input in linked_inputs retires, so the manual step is gone. Its asset mode stamped last_consulted and consulted_by on helpers and references for the reusable-asset registry, which was removed on 2026-08-03 (PLAN-AJ4) as a projection that listed objects for the sake of listing them. Your copy is not deleted on sync - it is moved to .claude/.plan-foundry-quarantine/<timestamp>/ and is recoverable from there.
