from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vietnamese_link_label_remains_product_text():
    translations = (ROOT / "clients/web/ui/js/i18n.js").read_text()

    assert "attAddLink: '＋ Liên kết'" in translations
