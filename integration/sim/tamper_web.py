"""The website-path tampering cases W-T1 to W-T8 (PROTOCOL.md section 14.5, G-TAMPER).

Each case is a verdict from ``integration/vectors/verdict-binding/W-T*.json`` (a tampered decision, a substituted
answer, an old verdict replayed for another attempt, a changed scope statement, an extra field, a forged clearance
state, a status shown as success, a stripped signature) served to the Worker instead of the service's real verdict.
Through the website path (the patched export's handler, the release gate in src/verify/release-gate.js and the
D1 store), each must be refused with its expected raw code and nothing may be stored as an answer.

``adapter_results`` runs the same cases through the Worker's release gate module alone (Node.js), which is what
refuses them; it is reported as a sub-check, never as the gate: the gate needs the whole website path.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

__all__ = ["CASES", "adapter_results"]

CASES = ("W-T1-tampered-decision", "W-T2-substituted-answer", "W-T3-verdict-of-another-attempt", "W-T4-changed-scope-statement",
         "W-T5-extra-field", "W-T6-forged-clearance-state", "W-T7-status-shown-as-success", "W-T8-stripped-signature")

_SCRIPT = """
import { bindingProblem } from %(gate)s;
import { readFileSync } from "node:fs";
const out = {};
for (const name of %(cases)s) {
  const v = JSON.parse(readFileSync(%(vectors)s + "/" + name + ".json", "utf8"));
  const c = v.context;
  const p = await bindingProblem(v.verdict, { taskId: c.task_id, requestId: c.request_id, userText: c.user_text, policy: c.policy, mode: c.mode,
                                              answers: c.answers, releaseText: c.release_text, revisionOf: c.revision_of });
  out[name.slice(0, name.indexOf("-", 2))] = { expected: v.expect.raw_code, got: p ? p[0] : null };
}
console.log(JSON.stringify(out));
"""


def adapter_results(kit: Path) -> Optional[dict]:
    node = shutil.which("node")
    if node is None:
        return None
    gate = (kit / "integration" / "website" / "src" / "verify" / "release-gate.js").as_uri()
    vectors = str(kit / "integration" / "vectors" / "verdict-binding")
    script = _SCRIPT % {"gate": json.dumps(gate), "cases": json.dumps(list(CASES)), "vectors": json.dumps(vectors)}
    proc = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return {"error": proc.stderr[-500:]}
    return json.loads(proc.stdout)
