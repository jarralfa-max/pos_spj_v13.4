from presentation.sales.cart_view_model import CartViewModel


def test_cart_vm_add_update_remove_clear_and_payload():
    vm = CartViewModel()
    it = vm.add_item({'id': 1, 'nombre': 'Pollo', 'cantidad': 2, 'precio_unitario': 10})
    uid = it['_uid']
    assert len(vm.items) == 1
    assert vm.update_quantity(uid, 3) is True
    assert vm.selected(uid)['total'] == 30
    payload = vm.to_item_carrito_payload()
    assert payload[0]['producto_id'] == 1
    assert vm.remove_by_uid(uid) is True
    vm.clear()
    assert vm.items == []
