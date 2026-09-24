"""Tests for the runs API routes.

These exercise route/DB behavior only -- the conftest `client` fixture
never starts the run_queue worker, so queued runs are created and
persisted but not actually executed here (run_service is covered
separately in test_run_service.py).
"""

import json

from app.database import AsyncSessionLocal
from app.models.asset_outcome import AssetOutcome
from app.models.run import Run


async def _configure_connection(client):
    await client.put(
        "/api/settings",
        json={
            "immich_api_base": "https://immich.example.com/api/",
            "immich_api_key": "key",
        },
    )


class TestCreateRun:
    async def test_requires_connection(self, client):
        resp = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        assert resp.status_code == 424

    async def test_creates_queued_run_with_snapshot(self, client):
        await _configure_connection(client)
        resp = await client.post(
            "/api/runs",
            json={"asset_types": "IMAGE", "dry_run": True, "video_crf": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["dry_run"] is True
        assert data["total_assets"] == 0

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == data["id"]))
            run = result.scalar_one()
            cfg = json.loads(run.config_snapshot)
            assert cfg["immich_api_base"] == "https://immich.example.com/api/"
            assert cfg["immich_api_key"] == "key"
            assert cfg["video_crf"] == 30
            # Unset override falls back to the saved Settings default.
            assert cfg["video_preset"] == 4

    async def test_convert_image_formats_override_stored_in_snapshot(self, client):
        await _configure_connection(client)
        resp = await client.post(
            "/api/runs",
            json={"asset_types": "IMAGE", "convert_image_formats": "jpg,png"},
        )
        data = resp.json()
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == data["id"]))
            run = result.scalar_one()
            cfg = json.loads(run.config_snapshot)
            assert cfg["convert_image_formats"] == "jpg,png"

    async def test_image_target_format_override_stored_in_snapshot(self, client):
        await _configure_connection(client)
        resp = await client.post(
            "/api/runs",
            json={
                "asset_types": "IMAGE",
                "image_target_format": "heic",
                "image_quality_heic": 70,
            },
        )
        data = resp.json()
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == data["id"]))
            run = result.scalar_one()
            cfg = json.loads(run.config_snapshot)
            assert cfg["image_target_format"] == "heic"
            assert cfg["image_quality_heic"] == 70
            # Unset overrides fall back to the saved Settings defaults.
            assert cfg["image_quality_avif"] == 75

    async def test_image_jxl_effort_override_stored_in_snapshot(self, client):
        await _configure_connection(client)
        resp = await client.post(
            "/api/runs",
            json={"asset_types": "IMAGE", "image_jxl_effort": 9},
        )
        data = resp.json()
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == data["id"]))
            run = result.scalar_one()
            cfg = json.loads(run.config_snapshot)
            assert cfg["image_jxl_effort"] == 9

    async def test_output_mode_override_stored_in_snapshot(self, client):
        await _configure_connection(client)
        resp = await client.post(
            "/api/runs",
            json={
                "asset_types": "IMAGE",
                "output_mode": "local",
                "local_output_dir": "/data/converted",
                "local_keep_originals": True,
            },
        )
        data = resp.json()
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == data["id"]))
            run = result.scalar_one()
            cfg = json.loads(run.config_snapshot)
            assert cfg["output_mode"] == "local"
            assert cfg["local_output_dir"] == "/data/converted"
            assert cfg["local_keep_originals"] is True

    async def test_explicit_asset_ids_stored_in_snapshot(self, client):
        await _configure_connection(client)
        resp = await client.post(
            "/api/runs", json={"asset_ids": ["a1", "a2"], "dry_run": False}
        )
        data = resp.json()
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == data["id"]))
            run = result.scalar_one()
            cfg = json.loads(run.config_snapshot)
            assert cfg["asset_ids"] == ["a1", "a2"]


class TestRunTimestampsAreUtcAware:
    """Regression test for the offset-less UTC timestamp bug.

    Run.created_at is always written as datetime.now(timezone.utc), but a
    plain DateTime column drops the tzinfo on read on SQLite -- so without
    the TZDateTime column type (app/models/types.py), the API returns e.g.
    "2026-09-23T22:00:01" instead of "...+00:00". A browser's
    `new Date(...)` treats the former as local time instead of converting
    it, making a run that started at local midnight (CEST, UTC+2) display
    as if it started at 22:00.

    datetime.fromisoformat() round-trips exactly what a browser's Date
    parser cares about: whether an offset is present at all. tzinfo is
    None for the old, broken shape (plain DateTime column) and
    datetime.timezone.utc for the fixed one (TZDateTime), so asserting
    `parsed.tzinfo is not None` fails on the old column type and passes
    on the new one. See test_types.py for unit tests of TZDateTime
    itself; these exercise it through the real API round-trip.
    """

    async def test_created_at_round_trips_through_sqlite_with_a_utc_offset(
        self, client
    ):
        from datetime import datetime

        await _configure_connection(client)
        resp = await client.post(
            "/api/runs", json={"asset_types": "IMAGE", "dry_run": True}
        )
        data = resp.json()

        parsed = datetime.fromisoformat(data["created_at"])
        assert parsed.tzinfo is not None, (
            f"created_at={data['created_at']!r} has no UTC offset -- a "
            "browser's `new Date(...)` will misread this as local time"
        )
        assert parsed.utcoffset().total_seconds() == 0

    async def test_asset_outcome_updated_at_has_a_utc_offset(self, client):
        from datetime import datetime

        await _configure_connection(client)
        run_resp = await client.post(
            "/api/runs", json={"asset_ids": ["a1"], "dry_run": False}
        )
        run_id = run_resp.json()["id"]

        async with AsyncSessionLocal() as db:
            outcome = AssetOutcome(
                run_id=run_id,
                asset_id="a1",
                filename="a1.jpg",
                status="success",
            )
            db.add(outcome)
            await db.commit()

        resp = await client.get(f"/api/runs/{run_id}/assets")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1

        parsed = datetime.fromisoformat(items[0]["updated_at"])
        assert parsed.tzinfo is not None, (
            f"updated_at={items[0]['updated_at']!r} has no UTC offset"
        )


