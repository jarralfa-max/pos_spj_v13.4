from pathlib import Path


def test_wiring_registers_phase7_loyalty_handlers():
    src = Path('core/events/wiring.py').read_text(encoding='utf-8')
    expected = [
        'LOYALTY_CARD_ASSIGNED',
        'LOYALTY_CARD_BLOCKED',
        'LOYALTY_REFERRAL_REWARDED',
        'LOYALTY_BIRTHDAY_REWARD_ISSUED',
        'LOYALTY_FRAUD_BLOCKED',
    ]
    for ev in expected:
        assert f'bus.subscribe({ev}' in src, f'Missing handler subscription for {ev}'


def test_ui_modules_do_not_publish_loyalty_events_directly():
    ui_files = [
        Path('modulos/fidelidad_config.py').read_text(encoding='utf-8'),
        Path('modulos/modulo_growth_engine.py').read_text(encoding='utf-8'),
    ]
    for src in ui_files:
        assert 'publish(' not in src, 'UI module must not publish events directly'
