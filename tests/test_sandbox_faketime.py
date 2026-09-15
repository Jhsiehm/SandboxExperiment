from datetime import date

import pytest
from fastapi.testclient import TestClient

from psbx.config import load_epochs
from psbx.sandbox.client import HttpSearchClient, LocalSearchClient
from psbx.sandbox.clock import faketime_env, faketime_stamp
from psbx.sandbox.harness import require_question_epoch, search_client_for
from psbx.sandbox.search_service import create_app
from psbx.schemas import Question, RunConfig


def test_faketime_stamp_freezes_end_of_cutoff_day():
    assert faketime_stamp(date(2012, 6, 30)) == "2012-06-30 12:00:00"
    env = faketime_env(date(2012, 6, 30), lib="/usr/lib/faketime/libfaketime.so.1")
    assert env["FAKETIME"] == "2012-06-30 12:00:00"
    assert env["FAKETIME_NO_CACHE"] == "1"
    assert "libfaketime.so.1" in env["LD_PRELOAD"]


def test_container_entrypoint_uses_stopped_clock_and_drops_privileges():
    from psbx.paths import resolve

    entrypoint = resolve("src/psbx/sandbox/entrypoint.sh").read_text(encoding="utf-8")
    assert 'export FAKETIME="${CUTOFF}"' in entrypoint
    assert 'export FAKETIME="@${CUTOFF}"' not in entrypoint
    assert "setpriv --reuid=psbx --regid=psbx" in entrypoint
    assert 'env LD_PRELOAD="${FAKETIME_LIB}" python' in entrypoint


def test_container_run_command_is_hardened(monkeypatch):
    from types import SimpleNamespace

    from psbx.sandbox import docker_sidecar

    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        del kwargs
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(docker_sidecar, "docker_bin", lambda: "docker")
    monkeypatch.setattr(docker_sidecar.subprocess, "run", fake_run)
    monkeypatch.setattr(docker_sidecar, "_wait_healthy", lambda: None)
    monkeypatch.setattr(
        docker_sidecar,
        "_index_mount",
        lambda epoch_id, source_type: (
            f"/host/{epoch_id}/silos/{source_type}",
            f"/app/data/corpus/{epoch_id}",
        ),
    )
    docker_sidecar.up("e2012", source_type="survey")

    run_command = next(command for command in calls if command[:2] == ["docker", "run"])
    assert "--read-only" in run_command
    assert "/tmp:rw,nosuid,nodev,noexec,size=64m" in run_command
    assert "no-new-privileges:true" in run_command
    assert run_command[run_command.index("--cap-drop") + 1] == "ALL"
    cap_adds = [
        run_command[index + 1] for index, value in enumerate(run_command) if value == "--cap-add"
    ]
    assert cap_adds == ["NET_ADMIN", "SETUID", "SETGID"]
    assert run_command[run_command.index("--pids-limit") + 1] == "128"
    assert "/host/e2012/silos/survey:/app/data/corpus/e2012:ro" in run_command
    assert "PSBX_ACTIVE_SOURCE_TYPE=survey" in run_command


def test_container_status_verifies_runtime_isolation(monkeypatch):
    import json
    from types import SimpleNamespace

    from psbx.sandbox import docker_sidecar

    runtime = [
        {
            "HostConfig": {
                "ReadonlyRootfs": True,
                "SecurityOpt": ["no-new-privileges:true"],
                "PortBindings": {
                    "8766/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8766"}]
                },
                "PidsLimit": 128,
            },
            "Config": {"Env": ["PSBX_LOCK_EGRESS=1"]},
            "Mounts": [{"Source": "/host/index", "Destination": "/app/index", "RW": False}],
        }
    ]

    def fake_run(command, **kwargs):
        del kwargs
        if "-f" in command:
            return SimpleNamespace(returncode=0, stdout="running\n", stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps(runtime), stderr="")

    monkeypatch.setattr(docker_sidecar, "docker_bin", lambda: "docker")
    monkeypatch.setattr(docker_sidecar.subprocess, "run", fake_run)
    body = docker_sidecar.status()
    assert body["running"] is True
    assert body["read_only_rootfs"] is True
    assert body["mounts_read_only"] is True
    assert body["no_new_privileges"] is True
    assert body["loopback_only"] is True
    assert body["egress_lock_requested"] is True
    assert body["pids_limit"] == 128
    assert body["verified_controls"] is True


