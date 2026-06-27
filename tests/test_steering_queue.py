from agentforge_harness.agent.steering_queue import SteeringQueue


def test_push_pop_steer_fifo():
    q = SteeringQueue()
    q.push_steer("first")
    q.push_steer("second")
    assert q.pop_steer() == "first"
    assert q.pop_steer() == "second"
    assert q.pop_steer() is None


def test_push_pop_follow_up_fifo():
    q = SteeringQueue()
    q.push_follow_up("a")
    q.push_follow_up("b")
    assert q.pop_follow_up() == "a"
    assert q.pop_follow_up() == "b"
    assert q.pop_follow_up() is None


def test_steer_and_follow_up_are_independent():
    q = SteeringQueue()
    q.push_steer("steer")
    q.push_follow_up("follow")
    assert q.pop_follow_up() == "follow"
    assert q.pop_steer() == "steer"


def test_snapshot_shape():
    q = SteeringQueue()
    q.push_steer("s1")
    q.push_follow_up("f1")
    snap = q.snapshot()
    assert snap["steer"] == ["s1"]
    assert snap["follow_up"] == ["f1"]


def test_clear_empties_both_queues():
    q = SteeringQueue()
    q.push_steer("x")
    q.push_follow_up("y")
    q.clear()
    assert q.pop_steer() is None
    assert q.pop_follow_up() is None
    assert q.snapshot() == {"steer": [], "follow_up": []}
