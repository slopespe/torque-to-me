"""Config precedence: defaults < config.toml/TORQUE_TO_ME_CONFIG < CLI flags."""

import pytest

from torque_to_me import config


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Run every test from an empty directory with no config env var."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    return tmp_path


def test_defaults_when_no_file():
    cfg = config.load()
    assert cfg.answer.model == "gemma4:12b"
    assert cfg.answer.num_ctx == 16384
    assert cfg.extract.parallel_workers == 1
    assert cfg.ollama.url == "http://localhost:11434"
    assert cfg.source is None


def test_explicit_file_overrides_defaults(tmp_path):
    toml = tmp_path / "custom.toml"
    toml.write_text('[answer]\nmodel = "other-model"\n')
    cfg = config.load(path=toml)
    assert cfg.answer.model == "other-model"
    assert cfg.answer.num_ctx == 16384  # untouched keys keep defaults
    assert cfg.source == toml


def test_config_toml_in_cwd_is_picked_up(isolated_cwd):
    (isolated_cwd / "config.toml").write_text('[extract]\nmodel = "cwd-model"\n')
    cfg = config.load()
    assert cfg.extract.model == "cwd-model"


def test_env_var_wins_over_cwd_file(isolated_cwd, tmp_path, monkeypatch):
    (isolated_cwd / "config.toml").write_text('[answer]\nmodel = "cwd-model"\n')
    env_file = tmp_path / "env.toml"
    env_file.write_text('[answer]\nmodel = "env-model"\n')
    monkeypatch.setenv(config.ENV_VAR, str(env_file))
    cfg = config.load()
    assert cfg.answer.model == "env-model"


def test_unknown_key_warns_and_is_ignored(tmp_path, capsys):
    toml = tmp_path / "typo.toml"
    toml.write_text('[answer]\nmodle = "x"\n')
    cfg = config.load(path=toml)
    assert cfg.answer.model == "gemma4:12b"
    assert "unknown key(s) in [answer]: modle" in capsys.readouterr().err


def test_unknown_section_warns(tmp_path, capsys):
    toml = tmp_path / "extra.toml"
    toml.write_text("[nonsense]\nkey = 1\n")
    config.load(path=toml)
    assert "unknown section [nonsense]" in capsys.readouterr().err


def test_missing_explicit_path_exits(tmp_path):
    with pytest.raises(SystemExit):
        config.load(path=tmp_path / "does-not-exist.toml")


def test_missing_env_file_exits(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_VAR, str(tmp_path / "gone.toml"))
    with pytest.raises(SystemExit):
        config.load()
