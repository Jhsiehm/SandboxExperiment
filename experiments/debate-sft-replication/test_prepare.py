import json
import unittest

from prepare import build_examples


def row(kind, order, who, text, recipient="", validity="VALID"):
    return dict(
        event_type=kind,
        event_order=str(order),
        worker_id=who,
        sender_id=who,
        recipient_id=recipient,
        text=text,
        sliderValue="3",
        chat_round_order="1.0",
        validity=validity,
    )


class EvidenceTests(unittest.TestCase):
    def initial(self):
        return [row("Initial Opinion", i + 1, p, "initial " + p) for i, p in enumerate("abcd")]

    def test_only_preceding_observed_messages(self):
        rows = self.initial() + [
            row("message_sent", 5, "a", "earlier", "b"),
            dict(row("message_received", 6, "b", "earlier", "b"), sender_id="a"),
            row("message_sent", 7, "b", "target", "a"),
            dict(row("message_received", 8, "a", "target", "a"), sender_id="b"),
            row("Post Opinion", 9, "b", "FUTURE_LABEL_SECRET"),
        ]
        data, _ = build_examples(rows, "topic", "g")
        first = json.loads(data[0]["messages"][1]["content"])
        second = json.loads(data[1]["messages"][1]["content"])
        self.assertEqual(first["history"], [])
        self.assertEqual([h["text"] for h in second["history"]], ["earlier"])
        self.assertNotIn("FUTURE_LABEL_SECRET", json.dumps(data))
        self.assertNotIn("initial a", data[1]["messages"][1]["content"])
        self.assertNotIn("target", data[1]["messages"][1]["content"])

    def test_unseen_receipt_rejected(self):
        with self.assertRaises(ValueError):
            build_examples(
                self.initial()
                + [dict(row("message_received", 5, "b", "unknown", "b"), sender_id="a")],
                "t",
                "g",
            )

    def test_invalid_target_not_supervised(self):
        rows = self.initial() + [
            row("message_sent", 5, "a", "invalid", "b", "INVALID"),
            dict(row("message_received", 6, "b", "invalid", "b"), sender_id="a"),
        ]
        data, counts = build_examples(rows, "t", "g")
        self.assertEqual(data, [])
        self.assertEqual(counts["invalid_targets"], 1)

    def test_missing_receipt_rejected(self):
        with self.assertRaises(ValueError):
            build_examples(self.initial() + [row("message_sent", 5, "a", "lost", "b")], "t", "g")


if __name__ == "__main__":
    unittest.main()
