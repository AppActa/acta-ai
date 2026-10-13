import importlib

from langchain_openai import ChatOpenAI
from pytest import MonkeyPatch

import config


def test_agents_share_one_gpt_6_luna_openai_model(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    llms = importlib.import_module("agents.helpers.llms")

    assert isinstance(llms.llm, ChatOpenAI)
    assert llms.llm.model_name == "gpt-6-luna"
    assert llms.llm.reasoning_effort == "none"