class TestListAndGetRuns:
    async def test_list_and_get(self, client):
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]

        list_resp = await client.get("/api/runs")
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] >= 1

        get_resp = await client.get(f"/api/runs/{run_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == run_id

    async def test_get_missing_run_404(self, client):
        resp = await client.get("/api/runs/999999")
        assert resp.status_code == 404

    async def test_filter_by_status(self, client):
        await _configure_connection(client)
        await client.post("/api/runs", json={"asset_types": "IMAGE"})
        resp = await client.get("/api/runs", params={"status": "queued"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert all(item["status"] == "queued" for item in items)


class TestRunAssets:
    async def test_lists_outcomes_for_run(self, client):
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            db.add(
                AssetOutcome(
                    run_id=run_id,
                    asset_id="a1",
                    filename="a.jpg",
                    status="success",
                )
            )
            db.add(
                AssetOutcome(
                    run_id=run_id,
                    asset_id="a2",
                    filename="b.jpg",
                    status="failed_upload",
                    error="boom",
                )
            )
            await db.commit()

        resp = await client.get(f"/api/runs/{run_id}/assets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

        failed_resp = await client.get(
            f"/api/runs/{run_id}/assets", params={"status": "failed_upload"}
        )
        failed_data = failed_resp.json()
        assert failed_data["total"] == 1
        assert failed_data["items"][0]["asset_id"] == "a2"


class TestCancelRun:
    async def test_cancel_queued_run_marks_cancelled_immediately(self, client):
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]

        resp = await client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_cancel_missing_run_404(self, client):
        resp = await client.delete("/api/runs/999999")
        assert resp.status_code == 404

    async def test_cancel_finished_run_is_idempotent(self, client):
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one()
            run.status = "completed"
            await db.commit()

        resp = await client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


class TestRetryFailed:
    async def test_creates_new_run_with_failed_ids_only(self, client):
        await _configure_connection(client)
        created = await client.post(
            "/api/runs", json={"asset_types": "IMAGE", "video_crf": 33}
        )
        run_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            db.add(
                AssetOutcome(
                    run_id=run_id, asset_id="a1", filename="a.jpg", status="success"
                )
            )
            db.add(
                AssetOutcome(
                    run_id=run_id,
                    asset_id="a2",
                    filename="b.jpg",
                    status="failed_upload",
                    error="boom",
                )
            )
            db.add(
                AssetOutcome(
                    run_id=run_id,
                    asset_id="a3",
                    filename="c.jpg",
                    status="failed_transcode",
                )
            )
            await db.commit()

        resp = await client.post(f"/api/runs/{run_id}/retry-failed")
        assert resp.status_code == 200
        new_run_id = resp.json()["id"]
        assert new_run_id != run_id

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            result = await db.execute(select(Run).where(Run.id == new_run_id))
            new_run = result.scalar_one()
            cfg = json.loads(new_run.config_snapshot)
            assert set(cfg["asset_ids"]) == {"a2", "a3"}
            assert cfg["video_crf"] == 33  # carried over from the source run

    async def test_no_failures_returns_400(self, client):
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]
        async with AsyncSessionLocal() as db:
            db.add(
                AssetOutcome(
                    run_id=run_id, asset_id="a1", filename="a.jpg", status="success"
                )
            )
            await db.commit()

        resp = await client.post(f"/api/runs/{run_id}/retry-failed")
        assert resp.status_code == 400

    async def test_missing_run_404(self, client):
        resp = await client.post("/api/runs/999999/retry-failed")
        assert resp.status_code == 404


class TestExportFailures:
    async def test_returns_csv_of_non_final_outcomes(self, client):
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            db.add(
                AssetOutcome(
                    run_id=run_id, asset_id="a1", filename="a.jpg", status="success"
                )
            )
            db.add(
                AssetOutcome(
                    run_id=run_id,
                    asset_id="a2",
                    filename="b.jpg",
                    status="failed_upload",
                    error="boom",
                )
            )
            await db.commit()

        resp = await client.get(f"/api/runs/{run_id}/export-failures")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        body = resp.text
        assert "a2" in body
        assert "b.jpg" in body
        assert "boom" in body
        assert "a1" not in body

    async def test_updated_at_column_has_a_utc_offset(self, client):
        """CSV export reads AssetOutcome.updated_at straight off the ORM
        object (not through AssetOutcomeResponse) -- it only gets a UTC
        offset because TZDateTime makes that true at the column itself,
        for every reader, not because this route was patched directly."""
        await _configure_connection(client)
        created = await client.post("/api/runs", json={"asset_types": "IMAGE"})
        run_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            db.add(
                AssetOutcome(
                    run_id=run_id,
                    asset_id="a2",
                    filename="b.jpg",
                    status="failed_upload",
                    error="boom",
                )
            )
            await db.commit()

        resp = await client.get(f"/api/runs/{run_id}/export-failures")
        body = resp.text
        updated_at_field = body.strip().splitlines()[-1].split(",")[-1]
        assert "+00:00" in updated_at_field, (
            f"CSV updated_at={updated_at_field!r} has no UTC offset"
        )

    async def test_missing_run_404(self, client):
        resp = await client.get("/api/runs/999999/export-failures")
        assert resp.status_code == 404
