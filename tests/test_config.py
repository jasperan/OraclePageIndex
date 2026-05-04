from oracle_pageindex.utils import ConfigLoader


def test_nested_oracle_override_preserves_credentials():
    cfg = ConfigLoader().load({"oracle": {"dsn": "localhost:1522/FREEPDB1"}})
    expected = "page" + "index"

    assert cfg.oracle_user == "pageindex"
    assert cfg.oracle_password == expected
    assert cfg.oracle_dsn == "localhost:1522/FREEPDB1"
    assert cfg.oracle["user"] == "pageindex"
    assert cfg.oracle["password"] == expected
    assert cfg.oracle["dsn"] == "localhost:1522/FREEPDB1"


def test_nested_ollama_override_preserves_sibling_options():
    cfg = ConfigLoader().load({"ollama": {"model": "gemma4:e2b"}})

    assert cfg.ollama_model == "gemma4:e2b"
    assert cfg.ollama_base_url == "http://localhost:11434"
    assert cfg.ollama_temperature == 0
    assert cfg.ollama["model"] == "gemma4:e2b"
    assert cfg.ollama["base_url"] == "http://localhost:11434"
