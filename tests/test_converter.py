import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from mtrpack.converter import ConvertError, RESOURCE, convert, inspect_pack


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.zip"
        self.template = self.root / "template.json"
        self.base = {
            "vehicles": [
                {"id": "sp1900_trailer", "name": "Trailer", "tags": ["family:sp1900", "type:trailer"],
                 "transportMode": "TRAIN", "models": [
                     {"modelResource": "mtr:models/vehicle/sp1900.bbmodel",
                      "textureResource": "mtr:textures/vehicle/sp1900.png",
                      "modelPropertiesResource": "mtr:properties/vehicle/sp1900_common.json"},
                     {"modelResource": "mtr:models/vehicle/door_overlay.bbmodel",
                      "textureResource": "mtr:textures/overlay/door_overlay.png"}]},
                {"id": "sp1900_cab_1", "name": "Cab", "tags": ["family:sp1900", "type:cab_1"],
                 "transportMode": "TRAIN", "models": [
                     {"modelResource": "mtr:models/vehicle/sp1900.bbmodel",
                      "textureResource": "mtr:textures/vehicle/sp1900.png"}]},
            ]}
        self.template.write_text(json.dumps(self.base), encoding="utf-8")

    def pack(self, obj):
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr(RESOURCE, json.dumps(obj))
            archive.writestr("pack.mcmeta", '{"pack":{"pack_format":9}}')
            archive.writestr("assets/mtr/custom/my.png", b"PNG-bytes")

    def load(self, path):
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read(RESOURCE)), archive.read("assets/mtr/custom/my.png")

    def test_roundtrip_simple_retexture(self):
        self.pack({"custom_trains": {"blue": {"name": "蓝色列车", "color": "123456",
                    "base_train_type": "sp1900", "texture_id": "mtr:custom/my.png"}}})
        self.assertEqual(inspect_pack(self.source)["format"], "3.2")
        four = self.root / "four.zip"
        report = convert(self.source, four, target="4.0", template=self.template)
        self.assertEqual(report["converted_groups"], 1)
        data, asset = self.load(four)
        self.assertEqual(asset, b"PNG-bytes")
        self.assertEqual(len(data["vehicles"]), 2)
        self.assertEqual(data["vehicles"][0]["models"][0]["textureResource"], "mtr:custom/my.png")
        self.assertEqual(data["vehicles"][0]["models"][1]["textureResource"],
                         "mtr:textures/overlay/door_overlay.png")
        three = self.root / "three.zip"
        report = convert(four, three, target="3.2", base_map={"blue": "sp1900"}, allow_partial=True)
        self.assertTrue(report["partial"])
        result, asset = self.load(three)
        self.assertEqual(result["custom_trains"]["blue"]["texture_id"], "mtr:custom/my.png")
        self.assertEqual(result["custom_trains"]["blue"]["base_train_type"], "sp1900")
        self.assertEqual(asset, b"PNG-bytes")

    def test_reject_custom_model_without_writing(self):
        self.pack({"custom_trains": {"x": {"model": "mtr:model.bbmodel"}}})
        out = self.root / "out.zip"
        with self.assertRaises(ConvertError):
            convert(self.source, out, target="4.0", template=self.template)
        self.assertFalse(out.exists())

    def test_reject_unmapped_content_then_allow_partial_and_backup(self):
        self.pack({"custom_trains": {"blue": {"base_train_type": "sp1900",
                   "texture_id": "mtr:custom/my.png"}}, "custom_signs": {"a": {}}})
        out = self.root / "out.zip"
        with self.assertRaises(ConvertError):
            convert(self.source, out, target="4.0", template=self.template)
        self.assertFalse(out.exists())
        convert(self.source, out, target="4.0", template=self.template, allow_partial=True)
        with zipfile.ZipFile(out) as archive:
            self.assertIn("custom_signs", json.loads(archive.read(
                "mtr_converter/original_mtr_custom_resources.json")))

    def test_reject_unsafe_zip(self):
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("../evil", "bad")
            archive.writestr(RESOURCE, '{"vehicles":[]}')
        with self.assertRaises(ConvertError):
            inspect_pack(self.source)


if __name__ == "__main__":
    unittest.main()
