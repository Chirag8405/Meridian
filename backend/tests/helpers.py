"""Fakes shared by the assistant tests: a table-dict data source and a scripted LLM."""

import json


class FakeSource:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.calls: list[str] = []

    async def table(self, name, order=None):
        self.calls.append(name)
        return self.tables.get(name, [])


class FakeLLM:
    """Returns scripted messages in order; records what it was sent."""

    def __init__(self, script: list[dict]):
        self.script = list(script)
        self.sent: list[tuple[list[dict], bool]] = []

    async def complete(self, messages, tools=None):
        self.sent.append((json.loads(json.dumps(messages)), tools is not None))
        item = self.script.pop(0)
        return {"message": item, "finish_reason": item.pop("_finish", "stop")}


def tool_call(name, args, cid="c1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


LIVE_ROWS = [
    {"pair": "USDC_DAI", "project": "curve", "risk_score": 4.357463592263221,
     "window_start_ts": "2026-10-25T03:00:00+00:00", "source": "alchemy_getlogs_replay",
     "price_dev": -0.4005594613424545, "cluster_id": 0, "cluster_severity": 0.05,
     "wallet_concentration_severity": 0.12830815594836484, "advisory": "x"},
    {"pair": "USDC_DAI", "project": "uniswap_v2", "risk_score": 7.704664214144552,
     "window_start_ts": "2026-10-23T15:00:00+00:00", "source": "alchemy_getlogs_replay",
     "price_dev": -1.9644359214397442, "cluster_id": 0, "cluster_severity": 0.05,
     "wallet_concentration_severity": 0.12830815594836484, "advisory": None},
]
EVAL_ROWS = [
    {"event_label": "USDC_MAR2023", "lead_time_hours": 72.0, "false_alarm_count": 12,
     "peak_score": 81.18, "elevated_threshold": 7.18, "first_warning_ts": "2023-03-08T00:00:00Z",
     "depeg_onset_ts": "2023-03-11T00:00:00Z", "calm_caveat": None, "calm_avg_volume_usd": 1.0},
    {"event_label": "UST_MAY2022", "lead_time_hours": 0.0, "false_alarm_count": 34,
     "peak_score": 56.31, "elevated_threshold": 7.18, "first_warning_ts": "2022-04-15T04:00:00Z",
     "depeg_onset_ts": "2022-04-15T04:00:00Z", "calm_caveat": "No genuine RELIABLE (calm) rows exist for UST.",
     "calm_avg_volume_usd": 2.0},
]
