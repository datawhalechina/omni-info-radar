from repo_courier.config import RepoLlmConfig
from repo_courier.models import Repository
from repo_courier.summary import Summarizer


def test_fallback_summary_without_ai_credentials() -> None:
    repository = Repository(
        rank=1,
        owner="acme",
        name="agent-kit",
        url="https://github.com/acme/agent-kit",
        description="A toolkit for building LLM agents",
        language="Python",
        stars_today=321,
        topics=["llm", "agent"],
    )

    Summarizer(RepoLlmConfig(model="", api_key="")).summarize([repository])

    assert repository.summary == "A toolkit for building LLM agents"
    assert repository.category == "AI / 机器学习"
    assert any("321" in item for item in repository.highlights)
    assert repository.risk_note == ""
    assert repository.analysis_status == "fallback"


def test_fallback_summary_supports_english_output() -> None:
    repository = Repository(
        rank=1,
        owner="acme",
        name="agent-kit",
        url="https://github.com/acme/agent-kit",
        language="Python",
        stars_today=321,
        topics=["llm", "agent"],
    )

    Summarizer(
        RepoLlmConfig(model="", api_key="", output_language="en")
    ).summarize([repository])

    assert repository.summary == "An open-source project primarily written in Python"
    assert repository.category == "AI / Machine Learning"
    assert any("Primary language" in item for item in repository.highlights)
    assert repository.use_cases == ["AI prototyping and capability integration"]


def test_summary_uses_shared_chat_completions_url_directly() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"repositories":[{"full_name":"acme/tool",'
                            '"summary":"中文概要","highlights":[],"use_cases":[]}]}'
                        }
                    }
                ]
            }

    class Client:
        url = ""

        def post(self, url, **kwargs):
            self.url = url
            return Response()

    client = Client()
    repository = Repository(
        rank=1,
        owner="acme",
        name="tool",
        url="https://github.com/acme/tool",
    )
    endpoint = "https://example.com/v1/chat/completions"

    Summarizer(
        RepoLlmConfig(api_key="secret", base_url=endpoint, model="model"), client
    ).summarize([repository])

    assert client.url == endpoint
    assert repository.summary == "中文概要"
    assert repository.analysis_status == "ai"