def test_clock_endpoint_reports_cutoff():
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    client = TestClient(create_app(index))
    body = client.get("/clock").json()
    assert body["cutoff"] == "2012-06-30"
    assert "now" in body
    assert "today" in body


def test_health_endpoint_reports_active_corpus_cell(monkeypatch):
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = [doc for doc in collect_documents(epoch) if doc.source_type == "survey"]
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    monkeypatch.setenv("PSBX_ACTIVE_SOURCE_TYPE", "survey")
    body = TestClient(create_app(index, epoch_id="e2012")).get("/health").json()
    assert body == {
        "status": "ok",
        "epoch": "e2012",
        "cutoff": "2012-06-30",
        "source_types": ["survey"],
        "n_documents": len(docs),
        "selection": "survey",
    }


def test_http_client_fails_closed_on_wrong_corpus_selection(monkeypatch):
    client = HttpSearchClient()
    monkeypatch.setattr(
        client,
        "health",
        lambda: {"epoch": "e2012", "selection": "news", "cutoff": "2012-06-30"},
    )
    with pytest.raises(RuntimeError, match="selection mismatch"):
        client.require_selection("e2012", "survey", "2012-06-30")


def test_http_client_fails_closed_on_wrong_cutoff(monkeypatch):
    client = HttpSearchClient()
    monkeypatch.setattr(
        client,
        "health",
        lambda: {"epoch": "e2012", "selection": "survey", "cutoff": "2012-05-31"},
    )
    with pytest.raises(RuntimeError, match="cutoff=2012-05-31"):
        client.require_selection("e2012", "survey", "2012-06-30")


def test_question_pack_cannot_cross_epoch_boundary():
    from psbx.io import read_jsonl

    epoch = load_epochs()["e2012"]
    question = read_jsonl("data/questions/e2012.jsonl", Question)[0]
    wrong = question.model_copy(update={"epoch_id": "e2013"})
    with pytest.raises(ValueError, match="question epoch leakage"):
        require_question_epoch([wrong], epoch)


def test_archive_proxy_serves_index_only():
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    client = TestClient(create_app(index))
    known = docs[0]
    ok = client.get("/archive", params={"url": known.url})
    assert ok.status_code == 200
    body = ok.json()
    assert body["id"] == known.id
    assert body["url"] == known.url
    assert body["published_at"][:10] <= "2012-06-30"

    missing = client.get(
        "/archive",
        params={"url": "https://www.nytimes.com/2013/07/01/world/syria.html"},
    )
    assert missing.status_code == 404
    empty = client.get("/archive", params={"url": ""})
    assert empty.status_code == 404
    unknown = client.get("/archive", params={"url": "https://example.com/never-indexed"})
    assert unknown.status_code == 404


def test_host_sandbox_uses_local_client():
    from psbx.corpus.build_index import collect_documents
    from psbx.corpus.embed import embed_texts
    from psbx.corpus.index import HybridIndex

    epoch = load_epochs()["e2012"]
    docs = collect_documents(epoch)
    embeddings = embed_texts([f"{d.title}\n{d.text}" for d in docs], backend="hashing")
    index = HybridIndex(docs, embeddings, epoch.cutoff_date)
    run = RunConfig(
        run_id="t",
        epoch="e2012",
        models=["gpt-oss-2012ish"],
        question_set="data/questions/e2012.jsonl",
        sandbox_mode="host",
    )
    client = search_client_for(run, index)
    assert isinstance(client, LocalSearchClient)
