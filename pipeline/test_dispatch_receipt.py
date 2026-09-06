import unittest

from pipeline.dispatch_receipt import ReceiptError, verify_dispatch_receipt


def base_job():
    return {
        "job_id": "job-1",
        "requirements": [
            {
                "requirement_id": "style",
                "media_type": "image",
                "source_id": "asset:style:abc",
                "conditioning": "MUST_SUPPLY_MEDIA",
                "required": True,
                "expected_hash": "abc123",
            }
        ],
        "renderer": {"renderer_id": "renderer-x"},
        "supplied": [
            {
                "requirement_id": "style",
                "asset_id": "asset:style:abc",
                "source_id": "asset:style:abc",
                "media_type": "image",
                "actual_hash": "abc123",
            }
        ],
    }


def base_receipt():
    return {
        "job_id": "job-1",
        "renderer_id": "renderer-x",
        "explicit_media_binding_confirmed": True,
        "bindings": [
            {
                "requirement_id": "style",
                "asset_id": "asset:style:abc",
                "source_id": "asset:style:abc",
                "media_type": "image",
                "actual_hash": "abc123",
                "binding_method": "EXPLICIT_MEDIA_INPUT",
                "input_handle": "/runtime/style.png",
            }
        ],
    }


class DispatchReceiptTests(unittest.TestCase):
    def test_confirms_explicit_binding(self):
        self.assertEqual(verify_dispatch_receipt(base_job(), base_receipt()), "CONFIRMED")

    def test_blocks_missing_required_binding(self):
        receipt = base_receipt()
        receipt["bindings"] = []
        with self.assertRaises(ReceiptError):
            verify_dispatch_receipt(base_job(), receipt)

    def test_blocks_metadata_only_claim(self):
        receipt = base_receipt()
        receipt["bindings"][0]["binding_method"] = "PROMPT_TEXT_ONLY"
        with self.assertRaisesRegex(ReceiptError, "EXPLICIT_MEDIA_INPUT"):
            verify_dispatch_receipt(base_job(), receipt)

    def test_blocks_empty_handle(self):
        receipt = base_receipt()
        receipt["bindings"][0]["input_handle"] = ""
        with self.assertRaisesRegex(ReceiptError, "input_handle"):
            verify_dispatch_receipt(base_job(), receipt)

    def test_blocks_hash_drift(self):
        receipt = base_receipt()
        receipt["bindings"][0]["actual_hash"] = "wrong"
        with self.assertRaisesRegex(ReceiptError, "hash"):
            verify_dispatch_receipt(base_job(), receipt)

    def test_blocks_unconfirmed_explicit_binding(self):
        receipt = base_receipt()
        receipt["explicit_media_binding_confirmed"] = False
        with self.assertRaisesRegex(ReceiptError, "explicit_media_binding_confirmed"):
            verify_dispatch_receipt(base_job(), receipt)


if __name__ == "__main__":
    unittest.main()
