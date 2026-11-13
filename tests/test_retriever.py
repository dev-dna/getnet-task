from app import retriever


def test_retrieve_finds_topic():
    chunks = retriever.retrieve("preciso de conta bancária para receber Pix", lang="pt")
    assert chunks and "pix" in (chunks[0]["title"] + chunks[0]["text"]).lower()


def test_english_question_reaches_portuguese_page():
    """Sem o glossário, 'receivables advance' não tem palavra em comum com a página em português."""
    pt_only = [c for c in retriever.retrieve("how does receivables advance work", k=10) if c["lang"] == "pt"]
    assert any("antecipa" in c["text"].lower() for c in pt_only)


def test_nonsense_returns_nothing():
    assert retriever.retrieve("xyzzy qwfp zxcv") == []


def test_sample_corpus_is_flagged():
    if not retriever.CORPUS_PATH.exists():
        assert retriever.is_placeholder()
