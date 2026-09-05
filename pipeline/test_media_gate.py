import unittest

from pipeline.media_gate import GateError, authorize


def base_job():
    return {
        "job_id":"generic-test",
        "requirements":[
            {
                "requirement_id":"visual_anchor",
                "role":"style",
                "media_type":"image",
                "source_id":"child/assets/ref.png",
                "conditioning":"MUST_SUPPLY_MEDIA",
                "required":True,
                "expected_hash":None,
            }
        ],
        "renderer":{
            "renderer_id":"renderer-x",
            "supports_explicit_media_inputs":True,
            "supported_media_types":["image","audio"],
            "max_media_inputs":4,
            "supported_prompt_bindings":["EXPLICIT","INFERRED"],
        },
        "supplied":[
            {
                "requirement_id":"visual_anchor",
                "source_id":"child/assets/ref.png",
                "media_type":"image",
                "input_handle":"provider-input-1",
                "actual_hash":None,
            }
        ],
        "prompt_binding":"EXPLICIT",
    }


class MediaGateTests(unittest.TestCase):
    def test_authorizes_generic_media_job(self):
        self.assertEqual(authorize(base_job()), "AUTHORIZED")

    def test_blocks_renderer_without_media_support(self):
        job=base_job()
        job["renderer"]["supports_explicit_media_inputs"]=False
        with self.assertRaises(GateError):
            authorize(job)

    def test_blocks_missing_supply_evidence(self):
        job=base_job()
        job["supplied"]=[]
        with self.assertRaises(GateError):
            authorize(job)

    def test_blocks_wrong_source(self):
        job=base_job()
        job["supplied"][0]["source_id"]="different.png"
        with self.assertRaises(GateError):
            authorize(job)

    def test_authority_only_can_run_without_supply(self):
        job=base_job()
        job["requirements"][0]["conditioning"]="AUTHORITY_ONLY_ALLOWED"
        job["supplied"]=[]
        job["renderer"]["supports_explicit_media_inputs"]=False
        self.assertEqual(authorize(job), "AUTHORIZED")

    def test_audio_uses_same_contract(self):
        job=base_job()
        job["requirements"][0].update({
            "role":"voice_identity",
            "media_type":"audio",
            "source_id":"child/assets/voice.wav",
        })
        job["supplied"][0].update({
            "media_type":"audio",
            "source_id":"child/assets/voice.wav",
        })
        self.assertEqual(authorize(job), "AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
