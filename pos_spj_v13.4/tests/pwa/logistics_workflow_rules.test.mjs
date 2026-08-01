import test from "node:test";
import assert from "node:assert/strict";

import { bottomUp, canDispatch, nodeDepth, validateAssignment } from
  "../../frontend/web/logistics/workflow_rules.js";

test("container tree orders children before parents and rejects cycles", () => {
  const nodes = [{ id: "root", parentNodeId: null }, { id: "box", parentNodeId: "root" },
    { id: "tray", parentNodeId: "box" }];
  assert.equal(nodeDepth(nodes[2], nodes), 2);
  assert.deepEqual(bottomUp(nodes).map((item) => item.id), ["tray", "box", "root"]);
  assert.throws(() => nodeDepth({ id: "a", parentNodeId: "b" }, [
    { id: "a", parentNodeId: "b" }, { id: "b", parentNodeId: "a" }]), /ciclo/);
});

test("catalog requirements enforce weight, lot and expiration", () => {
  const product = { catchWeightEnabled: true, lotControlled: true,
    expirationControlled: true };
  assert.throws(() => validateAssignment(product, {
    nodeId: "node", quantity: "1", netWeight: "0", lotNumber: null,
    expirationDate: null }), /peso neto.*lote.*caducidad/);
  assert.equal(validateAssignment(product, {
    nodeId: "node", quantity: "1", netWeight: "2.500", lotNumber: "L-1",
    expirationDate: "2026-12-01" }), true);
});

test("dispatch requires sync, seals, connectivity and zero conflicts", () => {
  const state = { nodes: [{ id: "a" }], sealedNodeIds: ["a"], pending: 0,
    conflicts: 0, online: true };
  assert.equal(canDispatch(state), true);
  assert.equal(canDispatch({ ...state, conflicts: 1 }), false);
  assert.equal(canDispatch({ ...state, pending: 1 }), false);
  assert.equal(canDispatch({ ...state, online: false }), false);
});
