"""Optional live check: python -m scripts.check_meta_api (from repository root).

Export META_API_KEY first. This performs a real, billable request only when
main() is explicitly called. The check always uses muse-spark-1.3.
"""

import sys

from backend.agent.config import DEFAULT_META_MODEL, MetaConfig
from backend.agent.errors import MuseAPIError, MuseConfigurationError
from backend.agent.provider import MuseProvider


EXPECTED_REPLY = "GRIDPROBE META OK"


def main() -> int:
    """Print the model reply and available usage; return nonzero on failure."""
    try:
        config = MetaConfig.from_env().model_copy(update={"model": DEFAULT_META_MODEL})
        with MuseProvider(config) as provider:
            response = provider.chat_completion([
                {"role": "developer", "content": f'Reply with exactly "{EXPECTED_REPLY}" and no other text.'},
                {"role": "user", "content": "Check connectivity."},
            ])
    except (MuseConfigurationError, MuseAPIError) as exc:
        print(f"Meta connectivity check failed: {exc}", file=sys.stderr)
        return 1

    content = response.choices[0].message.content if response.choices else None
    print(content if content is not None else "No text response received.")
    if response.usage is not None:
        print(f"Token usage: {response.usage.model_dump_json()}")
    if content != EXPECTED_REPLY:
        print("Meta connectivity check returned an unexpected reply.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
