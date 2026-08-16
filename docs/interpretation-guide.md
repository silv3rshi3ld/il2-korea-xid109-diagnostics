# Interpretation guide

Use three evidence levels consistently.

## OBSERVED

Directly present in captured artifacts. Examples:

- Baseline and no-descriptor-buffer both produced Xid 109.
- Both reports contain shader hash `0123456789abcdef` inside the parsed potential region.
- The single-queue run recorded at least 600 seconds after READY in the fully rendered hangar, and no Xid 109 was captured.

State both Proton runtime and READY observation duration for negative observations. Proton runtime begins before the hangar is ready and is not the negative-observation clock. The automatic ten-minute threshold uses `observation_duration_seconds`, measured from the tester's READY marker to finalization. A clean negative requires at least 600 seconds after READY, normal exit, no interruption or capture warning, and no captured Xid or device loss.

READY is a recorded tester declaration, not visual verification. Before describing a run as protocol-valid, the coordinator must also confirm the tester's note that READY was marked only after the correct known-failing hangar fully rendered and that the scene and settings remained as agreed. Without that confirmation, downgrade the protocol assessment to inconclusive. “Not observed” is not “cannot occur.”

## INFERRED

A cautious implication supported by comparisons. Examples:

- Failure without descriptor buffers makes descriptor-buffer use less likely to be the sole trigger.
- Stability with `single_queue` makes queue topology or timing a stronger lead.
- Stability under synchronized breadcrumbs makes timing/synchronization sensitivity more plausible.

These comparisons do not isolate every secondary timing or memory-layout effect.

## PROVEN

A claim demonstrated strongly enough to exclude alternatives. This four-run phase is unlikely to prove the driver, a specific shader, a resource, or a VKD3D command implementation defective. The default analyzer therefore states that no root cause is proven.

## Matrix outcomes

| Observation | Supported inference | Unsupported claim |
|---|---|---|
| Baseline and single-queue fail in the same normalized region | Async queues are less likely to be necessary | Async compute is ruled out |
| Baseline fails; single-queue has no Xid in its captured duration | Queue topology or timing may influence reproduction | Async compute causes the Xid |
| Baseline and no-descriptor-buffer fail in the same region | Descriptor buffers are less likely to be the sole trigger | Descriptor buffers are ruled out |
| Baseline fails; no-descriptor-buffer has no Xid | Descriptor path or timing may influence reproduction | Descriptor buffers are defective |
| Baseline fails; sync has no Xid | Timing/synchronization sensitivity becomes more plausible | A synchronization bug is proven |
| Multiple failures converge on one region and shader hash | The region is a focused candidate | The shader is faulty |

## Checkpoint limits

Top-of-pipe progress shows that the command processor reached a marker. Bottom-of-pipe progress shows retirement through a marker. Commands between those points are possible contributors, but checkpoint placement, pipelining, and the eventual device-lost observation limit precision. `breadcrumbs_sync` narrows some ambiguity by adding strong barriers but also changes execution.

Xid channel and `Info` values should be compared across runs as signatures. They do not, by themselves, map to a D3D12 command or prove the application submitted invalid work.

Automatic matrix progression requires a READY marker recorded before the failure, an Xid 109 line attributed to `IL2Series.exe`, completed device-lost breadcrumb analysis, at least one parsed crash region, verified kernel collection, and no interruption, malformed metadata, or capture warning. A pre-READY, unattributed, recovered, warned, or region-less Xid remains recorded evidence but is labeled `REVIEW REQUIRED`; it is not silently treated as a complete forensic case.
