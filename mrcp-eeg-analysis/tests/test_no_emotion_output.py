def test_active_source_has_no_emotion_pipeline():
    from pathlib import Path
    src=Path(__file__).resolve().parents[1]/"src"
    active="\n".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    assert "emotion_frequency.csv" not in active and "emotion_mapping" not in active
