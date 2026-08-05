export function nodeDepth(node, nodes) {
  let result = 0; let cursor = node; const seen = new Set([node.id]);
  while (cursor?.parentNodeId) {
    if (seen.has(cursor.parentNodeId)) throw new Error("La jerarquía contiene un ciclo");
    seen.add(cursor.parentNodeId); result += 1;
    cursor = nodes.find((item) => item.id === cursor.parentNodeId);
    if (!cursor) throw new Error("El contenedor padre no existe");
  }
  return result;
}

export function bottomUp(nodes) {
  return [...nodes].sort((a, b) => nodeDepth(b, nodes) - nodeDepth(a, nodes));
}

export function validateAssignment(product, values) {
  const errors = [];
  if (!product) errors.push("Selecciona un producto del documento");
  if (!values.nodeId) errors.push("Selecciona el contenedor físico");
  if (!(Number(values.quantity) > 0)) errors.push("La cantidad debe ser mayor a cero");
  if (!(Number(values.netWeight) >= 0)) errors.push("El peso neto no es válido");
  if (product?.catchWeightEnabled && !(Number(values.netWeight) > 0))
    errors.push("El producto de peso variable requiere peso neto");
  if (product?.lotControlled && !values.lotNumber) errors.push("El producto requiere lote");
  if (product?.expirationControlled && !values.expirationDate)
    errors.push("El producto requiere caducidad");
  if (errors.length) throw new Error(errors.join(". "));
  return true;
}

export function canDispatch({ nodes, sealedNodeIds, pending, conflicts, online }) {
  return Boolean(nodes.length && online && pending === 0 && conflicts === 0 &&
    sealedNodeIds.length === nodes.length);
}
