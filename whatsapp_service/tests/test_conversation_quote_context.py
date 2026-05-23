import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import tempfile
from state.conversation import ConversationStore
from models.context import ConversationContext, FlowState


def test_quote_context_fields_are_persisted():
    with tempfile.TemporaryDirectory() as td:
        db_path = f"{td}/ctx.db"
        store = ConversationStore(db_path=db_path)
        ctx = ConversationContext(phone="5215512345678")
        ctx.state = FlowState.COTIZACION_CONFIRMACION
        ctx.current_quote_id = 44
        ctx.current_quote_folio = "COT-WA-44"
        store.save(ctx)

        loaded = store.get(ctx.phone)
        assert loaded.current_quote_id == 44
        assert loaded.current_quote_folio == "COT-WA-44"
