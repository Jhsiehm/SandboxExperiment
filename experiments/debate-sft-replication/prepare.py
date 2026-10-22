"""Offline, development-only next-message SFT preparation. Standard library only."""

import csv
import hashlib
import json
from pathlib import Path

SYSTEM = (
    "Simulate the participant described in the input. Predict their next private chat "
    "message using only their initial opinion and messages they have already seen. "
    "Return only the message text. Preserve their own perspective; agreement is not required."
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_examples(rows, topic, group_id):
    initial = [r for r in rows if r["event_type"] == "Initial Opinion"]
    if len(initial) != 4 or len({r["worker_id"] for r in initial}) != 4:
        raise ValueError("Expected four unambiguous initial records")
    ids = {r["worker_id"]: f"p{i}" for i, r in enumerate(initial)}
    profiles = {}
    for r in initial:
        score = float(r["sliderValue"])
        if not score.is_integer() or not 1 <= score <= 6 or not r["text"].strip():
            raise ValueError("Invalid initial profile")
        profiles[r["worker_id"]] = dict(
            participant=ids[r["worker_id"]],
            topic=topic,
            initial_score=int(score),
            initial_text=r["text"],
        )
    initial_end = max(float(r["event_order"]) for r in initial)
    # Post opinions, exit surveys, and unaddressed public content never enter context.
    events = sorted(
        (r for r in rows if r["event_type"] in ("message_sent", "message_received", "tweet")),
        key=lambda r: float(r["event_order"]),
    )
    orders = [float(r["event_order"]) for r in events]
    if len(orders) != len(set(orders)) or any(o <= initial_end for o in orders):
        raise ValueError("Ambiguous or nonchronological events")
    histories = {i: [] for i in ids}
    pending = {}
    result = []
    excluded = dict(invalid_targets=0, empty_events=0, unaddressed_tweets=0)
    for r in events:
        kind, text = r["event_type"], r["text"].strip()
        if not text or "[AUTOSUBMISSION" in text or "[SLIDER_VALUE=" in text:
            excluded["empty_events"] += 1
            continue
        sender, recipient = r["sender_id"], r["recipient_id"]
        if sender not in ids or recipient not in ids or sender == recipient:
            if kind == "tweet":
                excluded["unaddressed_tweets"] += 1
                continue
            raise ValueError("Unknown directed message participant")
        order = float(r["event_order"])
        round_ = int(float(r["chat_round_order"]))
        if round_ not in (1, 2, 3):
            raise ValueError("Invalid round")
        entry = dict(speaker=ids[sender], round=round_, text=text, event_order=order)
        if kind == "message_sent":
            if r["worker_id"] != sender:
                raise ValueError("Sender ownership mismatch")
            if r.get("validity") == "VALID":
                context = dict(
                    profile=profiles[sender],
                    round=round_,
                    partner=ids[recipient],
                    history=list(histories[sender]),
                )
                result.append(
                    dict(
                        group_id=group_id,
                        topic=topic,
                        participant=ids[sender],
                        target_event_order=order,
                        context_event_orders=[h["event_order"] for h in histories[sender]],
                        messages=[
                            dict(role="system", content=SYSTEM),
                            dict(role="user", content=json.dumps(context, ensure_ascii=False)),
                            dict(role="assistant", content=text),
                        ],
                    )
                )
            else:
                excluded["invalid_targets"] += 1
            histories[sender].append(dict(**entry, direction="own"))
            key = (sender, recipient, round_, text)
            pending.setdefault(key, []).append(order)
        elif kind == "message_received":
            if r["worker_id"] != recipient:
                raise ValueError("Recipient ownership mismatch")
            key = (sender, recipient, round_, text)
            if not pending.get(key):
                raise ValueError("Receipt without preceding matching send")
            pending[key].pop(0)
            histories[recipient].append(dict(**entry, direction="received"))
        else:
            # The release supplies explicit directed tweet recipients. Do not broadcast.
            histories[sender].append(dict(**entry, direction="own_tweet"))
            histories[recipient].append(dict(**entry, direction="received_tweet"))
    if any(pending.values()):
        raise ValueError("Missing receipt for sent message")
    return result, excluded


def prepare(root):
    manifest = json.loads((root / "inputs/manifest.json").read_text())
    train, validation, counts, exclusions = [], [], {}, {}
    rejected = {}
    for g in manifest["groups"]:
        path = root / "inputs" / (g["group_id"] + ".csv")
        if sha(path) != g["sha256"]:
            raise ValueError("Input checksum mismatch")
        with path.open() as f:
            rows = list(csv.DictReader(f))
        try:
            examples, excluded = build_examples(rows, g["topic"], g["group_id"])
        except ValueError as error:
            rejected[g["group_id"]] = str(error)
            continue
        if not examples:
            raise ValueError("No training examples")
        (validation if g["partition"] == "validation" else train).extend(examples)
        counts[g["group_id"]] = len(examples)
        exclusions[g["group_id"]] = excluded
    tg = {r["group_id"] for r in train}
    vg = {r["group_id"] for r in validation}
    assert tg and vg and not tg & vg
    assert not {r["topic"] for r in train} & {r["topic"] for r in validation}
    assert all(
        all(e < r["target_event_order"] for e in r["context_event_orders"])
        for r in train + validation
    )
    return dict(
        train=train,
        validation=validation,
        audit=dict(
            training_examples=len(train),
            validation_examples=len(validation),
            training_groups=len(tg),
            validation_groups=len(vg),
            per_group=counts,
            rejected_groups=rejected,
            replacements=False,
            exclusions=exclusions,
            topic_overlap=0,
            future_events_in_context=0,
            reserve_files_loaded=0,
            adaptation=(
                "Private next-chat-message targets only; directed tweets retained as context. "
                "Not an exact paper replication."
            ),
        ),
    )


if __name__ == "__main__":
    print(json.dumps(prepare(Path("/app")), ensure_ascii=False))
