from assistant.ratelimit import RateLimiter


class Clock:
    t = 1_800_000_000.0

    def __call__(self):
        return self.t


def test_per_ip_limit_and_recovery():
    c = Clock()
    rl = RateLimiter(2, 100, 100, clock=c)
    assert rl.check("a")[0] and rl.check("a")[0]
    ok, reason, retry = rl.check("a")
    assert (ok, reason) == (False, "per_ip") and retry >= 1
    assert rl.check("b")[0]
    c.t += 61
    assert rl.check("a")[0]


def test_global_limit():
    rl = RateLimiter(10, 2, 100, clock=Clock())
    assert rl.check("a")[0] and rl.check("b")[0]
    assert rl.check("c")[:2] == (False, "global")


def test_daily_cap_resets_next_day():
    c = Clock()
    rl = RateLimiter(100, 100, 2, clock=c)
    assert rl.check("a")[0] and rl.check("b")[0]
    assert rl.check("c")[:2] == (False, "daily")
    c.t += 86400
    assert rl.check("c")[0]
