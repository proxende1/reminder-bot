from datetime import UTC, datetime, timedelta

from bot.db import Database

USER, OTHER = 1, 2
T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


async def test_add_get_and_isolation(db: Database):
    reminder = await db.add(USER, USER, "чай", T0)
    assert await db.get(USER, reminder.id) == reminder
    assert await db.get(OTHER, reminder.id) is None
    assert await db.delete(OTHER, reminder.id) is False


async def test_due_returns_only_ripe_unfired(db: Database):
    ripe = await db.add(USER, USER, "ripe", T0 - timedelta(minutes=1))
    await db.add(USER, USER, "later", T0 + timedelta(minutes=1))
    fired = await db.add(USER, USER, "fired", T0 - timedelta(hours=1))
    await db.mark_fired(fired.id)

    assert [r.id for r in await db.due(T0)] == [ripe.id]


async def test_list_active_sorted_and_hides_fired(db: Database):
    b = await db.add(USER, USER, "b", T0 + timedelta(hours=2))
    a = await db.add(USER, USER, "a", T0 + timedelta(hours=1))
    c = await db.add(USER, USER, "c", T0)
    await db.mark_fired(c.id)
    assert [r.id for r in await db.list_active(USER)] == [a.id, b.id]


async def test_reschedule_unfires(db: Database):
    reminder = await db.add(USER, USER, "x", T0)
    await db.mark_fired(reminder.id)
    await db.reschedule(reminder.id, T0 + timedelta(hours=1))
    loaded = await db.get(USER, reminder.id)
    assert not loaded.fired
    assert loaded.remind_at == T0 + timedelta(hours=1)


async def test_purge_fired(db: Database):
    old = await db.add(USER, USER, "old", T0 - timedelta(days=10))
    fresh = await db.add(USER, USER, "fresh", T0 - timedelta(days=1))
    active = await db.add(USER, USER, "active", T0 - timedelta(days=10))
    await db.mark_fired(old.id)
    await db.mark_fired(fresh.id)

    assert await db.purge_fired(T0 - timedelta(days=7)) == 1
    assert await db.get(USER, old.id) is None
    assert await db.get(USER, fresh.id) is not None
    assert await db.get(USER, active.id) is not None


async def test_repeat_is_stored(db: Database):
    reminder = await db.add(USER, USER, "x", T0, repeat="daily")
    assert (await db.get(USER, reminder.id)).repeat == "daily"
